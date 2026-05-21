"""
Configure S3 bucket CORS for browser PUT uploads via pre-signed URLs.

Environment variables:
  AWS_REGION        (default: ap-south-1)
  S3_BUCKET_NAME    (default: spend-data-q)
  CORS_ORIGINS      (optional comma-separated extra origins)

Usage:
  set -a && source deploy/aws.env && set +a
  python infra/setup_s3_cors.py
"""

import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
BUCKET = os.environ.get("S3_BUCKET_NAME", "spend-data-q")

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
]

extra_origins = os.environ.get("CORS_ORIGINS", "")
if extra_origins:
    DEFAULT_ORIGINS.extend(origin.strip() for origin in extra_origins.split(",") if origin.strip())

# S3 CORS does not support wildcard origins with credentials; list explicit origins.
ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_ORIGINS))

CORS_CONFIGURATION = {
    "CORSRules": [
        {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedOrigins": ALLOWED_ORIGINS,
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3000,
        }
    ]
}


def main():
    s3 = boto3.client("s3", region_name=REGION)
    s3.put_bucket_cors(Bucket=BUCKET, CORSConfiguration=CORS_CONFIGURATION)
    print(f"CORS configured on {BUCKET}")
    print(f"  AllowedOrigins: {ALLOWED_ORIGINS}")


if __name__ == "__main__":
    main()
