"""
Async chat: DynamoDB job table, GET /chat/{job_id}, Lambda deploy.

Usage:
  set -a && source deploy/aws.env && set +a
  python infra/setup_async_chat.py
"""

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "387957186026")
API_ID = os.environ["API_GATEWAY_ID"]
STAGE_NAME = os.environ.get("STAGE_NAME", "prod")
LAMBDA_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "SpendAgentAdapter")
JOBS_TABLE = os.environ.get("CHAT_JOBS_TABLE", "SpendAgentChatJobs")
REPO_ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = REPO_ROOT / "lambda"


def _ensure_jobs_table(dynamodb_client):
    existing = dynamodb_client.list_tables().get("TableNames", [])
    if JOBS_TABLE in existing:
        print(f"DynamoDB table exists: {JOBS_TABLE}")
        return

    print(f"Creating DynamoDB table: {JOBS_TABLE}")
    dynamodb_client.create_table(
        TableName=JOBS_TABLE,
        KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    waiter = dynamodb_client.get_waiter("table_exists")
    waiter.wait(TableName=JOBS_TABLE)

    dynamodb_client.update_time_to_live(
        TableName=JOBS_TABLE,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"},
    )
    print("TTL enabled on expires_at")


def _attach_lambda_policy(iam, role_name: str):
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeAgentCore",
                "Effect": "Allow",
                "Action": "bedrock-agentcore:InvokeAgentRuntime",
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:runtime/spendagentv1_MyAgent-TeCbnqAkL9",
                    f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:runtime/spendagentv1_MyAgent-TeCbnqAkL9/runtime-endpoint/DEFAULT",
                ],
            },
            {
                "Sid": "ChatJobsDynamoDB",
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                ],
                "Resource": f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/{JOBS_TABLE}",
            },
            {
                "Sid": "AsyncSelfInvoke",
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{LAMBDA_NAME}",
            },
            {
                "Sid": "BasicLambdaExecution",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:/aws/lambda/{LAMBDA_NAME}:*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="SpendAgentAdapterPolicy",
        PolicyDocument=json.dumps(policy_doc),
    )
    print(f"Updated inline policy on role: {role_name}")


def _deploy_lambda(lambda_client, role_name: str):
    zip_path = Path(tempfile.mktemp(suffix=".zip"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(LAMBDA_DIR / "handler.py", "handler.py")

    print(f"Updating Lambda code: {LAMBDA_NAME}")
    lambda_client.update_function_code(
        FunctionName=LAMBDA_NAME,
        ZipFile=zip_path.read_bytes(),
    )
    zip_path.unlink(missing_ok=True)

    for attempt in range(12):
        try:
            waiter = lambda_client.get_waiter("function_updated")
            waiter.wait(FunctionName=LAMBDA_NAME)
            cfg = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
            env = cfg.get("Environment", {}).get("Variables", {})
            env.update(
                {
                    "CHAT_JOBS_TABLE": JOBS_TABLE,
                    "LAMBDA_FUNCTION_NAME": LAMBDA_NAME,
                }
            )
            lambda_client.update_function_configuration(
                FunctionName=LAMBDA_NAME,
                Handler="handler.handler",
                Timeout=120,
                Environment={"Variables": env},
            )
            print("Lambda code and env updated (timeout=120s)")
            break
        except lambda_client.exceptions.ResourceConflictException:
            time.sleep(3)
    else:
        raise RuntimeError("Lambda configuration update timed out")


def _add_poll_route(apigw, lambda_arn: str):
    resources = apigw.get_resources(restApiId=API_ID)["items"]
    paths = {r["path"]: r["id"] for r in resources}
    chat_id = paths.get("/chat")
    if not chat_id:
        raise RuntimeError("/chat resource not found on API")

    job_path = "/chat/{job_id}"
    if job_path not in paths:
        job_resource = apigw.create_resource(
            restApiId=API_ID,
            parentId=chat_id,
            pathPart="{job_id}",
        )["id"]
        print(f"Created resource {job_path}")
    else:
        job_resource = paths[job_path]

    lambda_uri = (
        f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    )

    try:
        apigw.put_method(
            restApiId=API_ID,
            resourceId=job_resource,
            httpMethod="GET",
            authorizationType="NONE",
            apiKeyRequired=True,
        )
    except apigw.exceptions.ConflictException:
        apigw.update_method(
            restApiId=API_ID,
            resourceId=job_resource,
            httpMethod="GET",
            patchOperations=[
                {"op": "replace", "path": "/apiKeyRequired", "value": "true"},
            ],
        )

    apigw.put_integration(
        restApiId=API_ID,
        resourceId=job_resource,
        httpMethod="GET",
        type="AWS_PROXY",
        integrationHttpMethod="POST",
        uri=lambda_uri,
    )

    # OPTIONS for CORS
    try:
        apigw.put_method(
            restApiId=API_ID,
            resourceId=job_resource,
            httpMethod="OPTIONS",
            authorizationType="NONE",
            apiKeyRequired=False,
        )
    except apigw.exceptions.ConflictException:
        pass

    apigw.put_integration(
        restApiId=API_ID,
        resourceId=job_resource,
        httpMethod="OPTIONS",
        type="MOCK",
        requestTemplates={"application/json": '{"statusCode": 200}'},
    )
    apigw.put_method_response(
        restApiId=API_ID,
        resourceId=job_resource,
        httpMethod="OPTIONS",
        statusCode="200",
        responseParameters={
            "method.response.header.Access-Control-Allow-Headers": True,
            "method.response.header.Access-Control-Allow-Methods": True,
            "method.response.header.Access-Control-Allow-Origin": True,
        },
    )
    apigw.put_integration_response(
        restApiId=API_ID,
        resourceId=job_resource,
        httpMethod="OPTIONS",
        statusCode="200",
        responseParameters={
            "method.response.header.Access-Control-Allow-Origin": "'*'",
            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
            "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
        },
    )

    lambda_client = boto3.client("lambda", region_name=REGION)
    source_arn = f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{API_ID}/*/*/chat/*"
    try:
        lambda_client.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId="apigateway-chat-job-id",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=source_arn,
        )
    except lambda_client.exceptions.ResourceConflictException:
        print("Lambda permission for /chat/{job_id} already exists")

    deployment = apigw.create_deployment(
        restApiId=API_ID,
        stageName=STAGE_NAME,
        description="Async chat poll route",
    )
    print(f"Deployed API stage {STAGE_NAME}: {deployment['id']}")


def main():
    dynamodb_client = boto3.client("dynamodb", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)
    iam = boto3.client("iam", region_name=REGION)
    apigw = boto3.client("apigateway", region_name=REGION)

    _ensure_jobs_table(dynamodb_client)

    cfg = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    role_arn = cfg["Role"]
    role_name = role_arn.split("/")[-1]
    _attach_lambda_policy(iam, role_name)
    _deploy_lambda(lambda_client, role_name)

    lambda_arn = cfg["FunctionArn"]
    _add_poll_route(apigw, lambda_arn)

    invoke_url = f"https://{API_ID}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
    print(json.dumps({"invoke_url": invoke_url, "jobs_table": JOBS_TABLE}, indent=2))


if __name__ == "__main__":
    main()
