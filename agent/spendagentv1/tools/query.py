import os

from strands import tool

from session_store import SessionStore

store = SessionStore()
MAX_ROWS = int(os.environ.get("MAX_ROWS_RETURNED", 500))


@tool
def run_analysis_query(sql: str, session_id: str = "default") -> dict:
    """
    Execute a SQL query against the in-memory DuckDB 'spend' table and return results.
    Use this to answer questions about spend by category, vendor, time period, etc.
    Always call load_spend_data first if no data has been loaded yet.

    Args:
        sql: A valid DuckDB SQL query against the 'spend' table
        session_id: Current session identifier
    """
    conn = store.get(session_id, "conn")
    if conn is None:
        return {
            "status": "error",
            "message": "No spend data loaded. Call load_spend_data first.",
        }

    try:
        result = conn.execute(sql).fetchdf()
        rows = result.head(MAX_ROWS).to_dict(orient="records")
        return {
            "status": "ok",
            "row_count": len(rows),
            "columns": list(result.columns),
            "rows": rows,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
