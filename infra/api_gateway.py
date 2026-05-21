"""
Create API Gateway REST API, Lambda integration, deployment, and WAF association.

Environment variables:
  AWS_REGION              (default: ap-south-1)
  LAMBDA_FUNCTION_NAME    (default: SpendAgentAdapter)
  WAF_WEB_ACL_ARN         (required for WAF association)
  API_NAME                (default: SpendAgentAPI)
  STAGE_NAME              (default: prod)
  API_GATEWAY_ID          (optional — add file routes to existing API)
  COGNITO_USER_POOL_ID    (optional — Cognito authorizer for protected routes)
  AUTHORIZER_NAME         (default: SpendAgentCognitoAuthorizer)

Usage:
  export LAMBDA_FUNCTION_ARN=arn:aws:lambda:ap-south-1:387957186026:function:SpendAgentAdapter
  export WAF_WEB_ACL_ARN=arn:aws:wafv2:ap-south-1:387957186026:regional/webacl/SpendAgentWAF/...
  python api_gateway.py

  # Add upload routes to an existing API:
  export API_GATEWAY_ID=ee5b0fv5kc
  export COGNITO_USER_POOL_ID=ap-south-1_...
  python api_gateway.py --add-file-routes
"""

import argparse
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
API_ID = os.environ.get("API_GATEWAY_ID")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
AUTHORIZER_NAME = os.environ.get("AUTHORIZER_NAME", "SpendAgentCognitoAuthorizer")

CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
}


def _account_id():
    if ACCOUNT_ID:
        return ACCOUNT_ID
    return boto3.client("sts").get_caller_identity()["Account"]


def _lambda_uri(lambda_arn: str) -> str:
    return (
        f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/"
        f"{lambda_arn}/invocations"
    )


def _find_authorizer(apigw, api_id: str) -> str | None:
    authorizers = apigw.get_authorizers(restApiId=api_id)["items"]
    match = next((a for a in authorizers if a["name"] == AUTHORIZER_NAME), None)
    return match["id"] if match else None


def _ensure_cognito_authorizer(apigw, api_id: str) -> str | None:
    existing = _find_authorizer(apigw, api_id)
    if existing:
        return existing
    if not COGNITO_USER_POOL_ID:
        return None

    account = _account_id()
    pool_arn = f"arn:aws:cognito-idp:{REGION}:{account}:userpool/{COGNITO_USER_POOL_ID}"
    authorizer_id = apigw.create_authorizer(
        restApiId=api_id,
        name=AUTHORIZER_NAME,
        type="COGNITO_USER_POOLS",
        providerARNs=[pool_arn],
        identitySource="method.request.header.Authorization",
    )["id"]
    print(f"Created authorizer: {AUTHORIZER_NAME} ({authorizer_id})")
    return authorizer_id


def add_cors_options(apigw, api_id: str, resource_id: str):
    try:
        apigw.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            authorizationType="NONE",
            apiKeyRequired=False,
        )
    except apigw.exceptions.ConflictException:
        apigw.update_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            patchOperations=[
                {"op": "replace", "path": "/authorizationType", "value": "NONE"},
                {"op": "replace", "path": "/apiKeyRequired", "value": "false"},
            ],
        )

    try:
        apigw.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            type="MOCK",
            requestTemplates={"application/json": '{"statusCode": 200}'},
        )
    except apigw.exceptions.ConflictException:
        pass

    try:
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
    except apigw.exceptions.ConflictException:
        pass

    try:
        apigw.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters=CORS_HEADERS,
        )
    except apigw.exceptions.ConflictException:
        pass


def add_lambda_route(
    apigw,
    api_id: str,
    resource_id: str,
    http_method: str,
    lambda_uri: str,
    authorizer_id: str | None = None,
):
    auth_type = "COGNITO_USER_POOLS" if authorizer_id else "NONE"
    method_kwargs = {
        "restApiId": api_id,
        "resourceId": resource_id,
        "httpMethod": http_method,
        "authorizationType": auth_type,
        "apiKeyRequired": False,
    }
    if authorizer_id:
        method_kwargs["authorizerId"] = authorizer_id

    try:
        apigw.put_method(**method_kwargs)
    except apigw.exceptions.ConflictException:
        patch_ops = [
            {"op": "replace", "path": "/authorizationType", "value": auth_type},
            {"op": "replace", "path": "/apiKeyRequired", "value": "false"},
        ]
        if authorizer_id:
            patch_ops.append(
                {"op": "replace", "path": "/authorizerId", "value": authorizer_id}
            )
        apigw.update_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=http_method,
            patchOperations=patch_ops,
        )

    apigw.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=http_method,
        type="AWS_PROXY",
        integrationHttpMethod="POST",
        uri=lambda_uri,
    )
    add_cors_options(apigw, api_id, resource_id)


