"""
Create and configure AWS WAF WebACL for the Spend Analytics Agent API.

Usage:
  export AWS_REGION=ap-south-1
  python waf.py

Requires: boto3, appropriate IAM permissions for wafv2:CreateWebACL
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "ap-south-1")
WEB_ACL_NAME = os.environ.get("WAF_WEB_ACL_NAME", "SpendAgentWAF")


def create_web_acl():
    client = boto3.client("wafv2", region_name=REGION)

    response = client.create_web_acl(
        Name=WEB_ACL_NAME,
        Scope="REGIONAL",
        DefaultAction={"Allow": {}},
        Rules=[
            {
                "Name": "AWSManagedRulesCommonRuleSet",
                "Priority": 1,
                "OverrideAction": {"None": {}},
                "Statement": {
                    "ManagedRuleGroupStatement": {
                        "VendorName": "AWS",
                        "Name": "AWSManagedRulesCommonRuleSet",
                    }
                },
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "CommonRuleSet",
                },
            },
            {
                "Name": "RateLimit",
                "Priority": 2,
                "Action": {"Block": {}},
                "Statement": {
                    "RateBasedStatement": {
                        "Limit": 100,
                        "AggregateKeyType": "IP",
                    }
                },
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "RateLimit",
                },
            },
        ],
        VisibilityConfig={
            "SampledRequestsEnabled": True,
            "CloudWatchMetricsEnabled": True,
            "MetricName": WEB_ACL_NAME,
        },
    )

    arn = response["Summary"]["ARN"]
    print(f"Created WAF WebACL: {WEB_ACL_NAME}")
    print(f"WAF WebACL ARN: {arn}")
    return arn


if __name__ == "__main__":
    arn = create_web_acl()
    print(json.dumps({"web_acl_arn": arn}))
