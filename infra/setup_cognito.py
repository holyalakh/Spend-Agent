"""
Provision Cognito User Pool and attach JWT authorizer to API Gateway.

Replaces API key auth with Cognito JWT auth on all routes except OPTIONS.

Environment variables:
  AWS_REGION              (default: ap-south-1)
  AWS_ACCOUNT_ID          (default: 387957186026)
  API_GATEWAY_ID          (required, e.g. ee5b0fv5kc)
  STAGE_NAME              (default: prod)
  USER_POOL_NAME          (default: SpendAgentUserPool)
  APP_CLIENT_NAME         (default: SpendAgentWebClient)
  AUTHORIZER_NAME         (default: SpendAgentCognitoAuthorizer)

Usage:
  set -a && source deploy/aws.env && set +a
  python infra/setup_cognito.py
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "387957186026")
API_ID = os.environ.get("API_GATEWAY_ID")
STAGE_NAME = os.environ.get("STAGE_NAME", "prod")
USER_POOL_NAME = os.environ.get("USER_POOL_NAME", "SpendAgentUserPool")
APP_CLIENT_NAME = os.environ.get("APP_CLIENT_NAME", "SpendAgentWebClient")
AUTHORIZER_NAME = os.environ.get("AUTHORIZER_NAME", "SpendAgentCognitoAuthorizer")

RESOURCE_TAGS = {"Project": "SpendAgent", "Version": "v2"}

CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
}


def _find_user_pool(cognito, name: str) -> str | None:
    token = None
    while True:
        kwargs = {"MaxResults": 60}
        if token:
            kwargs["NextToken"] = token
        response = cognito.list_user_pools(**kwargs)
        for pool in response.get("UserPools", []):
            if pool["Name"] == name:
                return pool["Id"]
        token = response.get("NextToken")
        if not token:
            return None


def _ensure_user_pool(cognito) -> str:
    pool_id = _find_user_pool(cognito, USER_POOL_NAME)
    if pool_id:
        print(f"Using existing user pool: {USER_POOL_NAME} ({pool_id})")
        return pool_id

    response = cognito.create_user_pool(
        PoolName=USER_POOL_NAME,
        Policies={
            "PasswordPolicy": {
                "MinimumLength": 8,
                "RequireNumbers": True,
                "RequireSymbols": True,
                "RequireUppercase": False,
                "RequireLowercase": False,
            }
        },
        AutoVerifiedAttributes=["email"],
        UsernameAttributes=["email"],
        UserPoolTags=RESOURCE_TAGS,
    )
    pool_id = response["UserPool"]["Id"]
    print(f"Created user pool: {USER_POOL_NAME} ({pool_id})")
    return pool_id


def _ensure_app_client(cognito, pool_id: str) -> str:
    clients = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)
    existing = next(
        (c for c in clients.get("UserPoolClients", []) if c["ClientName"] == APP_CLIENT_NAME),
        None,
    )
    if existing:
        client_id = existing["ClientId"]
        print(f"Using existing app client: {APP_CLIENT_NAME} ({client_id})")
        return client_id

    response = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=APP_CLIENT_NAME,
        GenerateSecret=False,
        ExplicitAuthFlows=[
            "ALLOW_USER_SRP_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
        ],
    )
    client_id = response["UserPoolClient"]["ClientId"]
    print(f"Created app client: {APP_CLIENT_NAME} ({client_id})")
    return client_id


def _add_cors_options(apigw, resource_id: str):
    """OPTIONS preflight without Cognito auth."""
    try:
        apigw.put_method(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            authorizationType="NONE",
            apiKeyRequired=False,
        )
    except apigw.exceptions.ConflictException:
        apigw.update_method(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            patchOperations=[
                {"op": "replace", "path": "/authorizationType", "value": "NONE"},
                {"op": "replace", "path": "/apiKeyRequired", "value": "false"},
            ],
        )

    try:
        apigw.put_integration(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            type="MOCK",
            requestTemplates={"application/json": '{"statusCode": 200}'},
        )
    except apigw.exceptions.ConflictException:
        pass

    try:
        apigw.put_method_response(
            restApiId=API_ID,
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
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            statusCode="200",
            responseParameters=CORS_HEADERS,
        )
    except apigw.exceptions.ConflictException:
        pass


def _ensure_authorizer(apigw, pool_id: str) -> str:
    pool_arn = f"arn:aws:cognito-idp:{REGION}:{ACCOUNT_ID}:userpool/{pool_id}"
    authorizers = apigw.get_authorizers(restApiId=API_ID)["items"]
    existing = next((a for a in authorizers if a["name"] == AUTHORIZER_NAME), None)
    if existing:
        authorizer_id = existing["id"]
        print(f"Using existing authorizer: {AUTHORIZER_NAME} ({authorizer_id})")
        return authorizer_id

    authorizer_id = apigw.create_authorizer(
        restApiId=API_ID,
        name=AUTHORIZER_NAME,
        type="COGNITO_USER_POOLS",
        providerARNs=[pool_arn],
        identitySource="method.request.header.Authorization",
    )["id"]
    print(f"Created authorizer: {AUTHORIZER_NAME} ({authorizer_id})")
    return authorizer_id


def _attach_cognito_auth(apigw, authorizer_id: str):
    resources = apigw.get_resources(restApiId=API_ID)["items"]
    paths = {r["path"]: r["id"] for r in resources}

    method_updates = [
        (paths["/chat"], "POST"),
        (paths["/dashboard"], "GET"),
    ]
    if "/chat/{job_id}" in paths:
        method_updates.append((paths["/chat/{job_id}"], "GET"))
    if "/upload-url" in paths:
        method_updates.append((paths["/upload-url"], "POST"))
    if "/files" in paths:
        method_updates.append((paths["/files"], "GET"))

    for resource_id, http_method in method_updates:
        apigw.update_method(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod=http_method,
            patchOperations=[
                {"op": "replace", "path": "/authorizationType", "value": "COGNITO_USER_POOLS"},
                {"op": "replace", "path": "/authorizerId", "value": authorizer_id},
                {"op": "replace", "path": "/apiKeyRequired", "value": "false"},
            ],
        )
        _add_cors_options(apigw, resource_id)
        print(f"Attached Cognito auth: {http_method} on resource {resource_id}")


def setup_cognito() -> dict:
    if not API_ID:
        raise ValueError("API_GATEWAY_ID is required")

    cognito = boto3.client("cognito-idp", region_name=REGION)
    apigw = boto3.client("apigateway", region_name=REGION)

    pool_id = _ensure_user_pool(cognito)
    client_id = _ensure_app_client(cognito, pool_id)
    authorizer_id = _ensure_authorizer(apigw, pool_id)
    _attach_cognito_auth(apigw, authorizer_id)

    deployment = apigw.create_deployment(
        restApiId=API_ID,
        stageName=STAGE_NAME,
        description="Cognito JWT auth enabled",
    )
    print(f"Deployed stage {STAGE_NAME}: {deployment['id']}")

    invoke_url = f"https://{API_ID}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
    result = {
        "user_pool_id": pool_id,
        "client_id": client_id,
        "authorizer_id": authorizer_id,
        "region": REGION,
        "invoke_url": invoke_url,
    }
    print(json.dumps(result, indent=2))
    print("\nAdd to .env / deploy/aws.env:")
    print(f"COGNITO_USER_POOL_ID={pool_id}")
    print(f"COGNITO_CLIENT_ID={client_id}")
    print(f"COGNITO_REGION={REGION}")
    return result


if __name__ == "__main__":
    setup_cognito()
