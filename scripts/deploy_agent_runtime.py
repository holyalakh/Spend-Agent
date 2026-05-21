#!/usr/bin/env python3
"""
Build and deploy spendagentv1 to AgentCore Runtime (absolute imports, env vars).

Usage (from repo root):
  set -a && source deploy/aws.env && set +a
  python scripts/deploy_agent_runtime.py
"""

import json
import os
import shutil
import subprocess
import sys
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

SOURCE_FILES = [
    "main.py",
    "hooks.py",
    "memory.py",
    "session_store.py",
    "requirements.txt",
]
SOURCE_DIRS = ["tools"]


def _assert_no_relative_imports():
    bad = []
    check_paths = [AGENT_DIR / name for name in SOURCE_FILES]
    check_paths += [AGENT_DIR / "tools" / p.name for p in (AGENT_DIR / "tools").glob("*.py")]
    for path in check_paths:
        text = path.read_text()
        if "from ." in text or "import ." in text:
            bad.append(str(path.relative_to(AGENT_DIR)))
    if bad:
        raise SystemExit(f"Relative imports remain in: {bad}")


def _build_zip() -> Path:
    work = Path(tempfile.mkdtemp(prefix="spend-agent-deploy-"))
    try:
        for name in SOURCE_FILES:
            shutil.copy2(AGENT_DIR / name, work / name)
        for dirname in SOURCE_DIRS:
            shutil.copytree(AGENT_DIR / dirname, work / dirname)

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-t", str(work), "-q"],
            cwd=work,
            check=True,
        )

        zip_path = Path(tempfile.mktemp(suffix=".zip"))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(work):
                for file in files:
                    full = Path(root) / file
                    zf.write(full, full.relative_to(work).as_posix())
        return zip_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _deploy(zip_path: Path) -> dict:
    prefix = f"spend-agent-deploy/spend-agent-{int(time.time())}.zip"
    boto3.client("s3", region_name=REGION).upload_file(
        str(zip_path), BUCKET, prefix
    )

    env_vars = {
        "S3_BUCKET_NAME": os.environ["S3_BUCKET_NAME"],
        "AGENTCORE_MEMORY_ID": os.environ["AGENTCORE_MEMORY_ID"],
        "BEDROCK_GUARDRAIL_ID": os.environ["BEDROCK_GUARDRAIL_ID"],
        "BEDROCK_GUARDRAIL_VERSION": os.environ["BEDROCK_GUARDRAIL_VERSION"],
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
    return {"s3_key": prefix, "response": resp}


def main():
    _assert_no_relative_imports()
    print("Building deployment package...")
    zip_path = _build_zip()
    try:
        print(f"Package size: {zip_path.stat().st_size / 1_048_576:.1f} MB")
        result = _deploy(zip_path)
        print(json.dumps(result, indent=2, default=str))
        print("Waiting for runtime to become READY...")
        client = boto3.client("bedrock-agentcore-control", region_name=REGION)
        for _ in range(40):
            status = client.get_agent_runtime(agentRuntimeId=RUNTIME_ID)["status"]
            print(f"  status={status}")
            if status == "READY":
                break
            time.sleep(15)
        else:
            print("Warning: runtime did not reach READY within timeout")
    finally:
        zip_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
