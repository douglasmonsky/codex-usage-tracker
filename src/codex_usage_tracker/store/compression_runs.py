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
    source_generation: int = 0,
    revision_key: str = "",
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
                source_generation, revision_key,
                created_at, started_at, completed_at, last_accessed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                int(source_generation),
                revision_key,
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
    public_profile: Mapping[str, Any] | None = None,
    source_revision: str | None = None,
    source_generation: int | None = None,
    revision_key: str | None = None,
) -> dict[str, Any] | None:
    """Update run lifecycle metadata while keeping progress monotonic."""
    now = _utc_now()
    normalized_progress = _normalize_progress(progress_percent)
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            UPDATE compression_runs
            SET last_accessed_at = ?,
                status = COALESCE(?, status),
                started_at = CASE
                    WHEN ? = 'running' THEN COALESCE(started_at, ?)
                    ELSE started_at
                END,
                completed_at = CASE
                    WHEN ? IN ('completed', 'completed_with_warnings', 'failed', 'cancelled')
                        THEN COALESCE(completed_at, ?)
                    ELSE completed_at
                END,
                progress_percent = CASE
                    WHEN ? IS NULL THEN progress_percent
                    ELSE MAX(progress_percent, ?)
                END,
                stage = COALESCE(?, stage),
                current_detector = COALESCE(?, current_detector),
                completed_detectors = COALESCE(?, completed_detectors),
                total_detectors = COALESCE(?, total_detectors),
                records_examined = COALESCE(?, records_examined),
                cache_reused = COALESCE(?, cache_reused),
                coverage_json = COALESCE(?, coverage_json),
                timing_json = COALESCE(?, timing_json),
                error_summary_json = COALESCE(?, error_summary_json),
                aggregate_profile_json = COALESCE(?, aggregate_profile_json),
                public_profile_json = COALESCE(?, public_profile_json),
                source_revision = COALESCE(?, source_revision),
                source_generation = COALESCE(?, source_generation),
                revision_key = COALESCE(?, revision_key)
            WHERE run_id = ?
            """,
            (
                now,
                status,
                status,
                now,
                status,
                now,
                normalized_progress,
                normalized_progress,
                stage,
                current_detector,
                completed_detectors,
                total_detectors,
                records_examined,
                _optional_bool_int(cache_reused),
                _json_or_none(coverage),
                _json_or_none(timing),
                _json_or_none(error_summary),
                _json_or_none(aggregate_profile),
                _json_or_none(public_profile),
                source_revision,
                source_generation,
                revision_key,
                run_id,
            ),
        )
        row = _select_run(conn, run_id)
    return _decode_run(row) if row is not None else None


def find_current_compression_profile(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    revision_key: str,
    scope_hash: str,
    detector_set_version: str,
    estimator_version: str,
    compression_schema_version: int,
) -> dict[str, Any] | None:
    """Read only the compact profile for an exact current-generation cache hit."""
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT run_id, public_profile_json
            FROM compression_runs
            WHERE revision_key = ?
                AND scope_hash = ?
                AND detector_set_version = ?
                AND estimator_version = ?
                AND compression_schema_version = ?
                AND status IN ('completed', 'completed_with_warnings')
                AND public_profile_json != '{}'
            ORDER BY completed_at DESC, created_at DESC
            LIMIT 1
            """,
            (
                revision_key,
                scope_hash,
                detector_set_version,
                estimator_version,
                int(compression_schema_version),
            ),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE compression_runs SET last_accessed_at = ? WHERE run_id = ?",
            (_utc_now(), row["run_id"]),
        )
        return _json_load(row["public_profile_json"])


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
    with connect(db_path) as conn:
        init_db(conn)
        cursor = conn.execute(
            """
            DELETE FROM compression_runs
            WHERE status IN (?, ?, ?, ?) AND last_accessed_at < ?
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
        ("public_profile_json", "public_profile"),
    ):
        result[output_key] = _json_load(result.pop(key))
    result["cache_reused"] = bool(result["cache_reused"])
    return result


def _select_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM compression_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_load(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_progress(value: float | None) -> float | None:
    return None if value is None else min(100.0, max(0.0, float(value)))


def _optional_bool_int(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _json_or_none(value: Mapping[str, Any] | None) -> str | None:
    return None if value is None else _json_dump(value)
