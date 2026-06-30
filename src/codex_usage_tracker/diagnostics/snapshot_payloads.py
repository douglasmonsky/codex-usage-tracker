"""Payload and metadata helpers for diagnostic snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_analysis import path_privacy_metadata
from codex_usage_tracker.diagnostics.snapshot_concentration import (
    concentration_privacy_metadata,
)
from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_CONCENTRATION_SECTION,
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION,
    DIAGNOSTIC_FILE_READS_SECTION,
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION,
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
    DIAGNOSTIC_HISTORY_ACTIVE,
    DIAGNOSTIC_HISTORY_ALL,
    DIAGNOSTIC_OVERVIEW_SCHEMA,
    DIAGNOSTIC_OVERVIEW_SECTION,
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION,
    DIAGNOSTIC_SNAPSHOT_NOTES,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
)

MissingFieldValue = object | Callable[[], object]


def _empty_thread_cost_curves() -> dict[str, list[object]]:
    return {"threads": []}


_MISSING_SECTION_DEFAULTS: dict[str, dict[str, MissingFieldValue]] = {
    DIAGNOSTIC_OVERVIEW_SECTION: {
        "overview": None,
    },
    DIAGNOSTIC_TOOL_OUTPUT_SECTION: {
        "summary": None,
        "functions": list,
        "command_roots": list,
        "missing_reasons": list,
    },
    DIAGNOSTIC_COMMANDS_SECTION: {
        "summary": None,
        "commands": list,
    },
    DIAGNOSTIC_GIT_INTERACTIONS_SECTION: {
        "summary": None,
        "interactions": list,
        "categories": list,
        "mutability": list,
    },
    DIAGNOSTIC_FILE_READS_SECTION: {
        "summary": None,
        "by_reader": list,
        "top_paths": list,
        "largest_read_commands": list,
        "path_privacy": path_privacy_metadata,
    },
    DIAGNOSTIC_FILE_MODIFICATIONS_SECTION: {
        "summary": None,
        "top_paths": list,
        "by_extension": list,
        "largest_events": list,
        "path_privacy": path_privacy_metadata,
    },
    DIAGNOSTIC_READ_PRODUCTIVITY_SECTION: {
        "summary": None,
        "by_reader": list,
        "top_modified_paths": list,
        "path_privacy": path_privacy_metadata,
    },
    DIAGNOSTIC_CONCENTRATION_SECTION: {
        "summary": None,
        "metrics": list,
        "dimensions": list,
        "largest_impact_rows": list,
        "privacy": concentration_privacy_metadata,
    },
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION: {
        "summary": None,
        "drivers": list,
        "top_threads": list,
        "top_models": list,
        "top_efforts": list,
        "token_mix": None,
        "signals": list,
    },
    DIAGNOSTIC_USAGE_DRAIN_SECTION: {
        "summary": None,
        "thread_cost_curves": _empty_thread_cost_curves,
        "time_series": dict,
        "model_highlights": dict,
        "pricing": dict,
    },
}


def _resolve_missing_field(value: MissingFieldValue) -> object:
    return value() if callable(value) else value


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
    for key, value in _MISSING_SECTION_DEFAULTS.get(section, {}).items():
        payload[key] = _resolve_missing_field(value)
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
