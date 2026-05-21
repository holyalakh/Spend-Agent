import json
import os
import time
import uuid

import boto3
from botocore.exceptions import ClientError

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "spend-data-q")
CHAT_JOBS_TABLE = os.environ.get("CHAT_JOBS_TABLE", "SpendAgentChatJobs")
JOB_TTL_SECONDS = int(os.environ.get("CHAT_JOB_TTL_SECONDS", "86400"))
UPLOAD_URL_EXPIRY = 300
UPLOAD_CONTENT_TYPE = "text/csv"
LAMBDA_FUNCTION_NAME = os.environ.get(
    "LAMBDA_FUNCTION_NAME", os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "SpendAgentAdapter")
)

agentcore = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)
jobs_table = dynamodb.Table(CHAT_JOBS_TABLE)


def _normalize_session_id(session_id: str) -> str:
    """AgentCore requires runtimeSessionId length >= 33."""
    if session_id and len(session_id) >= 33:
        return session_id
    return str(uuid.uuid4())


def _invoke_agentcore(payload: dict, session_id: str) -> dict:
    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=_normalize_session_id(session_id),
        payload=json.dumps(payload).encode("utf-8"),
    )

    content_type = response.get("contentType", "")
    stream = response.get("response")

    if content_type == "application/json" and stream is not None:
        chunks = []
        for chunk in stream:
            chunks.append(chunk.decode("utf-8"))
        return json.loads("".join(chunks))

    if "text/event-stream" in content_type and stream is not None:
        lines = []
        for line in stream.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    lines.append(decoded[6:])
        return {"reply": "\n".join(lines)}

    if stream is not None:
        raw = stream.read() if hasattr(stream, "read") else b"".join(stream)
        if raw:
            return json.loads(raw.decode("utf-8"))
    return {"reply": str(response)}


def _cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body),
    }


def _http_method(event) -> str:
    return event.get(
        "httpMethod",
        event.get("requestContext", {}).get("http", {}).get("method", "POST"),
    )


def _http_path(event) -> str:
    return event.get("path", event.get("rawPath", ""))


def _auth_context(event) -> tuple[str, str]:
    """Extract Cognito sub and email from API Gateway JWT authorizer claims."""
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    )
    sub = claims.get("sub", "")
    email = claims.get("email", "")
    if not sub:
        raise ValueError("Missing authenticated user (sub) in JWT claims")
    return sub, email


def _user_upload_prefix(user_sub: str) -> str:
    return f"uploads/{user_sub}/"


def _validate_csv_filename(filename: str) -> bool:
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return False
    if len(filename) > 255:
        return False
    return filename.lower().endswith(".csv")


def _assert_user_s3_key(user_sub: str, s3_key: str):
    prefix = _user_upload_prefix(user_sub)
    if not s3_key.startswith(prefix):
        raise ValueError("Access denied: S3 key is outside your upload prefix")


def _create_upload_url(user_sub: str, filename: str) -> dict:
    s3_key = f"{_user_upload_prefix(user_sub)}{filename}"
    upload_url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": s3_key,
            "ContentType": UPLOAD_CONTENT_TYPE,
        },
        ExpiresIn=UPLOAD_URL_EXPIRY,
        HttpMethod="PUT",
    )
    return {
        "upload_url": upload_url,
        "s3_key": s3_key,
        "expires_in": UPLOAD_URL_EXPIRY,
        "content_type": UPLOAD_CONTENT_TYPE,
    }


def _list_user_files(user_sub: str) -> list[dict]:
    prefix = _user_upload_prefix(user_sub)
    files = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".csv") or key.endswith("/"):
                continue
            files.append(
                {
                    "filename": key[len(prefix) :],
                    "s3_key": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )
    return files


def _create_chat_job(session_id: str, payload: dict) -> str:
    job_id = str(uuid.uuid4())
    now = int(time.time())
    jobs_table.put_item(
        Item={
            "job_id": job_id,
            "status": "pending",
            "session_id": session_id,
            "payload": json.dumps(payload),
            "created_at": now,
            "updated_at": now,
            "expires_at": now + JOB_TTL_SECONDS,
        }
    )
    lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "internal": "process_chat_job",
                "job_id": job_id,
                "session_id": session_id,
                "payload": payload,
            }
        ).encode("utf-8"),
    )
    return job_id


def _get_chat_job(job_id: str) -> dict | None:
    response = jobs_table.get_item(Key={"job_id": job_id})
    return response.get("Item")


