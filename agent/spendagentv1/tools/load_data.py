import io
import os

import boto3
import duckdb
import pandas as pd
from strands import tool

from session_store import SessionStore

store = SessionStore()
S3_BUCKET = os.environ["S3_BUCKET_NAME"]
SHARED_PREFIX = "spend-data/raw/"

COLUMN_MAP = {
    "vendor": "vendor_name",
    "supplier": "vendor_name",
    "normalized_supplier": "vendor_name",
    "spend_category": "category",
    "category_l1": "category",
    "spend_amount": "amount",
    "total": "amount",
    "transaction_date": "date",
    "invoice_date": "date",
}


def _user_upload_prefix(user_sub: str) -> str:
    return f"uploads/{user_sub}/"


def _list_csv_keys(s3, prefix: str) -> list[str]:
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".csv") and not key.endswith("/"):
                keys.append(key)
    return sorted(keys)


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df.rename(columns=COLUMN_MAP, inplace=True)

    canonical = {"date", "vendor_name", "category", "amount"}
    missing = canonical - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. Found columns: {list(df.columns)}."
        )

    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=False, errors="coerce")
    df = df.dropna(subset=["date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def _read_s3_dataframe(s3, s3_file_key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_file_key)
    body = obj["Body"].read()

    if s3_file_key.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(body))
    else:
        df = pd.read_csv(io.BytesIO(body))
    return _normalize_dataframe(df)


def _register_dataframe(df: pd.DataFrame, session_id: str, s3_keys: list[str]):
    conn = duckdb.connect()
    conn.register("spend", df)
    store.set(session_id, "conn", conn)
    store.set(session_id, "s3_keys", s3_keys)
    if len(s3_keys) == 1:
        store.set(session_id, "s3_key", s3_keys[0])
    return conn


def _data_summary(conn) -> dict:
    summary = conn.execute("""
        SELECT
            COUNT(*) AS row_count,
            MIN(date)::varchar AS date_from,
            MAX(date)::varchar AS date_to,
            COUNT(DISTINCT category) AS category_count,
            COUNT(DISTINCT vendor_name) AS vendor_count
        FROM spend
    """).fetchone()

    categories = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT category FROM spend ORDER BY category"
        ).fetchall()
    ]

    return {
        "status": "ok",
        "row_count": summary[0],
        "date_from": summary[1],
        "date_to": summary[2],
        "category_count": summary[3],
        "vendor_count": summary[4],
        "categories": categories,
    }


def _resolve_user_sub(user_sub: str, session_id: str) -> str:
    """Prefer user_sub stored on the session (set by main.py from JWT)."""
    stored = store.get(session_id, "user_sub")
    if stored:
        return stored
    return user_sub


def _load_user_data(user_sub: str, session_id: str = "default") -> dict:
    """Load user CSV uploads, or fall back to the shared dataset."""
    resolved_sub = _resolve_user_sub(user_sub, session_id)
    if not resolved_sub:
        return {"status": "error", "message": "No user_sub available for this session."}

    s3 = boto3.client("s3")
    prefix = _user_upload_prefix(resolved_sub)
    print(
        f"load_user_data: bucket={S3_BUCKET} prefix={prefix} "
        f"user_sub={resolved_sub} session_id={session_id}"
    )

    user_keys = _list_csv_keys(s3, prefix)
    source = "user_uploads"

    if not user_keys:
        print(f"load_user_data: no files under {prefix}, falling back to {SHARED_PREFIX}")
        user_keys = _list_csv_keys(s3, SHARED_PREFIX)
        source = "shared"

    if not user_keys:
        return {
            "status": "error",
            "message": f"No CSV files found under {prefix} or {SHARED_PREFIX}.",
            "prefix_checked": prefix,
        }

    print(f"load_user_data: loading {len(user_keys)} file(s): {user_keys}")
    frames = [_read_s3_dataframe(s3, key) for key in user_keys]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    conn = _register_dataframe(df, session_id, user_keys)

    result = _data_summary(conn)
    result["source"] = source
    result["files_loaded"] = user_keys
    return result


def _load_and_register(s3_file_key: str, session_id: str = "default"):
    """Load S3 file into DuckDB; used by dashboard endpoint and load tool."""
    s3 = boto3.client("s3")
    df = _read_s3_dataframe(s3, s3_file_key)
    return _register_dataframe(df, session_id, [s3_file_key])


@tool
def load_user_data(session_id: str = "default", user_sub: str = "") -> dict:
    """
    Load the authenticated user's uploaded CSV files from S3 into DuckDB.
    Lists uploads/{user_sub}/ on S3; falls back to spend-data/raw/ when empty.
    user_sub is resolved from the session if omitted.

    Args:
        session_id: Current session identifier
        user_sub: Cognito user sub (optional — resolved from session when omitted)
    """
    try:
        return _load_user_data(user_sub, session_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@tool
def load_spend_data(s3_file_key: str, session_id: str = "default") -> dict:
    """
    Load a CSV or Excel spend file from S3 into an in-memory DuckDB table called 'spend'.
    Returns a summary: row count, date range, unique categories, and unique vendors.
    Call this before running any analysis queries.

    Args:
        s3_file_key: S3 key of the file, e.g. 'spend-data/raw/spend_2024_q1.xlsx'
        session_id: Current session identifier
    """
    try:
        conn = _load_and_register(s3_file_key, session_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return _data_summary(conn)
