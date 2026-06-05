"""Agent harness: tool registry, verification, step limits, and structured logging."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

import boto3
import pandas as pd
from strands import Agent, tool

from hooks import ReadOnlySqlHooks
from session_store import SessionStore
from tools.dashboard import get_dashboard_data as _get_dashboard_data_tool
from tools.load_data import (
    SHARED_PREFIX,
    S3_BUCKET,
    _data_summary,
    _list_csv_keys,
    _read_s3_dataframe,
    _register_dataframe,
    load_spend_data as _load_spend_data_tool,
    load_user_data as _load_user_data_tool,
)
from tools.query import run_analysis_query as _run_analysis_query_tool

store = SessionStore()
MAX_HARNESS_LOG_ENTRIES = 50
DEFAULT_MAX_TOOL_CALLS = 15


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation of value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _invoke_tool(tool_fn: Any, **kwargs: Any) -> Any:
    """Call a Strands tool or plain callable."""
    if hasattr(tool_fn, "invoke"):
        return tool_fn.invoke(**kwargs)
    return tool_fn(**kwargs)


def _normalize_tool_result(result: Any) -> Any:
    """Extract plain data from Strands ToolResult wrappers."""
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list) and content:
            first = content[0]
            if hasattr(first, "text"):
                text = first.text
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
                return text
            return first
        return content
    if hasattr(result, "text"):
        text = result.text
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text
    return result


def _verify_load_result(result: Any, session_id: str) -> tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "output is not a dict"
    if result.get("status") != "ok":
        return False, result.get("message", "status is not ok")
    if result.get("row_count", 0) <= 0:
        return False, "row_count must be greater than 0"
    if store.get(session_id, "conn") is None:
        return False, "DuckDB connection missing from session store"
    return True, ""


def _verify_query_result(result: Any) -> tuple[bool, str]:
    if isinstance(result, str):
        return False, "result is an error string"
    if not isinstance(result, dict):
        return False, "result is not a dict"
    if not result:
        return False, "result is an empty dict"
    if result.get("status") == "error":
        return False, result.get("message", "query returned error status")
    return True, ""


def _verify_dashboard_result(result: Any, session_id: str) -> tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "output is not a dict"
    if result.get("status") != "ok":
        return False, result.get("message", "status is not ok")
    if store.get(session_id, "conn") is None:
        return False, "DuckDB connection missing from session store"
    return True, ""


def _load_shared_fallback(session_id: str) -> dict:
    """Force-load the shared spend dataset when user uploads fail verification."""
    s3 = boto3.client("s3")
    keys = _list_csv_keys(s3, SHARED_PREFIX)
    if not keys:
        return {
            "status": "error",
            "message": f"No CSV files found under {SHARED_PREFIX}.",
        }

    frames = [_read_s3_dataframe(s3, key) for key in keys]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    conn = _register_dataframe(df, session_id, keys)
    result = _data_summary(conn)
    result["source"] = "shared_fallback"
    result["files_loaded"] = keys
    return result


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "load_user_data": {
        "name": "load_user_data",
        "description": "Load authenticated user CSV uploads from S3 into DuckDB.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "user_sub": {"type": "string"},
            },
        },
        "expected_output_schema": {
            "type": "object",
            "required": ["status", "row_count"],
            "properties": {
                "status": {"type": "string", "enum": ["ok"]},
                "row_count": {"type": "integer", "minimum": 1},
            },
        },
        "verify": _verify_load_result,
        "supports_fallback": True,
    },
    "load_spend_data": {
        "name": "load_spend_data",
        "description": "Load a CSV or Excel spend file from S3 into DuckDB.",
        "input_schema": {
            "type": "object",
            "required": ["s3_file_key"],
            "properties": {
                "s3_file_key": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        "expected_output_schema": {
            "type": "object",
            "required": ["status", "row_count"],
            "properties": {
                "status": {"type": "string", "enum": ["ok"]},
                "row_count": {"type": "integer", "minimum": 1},
            },
        },
        "verify": _verify_load_result,
        "supports_fallback": False,
    },
    "run_analysis_query": {
        "name": "run_analysis_query",
        "description": "Execute SQL against the in-memory DuckDB spend table.",
        "input_schema": {
            "type": "object",
            "required": ["sql"],
            "properties": {
                "sql": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        "expected_output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "rows": {"type": "array"},
            },
        },
        "verify": _verify_query_result,
        "supports_fallback": False,
    },
    "get_dashboard_data": {
        "name": "get_dashboard_data",
        "description": "Return pre-aggregated dashboard data from loaded spend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
        },
        "expected_output_schema": {
            "type": "object",
            "required": ["status"],
            "properties": {
                "status": {"type": "string", "enum": ["ok"]},
            },
        },
        "verify": _verify_dashboard_result,
        "supports_fallback": False,
    },
    "get_harness_log": {
        "name": "get_harness_log",
        "description": "Return harness execution trace for the current session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
        },
        "expected_output_schema": {
            "type": "object",
            "required": ["status", "entries"],
        },
        "verify": None,
        "supports_fallback": False,
    },
}


class Harness:
    """Wraps tool execution with verification, retries, step limits, and logging."""

    def __init__(self, session_id: str, max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS):
        self.session_id = session_id
        self.max_tool_calls = max_tool_calls

    def _get_step_count(self) -> int:
        return int(store.get(self.session_id, "harness_step_count") or 0)

    def _increment_step_count(self) -> int:
        step = self._get_step_count() + 1
        store.set(self.session_id, "harness_step_count", step)
        return step

    def _append_log(self, entry: dict[str, Any]) -> None:
        log = list(store.get(self.session_id, "harness_log") or [])
        log.append(entry)
        store.set(self.session_id, "harness_log", log[-MAX_HARNESS_LOG_ENTRIES:])
        print(json.dumps(entry))

    def _structured_error(
        self,
        tool_name: str,
        reason: str,
        *,
        retried: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "error",
            "tool": tool_name,
            "reason": reason,
            "retried": retried,
        }
        if extra:
            payload.update(extra)
        return payload

    def _run_fallback(self, tool_name: str, inputs: dict[str, Any]) -> Any:
        if tool_name == "load_user_data":
            return _load_shared_fallback(self.session_id)
        retry_tools = {
            "load_spend_data": _load_spend_data_tool,
            "run_analysis_query": _run_analysis_query_tool,
            "get_dashboard_data": _get_dashboard_data_tool,
        }
        return _invoke_tool(retry_tools[tool_name], **inputs)

    def run_tool(self, tool_name: str, tool_fn: Callable[..., Any], **inputs: Any) -> Any:
        """Execute a registered tool with harness guarantees."""
        registry_entry = TOOL_REGISTRY.get(tool_name)
        verify_fn = registry_entry.get("verify") if registry_entry else None
        supports_fallback = bool(registry_entry and registry_entry.get("supports_fallback"))
        safe_inputs = _json_safe(inputs)

        if self._get_step_count() >= self.max_tool_calls:
            error = {
                "status": "error",
                "reason": "step_limit_exceeded",
                "steps_taken": self._get_step_count(),
            }
            self._append_log(
                {
                    "session_id": self.session_id,
                    "tool": tool_name,
                    "inputs": safe_inputs,
                    "output_valid": False,
                    "retried": False,
                    "step_number": self._get_step_count(),
                    "duration_ms": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": error["reason"],
                }
            )
            return error

        step_number = self._increment_step_count()
        started = time.perf_counter()
        retried = False
        output_valid = False
        result: Any = None

        try:
            result = _normalize_tool_result(_invoke_tool(tool_fn, **inputs))
            valid, reason = (True, "")
            if verify_fn:
                if tool_name in ("load_user_data", "load_spend_data", "get_dashboard_data"):
                    valid, reason = verify_fn(result, self.session_id)
                else:
                    valid, reason = verify_fn(result)

            if not valid:
                retried = True
                if supports_fallback:
                    result = _normalize_tool_result(self._run_fallback(tool_name, inputs))
                else:
                    result = _normalize_tool_result(_invoke_tool(tool_fn, **inputs))

                if verify_fn:
                    if tool_name in ("load_user_data", "load_spend_data", "get_dashboard_data"):
                        output_valid, reason = verify_fn(result, self.session_id)
                    else:
                        output_valid, reason = verify_fn(result)
                else:
                    output_valid = True
                    reason = ""

                if not output_valid:
                    result = self._structured_error(tool_name, reason, retried=retried)
            else:
                output_valid = True
        except Exception as exc:
            reason = str(exc)
            if not retried:
                retried = True
                try:
                    if supports_fallback:
                        result = _normalize_tool_result(self._run_fallback(tool_name, inputs))
                    else:
                        result = _normalize_tool_result(_invoke_tool(tool_fn, **inputs))
                    if verify_fn:
                        if tool_name in ("load_user_data", "load_spend_data", "get_dashboard_data"):
                            output_valid, reason = verify_fn(result, self.session_id)
                        else:
                            output_valid, reason = verify_fn(result)
                    else:
                        output_valid = True
                    if not output_valid:
                        result = self._structured_error(tool_name, reason, retried=retried)
                except Exception as retry_exc:
                    result = self._structured_error(
                        tool_name,
                        str(retry_exc),
                        retried=retried,
                    )
            else:
                result = self._structured_error(tool_name, reason, retried=retried)

        duration_ms = int((time.perf_counter() - started) * 1000)
        safe_result = _json_safe(result)
        self._append_log(
            {
                "session_id": self.session_id,
                "tool": tool_name,
                "inputs": safe_inputs,
                "outputs": safe_result,
                "output_valid": output_valid,
                "success": output_valid,
                "retried": retried,
                "step_number": step_number,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return safe_result


def build_harness_tools(harness: Harness) -> list[Any]:
    """Return harness-wrapped tools for agent registration."""

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
        return harness.run_tool(
            "load_user_data",
            _load_user_data_tool,
            session_id=session_id,
            user_sub=user_sub,
        )

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
        return harness.run_tool(
            "load_spend_data",
            _load_spend_data_tool,
            s3_file_key=s3_file_key,
            session_id=session_id,
        )

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
        return harness.run_tool(
            "run_analysis_query",
            _run_analysis_query_tool,
            sql=sql,
            session_id=session_id,
        )

    @tool
    def get_dashboard_data(session_id: str = "default") -> dict:
        """
        Return pre-aggregated dashboard data from the loaded spend table.
        Includes: total spend, spend by category, top 10 vendors, and monthly trend.
        Call load_spend_data first.

        Args:
            session_id: Current session identifier
        """
        return harness.run_tool(
            "get_dashboard_data",
            _get_dashboard_data_tool,
            session_id=session_id,
        )

    def _fetch_harness_log(session_id: str = "default") -> dict:
        log = store.get(session_id, "harness_log") or []
        return {
            "status": "ok",
            "steps_taken": int(store.get(session_id, "harness_step_count") or 0),
            "entries": _json_safe(log),
        }

    @tool
    def get_harness_log(session_id: str = "default") -> dict:
        """
        Return the harness execution trace for this session (last 50 tool calls).

        Args:
            session_id: Current session identifier
        """
        return harness.run_tool(
            "get_harness_log",
            _fetch_harness_log,
            session_id=session_id,
        )

    return [
        load_user_data,
        load_spend_data,
        run_analysis_query,
        get_dashboard_data,
        get_harness_log,
    ]


async def run_with_harness(payload: dict, session_id: str) -> Any:
    """
    Run the spend agent with harness-wrapped tools, verification, and step limits.
    """
    from memory import create_session_manager

    message = payload.get("message", "")
    system_prompt = payload.get("system_prompt", "")
    session_manager = payload.get("session_manager")
    user_sub = payload.get("user_sub") or session_id

    if session_manager is None:
        session_manager = create_session_manager(session_id)

    max_tool_calls = int(os.environ.get("MAX_TOOL_CALLS", DEFAULT_MAX_TOOL_CALLS))
    harness = Harness(session_id=session_id, max_tool_calls=max_tool_calls)
    tools = build_harness_tools(harness)

    from main import model

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        session_manager=session_manager,
        hooks=[ReadOnlySqlHooks()],
    )

    if payload.get("s3_key"):
        store.set(session_id, "s3_key", payload["s3_key"])

    store.set(session_id, "user_sub", user_sub)

    return await agent.invoke_async(message)