def _process_chat_job(event: dict):
    job_id = event["job_id"]
    session_id = event["session_id"]
    payload = event["payload"]
    now = int(time.time())

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :processing, updated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":processing": "processing", ":now": now},
    )

    try:
        result = _invoke_agentcore(payload, session_id)
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :completed, #r = :result, updated_at = :now",
            ExpressionAttributeNames={"#s": "status", "#r": "result"},
            ExpressionAttributeValues={
                ":completed": "completed",
                ":result": json.dumps(result),
                ":now": int(time.time()),
            },
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = "failed"
        error_message = str(e)
        if code in ("AccessDeniedException", "AccessDenied"):
            error_message = f"AgentCore access denied: {e}"
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :failed, #e = :error, updated_at = :now",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":failed": status,
                ":error": error_message,
                ":now": int(time.time()),
            },
        )
    except Exception as e:
        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :failed, #e = :error, updated_at = :now",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":failed": "failed",
                ":error": str(e),
                ":now": int(time.time()),
            },
        )


def _poll_chat_job(job_id: str, session_id: str):
    job = _get_chat_job(job_id)
    if not job:
        return _response(404, {"error": "Job not found", "job_id": job_id})

    if job.get("session_id") != session_id:
        return _response(403, {"error": "Forbidden", "job_id": job_id})

    status = job.get("status", "pending")
    body = {"job_id": job_id, "status": status}

    if status == "completed":
        body["result"] = json.loads(job.get("result", "{}"))
        return _response(200, body)

    if status == "failed":
        body["error"] = job.get("error", "Unknown error")
        return _response(500, body)

    return _response(202, body)


def _handle_http(event, context):
    method = _http_method(event)
    path = _http_path(event)

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")

    try:
        user_sub, user_email = _auth_context(event)
    except ValueError as e:
        return _response(401, {"error": str(e)})

    if method == "GET" and job_id:
        return _poll_chat_job(job_id, user_sub)

    if method == "GET" and "dashboard" in path:
        params = event.get("queryStringParameters") or {}
        s3_file_key = params.get("s3_file_key", "")
        if not s3_file_key:
            return _response(400, {"error": "Missing query parameter: s3_file_key"})
        try:
            _assert_user_s3_key(user_sub, s3_file_key)
        except ValueError as e:
            return _response(403, {"error": str(e)})
        payload = {
            "action": "dashboard",
            "session_id": user_sub,
            "user_sub": user_sub,
            "user_email": user_email,
            "s3_file_key": s3_file_key,
        }
        result = _invoke_agentcore(payload, user_sub)
        return _response(200, result)

    if method == "GET" and path.rstrip("/").endswith("/files"):
        return _response(200, {"files": _list_user_files(user_sub)})

    if method == "POST" and path.rstrip("/").endswith("/upload-url"):
        body = json.loads(event.get("body") or "{}")
        filename = body.get("filename", "")
        if not _validate_csv_filename(filename):
            return _response(400, {"error": "Only CSV files with a valid filename are supported"})
        return _response(200, _create_upload_url(user_sub, filename))

    if method == "POST" and path.rstrip("/").endswith("/chat"):
        body = json.loads(event.get("body") or "{}")
        if "message" not in body:
            return _response(400, {"error": "Missing required field: message"})

        s3_file_key = body.get("s3_file_key", "")
        if s3_file_key:
            try:
                _assert_user_s3_key(user_sub, s3_file_key)
            except ValueError as e:
                return _response(403, {"error": str(e)})

        payload = {
            "session_id": user_sub,
            "user_sub": user_sub,
            "user_email": user_email,
            "message": body["message"],
            "s3_file_key": s3_file_key,
        }
        new_job_id = _create_chat_job(user_sub, payload)
        return _response(202, {"job_id": new_job_id, "status": "pending"})

    return _response(404, {"error": f"Not found: {method} {path}"})


def handler(event, context):
    """
    API Gateway entry (sync) or async worker (internal process_chat_job).
    POST /chat returns job_id; GET /chat/{job_id} polls for result.
    """
    if event.get("internal") == "process_chat_job":
        _process_chat_job(event)
        return {"statusCode": 200}

    try:
        return _handle_http(event, context)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("AccessDeniedException", "AccessDenied"):
            return _response(403, {"error": f"AgentCore access denied: {e}"})
        if code == "RuntimeClientError":
            return _response(503, {"error": str(e)})
        raise
    except Exception as e:
        return _response(500, {"error": str(e)})
