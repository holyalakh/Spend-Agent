from typing import Any


class SessionStore:
    """Simple in-process key-value store for DuckDB connections and session state."""

    _data: dict = {}

    def set(self, session_id: str, key: str, value: Any):
        self._data.setdefault(session_id, {})[key] = value

    def get(self, session_id: str, key: str) -> Any:
        return self._data.get(session_id, {}).get(key)
