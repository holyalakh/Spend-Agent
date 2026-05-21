#!/usr/bin/env python3
"""Patch deployed AgentCore zip with fixed source files (no pip reinstall)."""

import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agent" / "spendagentv1"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
RUNTIME_ID = os.environ.get("AGENTCORE_RUNTIME_ID", "spendagentv1_MyAgent-TeCbnqAkL9")
ROLE_ARN = os.environ.get(
    "AGENTCORE_EXECUTION_ROLE_ARN",
    "arn:aws:iam::387957186026:role/AgentCore-spendagentv1-de-ApplicationAgentMyAgentRu-kiEITq1KlBLD",
)
BUCKET = os.environ["S3_BUCKET_NAME"]

PATCH_FILES = [
    "main.py",
    "hooks.py",
    "memory.py",
    "session_store.py",
    "tools/load_data.py",
    "tools/query.py",
    "tools/dashboard.py",
    "tools/__init__.py",
]

def _source_artifact(s3):
    """Use the currently deployed runtime artifact as the patch base."""
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    artifact = client.get_agent_runtime(agentRuntimeId=RUNTIME_ID)["agentRuntimeArtifact"]
    code = artifact["codeConfiguration"]["code"]
    return code["s3"]["bucket"], code["s3"]["prefix"]


def main():
    s3 = boto3.client("s3", region_name=REGION)
    work = Path(tempfile.mkdtemp(prefix="patch-agent-"))
    src_zip = work / "source.zip"
    out_zip = work / "patched.zip"

    try:
        src_bucket, src_prefix = _source_artifact(s3)
        print(f"Downloading current runtime artifact s3://{src_bucket}/{src_prefix} ...")
        s3.download_file(src_bucket, src_prefix, str(src_zip))

        extract_dir = work / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(src_zip, "r") as zf:
            zf.extractall(extract_dir)

        print("Patching source files...")
        for rel in PATCH_FILES:
            src = AGENT_DIR / rel
            dst = extract_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            head = dst.read_text().splitlines()[:12]
            if any("from ." in line for line in head):
                raise SystemExit(f"Relative import still in {rel}")

        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(extract_dir):
                for name in files:
                    full = Path(root) / name
                    zf.write(full, full.relative_to(extract_dir).as_posix())

        prefix = f"spend-agent-deploy/patched-{int(time.time())}.zip"
        print(f"Uploading to s3://{BUCKET}/{prefix} ...")
        s3.upload_file(str(out_zip), BUCKET, prefix)

        env_vars = {
            "S3_BUCKET_NAME": os.environ["S3_BUCKET_NAME"],
            "AGENTCORE_MEMORY_ID": os.environ["AGENTCORE_MEMORY_ID"],
            "BEDROCK_GUARDRAIL_ID": os.environ["BEDROCK_GUARDRAIL_ID"],
            "BEDROCK_GUARDRAIL_VERSION": os.environ["BEDROCK_GUARDRAIL_VERSION"],
            "BEDROCK_MODEL_ID": os.environ.get(
                "BEDROCK_MODEL_ID",
                "arn:aws:bedrock:ap-south-1:387957186026:inference-profile/global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            ),
            "MAX_ROWS_RETURNED": os.environ.get("MAX_ROWS_RETURNED", "500"),
        }

        client = boto3.client("bedrock-agentcore-control", region_name=REGION)
        resp = client.update_agent_runtime(
            agentRuntimeId=RUNTIME_ID,
            roleArn=ROLE_ARN,
            networkConfiguration={"networkMode": "PUBLIC"},
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {"s3": {"bucket": BUCKET, "prefix": prefix}},
                    "runtime": "PYTHON_3_14",
                    "entryPoint": ["opentelemetry-instrument", "main.py"],
                }
            },
            environmentVariables=env_vars,
        )
        print(json.dumps({"s3_key": prefix, "status": resp.get("status")}, indent=2))

        for i in range(40):
            status = client.get_agent_runtime(agentRuntimeId=RUNTIME_ID)["status"]
            print(f"  status={status}")
            if status == "READY":
                break
            time.sleep(10)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
