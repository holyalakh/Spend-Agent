from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

WRITE_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"}


def read_only_sql_guard(event: BeforeToolCallEvent):
    """Block any SQL write operations before they reach DuckDB."""
    tool_name = event.tool_use.get("name", "") if hasattr(event, "tool_use") else ""
    if not tool_name and hasattr(event, "tool"):
        tool_name = getattr(event.tool, "tool_name", "")

    if tool_name != "run_analysis_query":
        return

    tool_input = (
        event.tool_use.get("input", {})
        if hasattr(event, "tool_use")
        else getattr(event.tool, "tool_input", {})
    )
    sql = (tool_input.get("sql") or "").upper()
    for keyword in WRITE_KEYWORDS:
        if keyword in sql:
            raise ValueError(
                f"Write operation '{keyword}' is not permitted. "
                "This agent is read-only."
            )


class ReadOnlySqlHooks(HookProvider):
    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, read_only_sql_guard)
