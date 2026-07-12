"""Persistent cache and candidate repository for Compression Lab analyses."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_CACHEABLE_STATUSES = ("completed", "completed_with_warnings")
_TERMINAL_STATUSES = (*_CACHEABLE_STATUSES, "failed", "cancelled")


def create_compression_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    source_revision: str,
    scope_hash: str,
    detector_set_version: str,
    estimator_version: str,
    compression_schema_version: int,
    scope: Mapping[str, Any],
    run_id: str | None = None,
    status: str = "pending",
    filters: Mapping[str, Any] | None = None,
    coverage: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create one analysis run and return its decoded metadata."""
    timestamp = created_at or _utc_now()
    resolved_run_id = run_id or f"compression_{uuid.uuid4().hex}"
    completed_at = timestamp if status in _TERMINAL_STATUSES else None
    started_at = timestamp if status != "pending" else None
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO compression_runs (
                run_id, status, source_revision, scope_hash,
                detector_set_version, estimator_version, compression_schema_version,
                scope_json, filters_json, coverage_json, progress_percent, stage,
                created_at, started_at, completed_at, last_accessed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_run_id,
                status,
                source_revision,
                scope_hash,
                detector_set_version,
                estimator_version,
                int(compression_schema_version),
                _json_dump(scope),
                _json_dump(filters or {}),
                _json_dump(coverage or {}),
                100.0 if status in _CACHEABLE_STATUSES else 0.0,
                "complete" if status in _CACHEABLE_STATUSES else status,
                timestamp,
                started_at,
                completed_at,
                timestamp,
            ),
        )
        row = _select_run(conn, resolved_run_id)
        if row is None:
            raise RuntimeError("compression run insert did not persist")
    return _decode_run(row)


def update_compression_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_id: str,
    status: str | None = None,
    progress_percent: float | None = None,
    stage: str | None = None,
    current_detector: str | None = None,
    completed_detectors: int | None = None,
    total_detectors: int | None = None,
    records_examined: int | None = None,
    cache_reused: bool | None = None,
    coverage: Mapping[str, Any] | None = None,
    timing: Mapping[str, Any] | None = None,
    error_summary: Mapping[str, Any] | None = None,
    aggregate_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update run lifecycle metadata while keeping progress monotonic."""
    assignments: list[str] = ["last_accessed_at = ?"]
    values: list[Any] = [_utc_now()]
    if status is not None:
        assignments.append("status = ?")
        values.append(status)
        if status == "running":
            assignments.append("started_at = COALESCE(started_at, ?)")
            values.append(_utc_now())
        if status in _TERMINAL_STATUSES:
            assignments.append("completed_at = COALESCE(completed_at, ?)")
            values.append(_utc_now())
    if progress_percent is not None:
        assignments.append("progress_percent = MAX(progress_percent, ?)")
        values.append(min(100.0, max(0.0, float(progress_percent))))
    _append_scalar(assignments, values, "stage", stage)
    _append_scalar(assignments, values, "current_detector", current_detector)
    _append_scalar(assignments, values, "completed_detectors", completed_detectors)
    _append_scalar(assignments, values, "total_detectors", total_detectors)
    _append_scalar(assignments, values, "records_examined", records_examined)
    if cache_reused is not None:
        _append_scalar(assignments, values, "cache_reused", int(cache_reused))
    _append_json(assignments, values, "coverage_json", coverage)
    _append_json(assignments, values, "timing_json", timing)
    _append_json(assignments, values, "error_summary_json", error_summary)
    _append_json(assignments, values, "aggregate_profile_json", aggregate_profile)
    values.append(run_id)
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            f"UPDATE compression_runs SET {', '.join(assignments)} WHERE run_id = ?",
            values,
        )
        row = _select_run(conn, run_id)
    return _decode_run(row) if row is not None else None


def find_compression_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    source_revision: str,
    scope_hash: str,
    detector_set_version: str,
    estimator_version: str,
    compression_schema_version: int,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Find the newest completed run matching the exact cache identity."""
    del scope
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT * FROM compression_runs
            WHERE source_revision = ?
                AND scope_hash = ?
                AND detector_set_version = ?
                AND estimator_version = ?
                AND compression_schema_version = ?
                AND status IN ('completed', 'completed_with_warnings')
            ORDER BY completed_at DESC, created_at DESC
            LIMIT 1
            """,
            (
                source_revision,
                scope_hash,
                detector_set_version,
                estimator_version,
                int(compression_schema_version),
            ),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE compression_runs SET last_accessed_at = ? WHERE run_id = ?",
                (_utc_now(), row["run_id"]),
            )
    return _decode_run(row) if row is not None else None


def get_compression_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_id: str,
) -> dict[str, Any] | None:
    """Return one decoded run and mark it recently accessed."""
    with connect(db_path) as conn:
        init_db(conn)
        row = _select_run(conn, run_id)
        if row is not None:
            conn.execute(
                "UPDATE compression_runs SET last_accessed_at = ? WHERE run_id = ?",
                (_utc_now(), run_id),
            )
    return _decode_run(row) if row is not None else None


def delete_stale_compression_runs(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    before: str,
) -> int:
    """Delete terminal runs not accessed since the supplied UTC timestamp."""
    placeholders = ", ".join("?" for _status in _TERMINAL_STATUSES)
    with connect(db_path) as conn:
        init_db(conn)
        cursor = conn.execute(
            f"""
            DELETE FROM compression_runs
            WHERE status IN ({placeholders}) AND last_accessed_at < ?
            """,
            [*_TERMINAL_STATUSES, before],
        )
    return max(0, int(cursor.rowcount))


def _decode_run(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key, output_key in (
        ("scope_json", "scope"),
        ("filters_json", "filters"),
        ("coverage_json", "coverage"),
        ("timing_json", "timing"),
        ("error_summary_json", "error_summary"),
        ("aggregate_profile_json", "aggregate_profile"),
    ):
        result[output_key] = _json_load(result.pop(key))
    result["cache_reused"] = bool(result["cache_reused"])
    return result


def _select_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM compression_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()


def _append_scalar(
    assignments: list[str],
    values: list[Any],
    column: str,
    value: Any,
) -> None:
    if value is not None:
        assignments.append(f"{column} = ?")
        values.append(value)


def _append_json(
    assignments: list[str],
    values: list[Any],
    column: str,
    value: Mapping[str, Any] | None,
) -> None:
    if value is not None:
        _append_scalar(assignments, values, column, _json_dump(value))


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_load(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
