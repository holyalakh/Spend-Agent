from strands import tool

from session_store import SessionStore

store = SessionStore()


@tool
def get_dashboard_data(session_id: str = "default") -> dict:
    """
    Return pre-aggregated dashboard data from the loaded spend table.
    Includes: total spend, spend by category, top 10 vendors, and monthly trend.
    Call load_spend_data first.

    Args:
        session_id: Current session identifier
    """
    conn = store.get(session_id, "conn")
    if conn is None:
        return {"status": "error", "message": "No data loaded. Call load_spend_data first."}

    return _aggregate(conn)


def _aggregate(conn) -> dict:
    total = conn.execute(
        "SELECT SUM(amount), MIN(date)::varchar, MAX(date)::varchar FROM spend"
    ).fetchone()

    by_category = (
        conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM spend GROUP BY category ORDER BY total DESC
    """)
        .fetchdf()
        .to_dict(orient="records")
    )

    top_vendors = (
        conn.execute("""
        SELECT vendor_name, SUM(amount) AS total
        FROM spend GROUP BY vendor_name ORDER BY total DESC LIMIT 10
    """)
        .fetchdf()
        .to_dict(orient="records")
    )

    by_month = (
        conn.execute("""
        SELECT strftime(date, '%Y-%m') AS month, SUM(amount) AS total
        FROM spend GROUP BY month ORDER BY month
    """)
        .fetchdf()
        .to_dict(orient="records")
    )

    return {
        "status": "ok",
        "total_spend": total[0],
        "period": {"from": total[1], "to": total[2]},
        "by_category": by_category,
        "top_vendors": top_vendors,
        "by_month": by_month,
    }
