"""Context API settings helpers for the local dashboard server."""

from __future__ import annotations

import threading
from urllib.parse import parse_qs

from codex_usage_tracker.server.utils import first_query_value, parse_bool_query_value

CONTEXT_SETTINGS_SCHEMA = "codex-usage-tracker-context-settings-v1"


class ContextApiState:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled


def context_settings_payload(
    query: str,
    *,
    context_api_state: ContextApiState,
) -> dict[str, object]:
    """Update context API state and return the settings response payload."""
    params = parse_qs(query)
    enabled = parse_bool_query_value(first_query_value(params.get("enabled")), True)
    context_api_state.set_enabled(enabled)
    return {
        "schema": CONTEXT_SETTINGS_SCHEMA,
        "context_api_enabled": context_api_state.enabled,
        "raw_context_persisted": False,
    }
