import io
import os

import boto3
import duckdb
import pandas as pd
from strands import tool

from session_store import SessionStore

store = SessionStore()
S3_BUCKET = os.environ["S3_BUCKET_NAME"]

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


def _load_and_register(s3_file_key: str, session_id: str = "default"):
    """Load S3 file into DuckDB; used by dashboard endpoint and load tool."""
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_file_key)
    body = obj["Body"].read()

    if s3_file_key.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(body))
    else:
        df = pd.read_csv(io.BytesIO(body))

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

    conn = duckdb.connect()
    conn.register("spend", df)
    store.set(session_id, "conn", conn)
    store.set(session_id, "s3_key", s3_file_key)
    return conn


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
