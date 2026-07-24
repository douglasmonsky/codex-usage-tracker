"""Store-local refresh counters without importing the public store facade."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.core.schema import USAGE_EVENT_SCHEMA_CHECKSUM
from codex_usage_tracker.parser.otel import OTEL_DIAGNOSTIC_KEYS
from codex_usage_tracker.parser.state import (
    PARSER_ADAPTER_VERSION,
    PARSER_DIAGNOSTIC_KEYS,
)
from codex_usage_tracker.store.cache_repository import SQLiteCacheRepository
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import SCHEMA_VERSION, init_db

REFRESH_WORKFLOW_KEY = "refresh_workflow_v1"

OTEL_REFRESH_COUNTER_KEYS = (
    "otel_files_scanned",
    "otel_imported",
    "otel_duplicates",
    "otel_matched",
    "otel_pending",
    "otel_ambiguous",
    "otel_conflicts",
    *OTEL_DIAGNOSTIC_KEYS,
)


def record_refresh_metadata(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scanned_files: int,
    parsed_events: int,
    skipped_events: int,
    inserted_or_updated_events: int,
    parser_diagnostics: dict[str, int] | None = None,
    otel_diagnostics: dict[str, int] | None = None,
    parsed_source_files: int | None = None,
    skipped_source_files: int | None = None,
    workflow_kind: str = "refresh",
) -> None:
    """Record the latest refresh counters in refresh_meta."""

    values = {
        "latest_refresh_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scanned_files": str(scanned_files),
        "parsed_events": str(parsed_events),
        "skipped_events": str(skipped_events),
        "inserted_or_updated_events": str(inserted_or_updated_events),
        "parser_adapter": PARSER_ADAPTER_VERSION,
        "schema_version": str(SCHEMA_VERSION),
        "usage_events_schema_checksum": USAGE_EVENT_SCHEMA_CHECKSUM,
    }
    if parsed_source_files is not None:
        values["parsed_source_files"] = str(parsed_source_files)
    if skipped_source_files is not None:
        values["skipped_source_files"] = str(skipped_source_files)
    diagnostics = parser_diagnostics or {}
    for key in PARSER_DIAGNOSTIC_KEYS:
        values[f"parser_{key}"] = str(int(diagnostics.get(key, 0)))
    otel_counters = otel_diagnostics or {}
    for key in OTEL_REFRESH_COUNTER_KEYS:
        values[key] = str(int(otel_counters.get(key, 0)))
    with connect(db_path) as conn:
        init_db(conn)
        cache = SQLiteCacheRepository(conn)
        cache.set_many(values)
        set_refresh_workflow_state(
            conn,
            kind=workflow_kind,
            phase="complete",
            status="completed",
        )


def set_refresh_workflow_state(
    conn: sqlite3.Connection,
    *,
    kind: str,
    phase: str,
    status: str = "running",
) -> None:
    """Persist a bounded retry marker in the caller's transaction."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = json.dumps(
        {
            "kind": kind,
            "phase": phase,
            "status": status,
            "updated_at": now,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    SQLiteCacheRepository(conn).set_many({REFRESH_WORKFLOW_KEY: payload})


def record_refresh_workflow_state(
    db_path: Path,
    *,
    kind: str,
    phase: str,
    status: str = "running",
) -> None:
    """Record a refresh phase independently so an interrupted run is visible."""
    with connect(db_path) as conn:
        init_db(conn)
        set_refresh_workflow_state(conn, kind=kind, phase=phase, status=status)


def read_refresh_workflow_state(db_path: Path) -> dict[str, Any] | None:
    """Return the bounded persisted workflow state when it is valid."""
    with connect(db_path) as conn:
        init_db(conn)
        raw = SQLiteCacheRepository(conn).get(REFRESH_WORKFLOW_KEY)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
