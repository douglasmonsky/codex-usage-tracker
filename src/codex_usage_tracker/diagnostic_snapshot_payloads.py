"""Payload and metadata helpers for diagnostic snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.diagnostic_snapshot_analysis import path_privacy_metadata
from codex_usage_tracker.diagnostic_snapshot_concentration import (
    concentration_privacy_metadata,
)
from codex_usage_tracker.diagnostic_snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_HISTORY_ACTIVE,
    DIAGNOSTIC_HISTORY_ALL,
    DIAGNOSTIC_OVERVIEW_SCHEMA,
    DIAGNOSTIC_OVERVIEW_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_SNAPSHOT_NOTES,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
)


def ready_payload(
    *,
    schema: str,
    section: str,
    snapshot: dict[str, Any],
    refreshed: bool,
    **sections: object,
) -> dict[str, Any]:
    """Build a ready diagnostic snapshot payload."""
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "ready",
        "refreshed": refreshed,
        "raw_context_included": False,
        "snapshot": snapshot,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    payload.update(sections)
    return payload


def missing_payload(
    *,
    history_scope: str,
    schema: str = DIAGNOSTIC_OVERVIEW_SCHEMA,
    section: str = DIAGNOSTIC_OVERVIEW_SECTION,
) -> dict[str, Any]:
    """Build an empty diagnostic snapshot payload for a missing section."""
    payload: dict[str, Any] = {
        "schema": schema,
        "section": section,
        "status": "missing",
        "refreshed": False,
        "raw_context_included": False,
        "snapshot": None,
        "history_scope": history_scope,
        "notes": list(DIAGNOSTIC_SNAPSHOT_NOTES),
    }
    if section == DIAGNOSTIC_OVERVIEW_SECTION:
        payload["overview"] = None
    elif section == DIAGNOSTIC_TOOL_OUTPUT_SECTION:
        payload["summary"] = None
        payload["functions"] = []
        payload["command_roots"] = []
        payload["missing_reasons"] = []
    elif section == DIAGNOSTIC_COMMANDS_SECTION:
        payload["summary"] = None
        payload["commands"] = []
    elif section == DIAGNOSTIC_GIT_INTERACTIONS_SECTION:
        payload["summary"] = None
        payload["interactions"] = []
        payload["categories"] = []
        payload["mutability"] = []
    elif section == DIAGNOSTIC_FILE_READS_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_paths"] = []
        payload["largest_read_commands"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_FILE_MODIFICATIONS_SECTION:
        payload["summary"] = None
        payload["top_paths"] = []
        payload["by_extension"] = []
        payload["largest_events"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_READ_PRODUCTIVITY_SECTION:
        payload["summary"] = None
        payload["by_reader"] = []
        payload["top_modified_paths"] = []
        payload["path_privacy"] = path_privacy_metadata()
    elif section == DIAGNOSTIC_CONCENTRATION_SECTION:
        payload["summary"] = None
        payload["metrics"] = []
        payload["dimensions"] = []
        payload["largest_impact_rows"] = []
        payload["privacy"] = concentration_privacy_metadata()
    elif section == DIAGNOSTIC_USAGE_DRAIN_SECTION:
        payload["summary"] = None
        payload["thread_cost_curves"] = {"threads": []}
        payload["time_series"] = {}
        payload["model_highlights"] = {}
        payload["pricing"] = {}
    return payload


def snapshot_metadata(
    *,
    computed_at: str,
    history_scope: str,
    source_logs_scanned: int,
    usage_rows_scanned: int,
) -> dict[str, Any]:
    """Build diagnostic snapshot metadata."""
    return {
        "computed_at": computed_at,
        "history_scope": history_scope,
        "source_logs_scanned": int(source_logs_scanned),
        "usage_rows_scanned": int(usage_rows_scanned),
        "raw_content_included": False,
    }


def history_scope(include_archived: bool) -> str:
    """Return the stored snapshot history-scope label."""
    return DIAGNOSTIC_HISTORY_ALL if include_archived else DIAGNOSTIC_HISTORY_ACTIVE


def utc_now() -> str:
    """Return the current UTC timestamp used for snapshot metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def int_value(value: object) -> int:
    """Coerce aggregate SQL values into ints for snapshot payloads."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0
