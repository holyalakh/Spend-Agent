"""
Switch an existing API Gateway REST API from IAM auth to API key auth.

Environment variables:
  AWS_REGION       (default: ap-south-1)
  API_GATEWAY_ID   (required, e.g. ee5b0fv5kc)
  STAGE_NAME       (default: prod)
  API_KEY_NAME     (default: SpendAgentFrontendKey)
  USAGE_PLAN_NAME  (default: SpendAgentUsagePlan)

Usage:
  source deploy/aws.env
  python enable_api_key_auth.py
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
API_ID = os.environ.get("API_GATEWAY_ID")
STAGE_NAME = os.environ.get("STAGE_NAME", "prod")
API_KEY_NAME = os.environ.get("API_KEY_NAME", "SpendAgentFrontendKey")
USAGE_PLAN_NAME = os.environ.get("USAGE_PLAN_NAME", "SpendAgentUsagePlan")

CORS_HEADERS = {
    "method.response.header.Access-Control-Allow-Origin": "'*'",
    "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
    "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
}


def _add_cors_options(apigw, api_id: str, resource_id: str):
    """OPTIONS preflight without API key."""
    try:
        apigw.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod="OPTIONS",
            authorizationType="NONE",
            apiKeyRequired=False,
        )
    except apigw.exceptions.ConflictException:
        apigw.delete_method(
            restApiId=api_id, resourceId=resource_id, httpMethod="OPTIONS"
        )
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
        responseParameters=CORS_HEADERS,
    )


def enable_api_key_auth() -> dict:
    if not API_ID:
        raise ValueError("API_GATEWAY_ID is required")

    apigw = boto3.client("apigateway", region_name=REGION)

    resources = apigw.get_resources(restApiId=API_ID)["items"]
    paths = {r["path"]: r["id"] for r in resources}

    method_updates = [
        (paths["/chat"], "POST"),
        (paths["/dashboard"], "GET"),
    ]
    if "/chat/{job_id}" in paths:
        method_updates.append((paths["/chat/{job_id}"], "GET"))

    for resource_id, http_method in method_updates:
        apigw.update_method(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod=http_method,
            patchOperations=[
                {"op": "replace", "path": "/authorizationType", "value": "NONE"},
                {"op": "replace", "path": "/apiKeyRequired", "value": "true"},
            ],
        )
        _add_cors_options(apigw, API_ID, resource_id)

    deployment = apigw.create_deployment(
        restApiId=API_ID,
        stageName=STAGE_NAME,
        description="API key auth enabled",
    )
    print(f"Deployed stage {STAGE_NAME}: {deployment['id']}")

    usage_plans = apigw.get_usage_plans()["items"]
    usage_plan = next((p for p in usage_plans if p["name"] == USAGE_PLAN_NAME), None)

    if usage_plan:
        usage_plan_id = usage_plan["id"]
        print(f"Using existing usage plan: {usage_plan_id}")
    else:
        usage_plan_id = apigw.create_usage_plan(
            name=USAGE_PLAN_NAME,
            description="Spend Analytics Agent frontend",
            apiStages=[{"apiId": API_ID, "stage": STAGE_NAME}],
            throttle={"rateLimit": 100, "burstLimit": 200},
            quota={"limit": 100000, "period": "MONTH"},
        )["id"]
        print(f"Created usage plan: {usage_plan_id}")

    keys = apigw.get_api_keys(nameQuery=API_KEY_NAME, includeValues=True)["items"]
    api_key = next((k for k in keys if k["name"] == API_KEY_NAME), None)

    if api_key:
        api_key_id = api_key["id"]
        api_key_value = api_key.get("value")
        print(f"Using existing API key: {api_key_id}")
    else:
        created = apigw.create_api_key(
            name=API_KEY_NAME,
            description="Frontend key for Spend Analytics Agent",
            enabled=True,
        )
        api_key_id = created["id"]
        api_key_value = created["value"]
        print(f"Created API key: {api_key_id}")

    existing_links = apigw.get_usage_plan_keys(usagePlanId=usage_plan_id)["items"]
    if not any(link["id"] == api_key_id for link in existing_links):
        apigw.create_usage_plan_key(
            usagePlanId=usage_plan_id,
            keyId=api_key_id,
            keyType="API_KEY",
        )

    invoke_url = f"https://{API_ID}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}"
    result = {
        "api_id": API_ID,
        "invoke_url": invoke_url,
        "api_key_id": api_key_id,
        "api_key_value": api_key_value,
        "usage_plan_id": usage_plan_id,
    }
    print(json.dumps({k: v for k, v in result.items() if k != "api_key_value"}, indent=2))
    print(f"\nAPI_KEY_VALUE={api_key_value}")
    print("Add to frontend/.env: VITE_API_KEY=<value above>")
    return result


if __name__ == "__main__":
    enable_api_key_auth()
