"""
Create API Gateway REST API, Lambda integration, deployment, and WAF association.

Environment variables:
  AWS_REGION              (default: ap-south-1)
  LAMBDA_FUNCTION_NAME    (default: SpendAgentAdapter)
  WAF_WEB_ACL_ARN         (required for WAF association)
  API_NAME                (default: SpendAgentAPI)
  STAGE_NAME              (default: prod)

Usage:
  export LAMBDA_FUNCTION_ARN=arn:aws:lambda:ap-south-1:387957186026:function:SpendAgentAdapter
  export WAF_WEB_ACL_ARN=arn:aws:wafv2:ap-south-1:387957186026:regional/webacl/SpendAgentWAF/...
  python api_gateway.py
"""

import json
import os
import time

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
API_NAME = os.environ.get("API_NAME", "SpendAgentAPI")
STAGE_NAME = os.environ.get("STAGE_NAME", "prod")
LAMBDA_FUNCTION_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "SpendAgentAdapter")
LAMBDA_ARN = os.environ.get("LAMBDA_FUNCTION_ARN")
WAF_WEB_ACL_ARN = os.environ.get("WAF_WEB_ACL_ARN")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID")


def _account_id():
    if ACCOUNT_ID:
        return ACCOUNT_ID
    return boto3.client("sts").get_caller_identity()["Account"]


def create_api(lambda_arn: str) -> dict:
    apigw = boto3.client("apigateway", region_name=REGION)
    account = _account_id()

    api = apigw.create_rest_api(
        name=API_NAME,
        description="Spend Analytics Agent API",
        endpointConfiguration={"types": ["REGIONAL"]},
    )
    api_id = api["id"]
    print(f"Created REST API: {api_id}")

    resources = apigw.get_resources(restApiId=api_id)
    root_id = next(r["id"] for r in resources["items"] if r["path"] == "/")

    chat_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="chat",
    )["id"]

    chat_job_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=chat_resource,
        pathPart="{job_id}",
    )["id"]

    dashboard_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="dashboard",
    )["id"]

    lambda_uri = (
        f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/"
        f"{lambda_arn}/invocations"
    )

    def add_cors_options(resource_id: str):
        apigw.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            authorizationType="NONE",
            apiKeyRequired=False,
        )
        apigw.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            type="MOCK",
            requestTemplates={"application/json": '{"statusCode": 200}'},
        )
        apigw.put_method_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Headers": True,
                "method.response.header.Access-Control-Allow-Methods": True,
                "method.response.header.Access-Control-Allow-Origin": True,
            },
        )
        apigw.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters={
                "method.response.header.Access-Control-Allow-Origin": "'*'",
                "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
            },
        )

    routes = [
        (chat_resource, "POST"),
        (chat_job_resource, "GET"),
        (dashboard_resource, "GET"),
    ]
    for resource_id, method in routes:
        apigw.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=method,
            authorizationType="NONE",
            apiKeyRequired=True,
        )
        apigw.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=method,
            type="AWS_PROXY",
            integrationHttpMethod="POST",
            uri=lambda_uri,
        )
        add_cors_options(resource_id)

    apigw.create_deployment(restApiId=api_id, stageName=STAGE_NAME)
    print(f"Deployed stage: {STAGE_NAME}")

    usage_plan_id = apigw.create_usage_plan(
        name=os.environ.get("USAGE_PLAN_NAME", "SpendAgentUsagePlan"),
        description="Spend Analytics Agent frontend",
        apiStages=[{"apiId": api_id, "stage": STAGE_NAME}],
        throttle={"rateLimit": 100, "burstLimit": 200},
    )["id"]
    api_key = apigw.create_api_key(
        name=os.environ.get("API_KEY_NAME", "SpendAgentFrontendKey"),
        description="Frontend key for Spend Analytics Agent",
        enabled=True,
    )
    apigw.create_usage_plan_key(
        usagePlanId=usage_plan_id,
        keyId=api_key["id"],
        keyType="API_KEY",
    )
    print(f"API_KEY_VALUE={api_key['value']}")

    lambda_client = boto3.client("lambda", region_name=REGION)
    for path in ["chat", "chat/*", "dashboard"]:
        source_arn = (
            f"arn:aws:execute-api:{REGION}:{account}:{api_id}/*/*/{path}"
        )
        try:
            lambda_client.add_permission(
                FunctionName=LAMBDA_FUNCTION_NAME,
                StatementId=f"apigateway-{path}",
                Action="lambda:InvokeFunction",
                Principal="apigateway.amazonaws.com",
                SourceArn=source_arn,
            )
        except lambda_client.exceptions.ResourceConflictException:
            print(f"Permission already exists for /{path}")

    invoke_url = (
        f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
    )

    if WAF_WEB_ACL_ARN:
        waf = boto3.client("wafv2", region_name=REGION)
        stage_arn = (
            f"arn:aws:apigateway:{REGION}::/restapis/{api_id}/stages/{STAGE_NAME}"
        )
        waf.associate_web_acl(WebACLArn=WAF_WEB_ACL_ARN, ResourceArn=stage_arn)
        print(f"Associated WAF with stage: {stage_arn}")

    result = {
        "api_id": api_id,
        "invoke_url": invoke_url,
        "chat_url": f"{invoke_url}/chat",
        "dashboard_url": f"{invoke_url}/dashboard",
    }
    print(json.dumps(result, indent=2))
    return result


def resolve_lambda_arn() -> str:
    if LAMBDA_ARN:
        return LAMBDA_ARN
    account = _account_id()
    return (
        f"arn:aws:lambda:{REGION}:{account}:function:{LAMBDA_FUNCTION_NAME}"
    )


if __name__ == "__main__":
    time.sleep(0)
    create_api(resolve_lambda_arn())