def _ensure_resource(apigw, api_id: str, root_id: str, path_part: str, paths: dict) -> str:
    path = f"/{path_part}"
    if path in paths:
        return paths[path]

    resource_id = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart=path_part,
    )["id"]
    paths[path] = resource_id
    print(f"Created resource {path}")
    return resource_id


def add_file_routes(api_id: str, lambda_arn: str) -> dict:
    apigw = boto3.client("apigateway", region_name=REGION)
    account = _account_id()
    lambda_uri = _lambda_uri(lambda_arn)
    authorizer_id = _ensure_cognito_authorizer(apigw, api_id)

    resources = apigw.get_resources(restApiId=api_id)["items"]
    paths = {r["path"]: r["id"] for r in resources}
    root_id = paths["/"]

    upload_resource = _ensure_resource(apigw, api_id, root_id, "upload-url", paths)
    files_resource = _ensure_resource(apigw, api_id, root_id, "files", paths)

    add_lambda_route(apigw, api_id, upload_resource, "POST", lambda_uri, authorizer_id)
    add_lambda_route(apigw, api_id, files_resource, "GET", lambda_uri, authorizer_id)
    print("Registered POST /upload-url and GET /files")

    lambda_client = boto3.client("lambda", region_name=REGION)
    for path in ["upload-url", "files"]:
        source_arn = f"arn:aws:execute-api:{REGION}:{account}:{api_id}/*/*/{path}"
        try:
            lambda_client.add_permission(
                FunctionName=LAMBDA_FUNCTION_NAME,
                StatementId=f"apigateway-{path.replace('/', '-')}",
                Action="lambda:InvokeFunction",
                Principal="apigateway.amazonaws.com",
                SourceArn=source_arn,
            )
        except lambda_client.exceptions.ResourceConflictException:
            print(f"Lambda permission already exists for /{path}")

    deployment = apigw.create_deployment(
        restApiId=api_id,
        stageName=STAGE_NAME,
        description="File upload routes",
    )
    print(f"Deployed stage {STAGE_NAME}: {deployment['id']}")

    invoke_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
    result = {
        "api_id": api_id,
        "invoke_url": invoke_url,
        "upload_url": f"{invoke_url}/upload-url",
        "files_url": f"{invoke_url}/files",
    }
    print(json.dumps(result, indent=2))
    return result


def create_api(lambda_arn: str) -> dict:
    apigw = boto3.client("apigateway", region_name=REGION)
    account = _account_id()

    api = apigw.create_rest_api(
        name=API_NAME,
        description="Spend Analytics Agent API",
        endpointConfiguration={"types": ["REGIONAL"]},
        tags={"Project": "SpendAgent", "Version": "v2"},
    )
    api_id = api["id"]
    print(f"Created REST API: {api_id}")

    resources = apigw.get_resources(restApiId=api_id)
    root_id = next(r["id"] for r in resources["items"] if r["path"] == "/")
    paths = {r["path"]: r["id"] for r in resources["items"]}

    chat_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="chat",
    )["id"]
    paths["/chat"] = chat_resource

    chat_job_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=chat_resource,
        pathPart="{job_id}",
    )["id"]
    paths["/chat/{job_id}"] = chat_job_resource

    dashboard_resource = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="dashboard",
    )["id"]
    paths["/dashboard"] = dashboard_resource

    upload_resource = _ensure_resource(apigw, api_id, root_id, "upload-url", paths)
    files_resource = _ensure_resource(apigw, api_id, root_id, "files", paths)

    lambda_uri = _lambda_uri(lambda_arn)
    authorizer_id = _ensure_cognito_authorizer(apigw, api_id)

    routes = [
        (chat_resource, "POST"),
        (chat_job_resource, "GET"),
        (dashboard_resource, "GET"),
        (upload_resource, "POST"),
        (files_resource, "GET"),
    ]
    for resource_id, method in routes:
        add_lambda_route(apigw, api_id, resource_id, method, lambda_uri, authorizer_id)

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
    for path in ["chat", "chat/*", "dashboard", "upload-url", "files"]:
        source_arn = (
            f"arn:aws:execute-api:{REGION}:{account}:{api_id}/*/*/{path}"
        )
        try:
            lambda_client.add_permission(
                FunctionName=LAMBDA_FUNCTION_NAME,
                StatementId=f"apigateway-{path.replace('/', '-')}",
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
        "upload_url": f"{invoke_url}/upload-url",
        "files_url": f"{invoke_url}/files",
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--add-file-routes",
        action="store_true",
        help="Add upload-url and files routes to an existing API (requires API_GATEWAY_ID)",
    )
    args = parser.parse_args()

    time.sleep(0)
    lambda_arn = resolve_lambda_arn()

    if args.add_file_routes:
        if not API_ID:
            raise SystemExit("API_GATEWAY_ID is required for --add-file-routes")
        add_file_routes(API_ID, lambda_arn)
    else:
        create_api(lambda_arn)
