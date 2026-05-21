"""
Add S3 permissions to the SpendAgentAdapter Lambda execution role.

Environment variables:
  AWS_REGION              (default: ap-south-1)
  LAMBDA_FUNCTION_NAME    (default: SpendAgentAdapter)
  S3_BUCKET_NAME          (default: spend-data-q)

Usage:
  set -a && source deploy/aws.env && set +a
  python infra/update_lambda_s3_policy.py
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
LAMBDA_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "SpendAgentAdapter")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "spend-data-q")
POLICY_NAME = "SpendAgentAdapterS3Policy"


def s3_policy_document(bucket: str) -> dict:
    bucket_arn = f"arn:aws:s3:::{bucket}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ListUserUploads",
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": bucket_arn,
                "Condition": {
                    "StringLike": {"s3:prefix": ["uploads/*", "spend-data/raw/*"]}
                },
            },
            {
                "Sid": "ReadWriteObjects",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject"],
                "Resource": f"{bucket_arn}/*",
            },
        ],
    }


def update_lambda_s3_policy() -> dict:
    lambda_client = boto3.client("lambda", region_name=REGION)
    iam = boto3.client("iam", region_name=REGION)

    cfg = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    role_name = cfg["Role"].split("/")[-1]

    policy = s3_policy_document(S3_BUCKET)
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(policy),
    )
    print(f"Attached {POLICY_NAME} to role {role_name}")

    result = {"role_name": role_name, "policy_name": POLICY_NAME, "bucket": S3_BUCKET}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    update_lambda_s3_policy()
