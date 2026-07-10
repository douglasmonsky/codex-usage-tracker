"""Text rendering for the inspect-log command."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def print_inspect_log_summary(payload: Mapping[str, Any]) -> None:
    """Print a human-readable summary while tolerating parser shape drift."""
    print(f"Log: {payload['path']}")
    print(f"Adapter: {payload['adapter']}")
    print(f"File session id: {payload['file_session_id'] or 'unknown'}")
    print(f"Parsed events: {payload['event_count']}")
    _print_values("Sessions", payload.get("session_ids"))
    _print_values("Models", payload.get("models"))

    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Mapping) and diagnostics:
        values = ", ".join(f"{key}={value}" for key, value in diagnostics.items())
        print(f"Diagnostics: {values}")
    else:
        print("Diagnostics: none")


def _print_values(label: str, value: Any) -> None:
    if isinstance(value, (list, tuple)) and value:
        print(f"{label}: " + ", ".join(str(item) for item in value))
