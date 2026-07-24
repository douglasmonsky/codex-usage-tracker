"""SQLite repository for compact generic analysis job state."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.analysis_job_codec import (
    _as_utc,
    _bounded_json,
    _compatible,
    _decode,
    _interrupt_row,
    _json_dump,
    _optional_bounded_json,
    _require_completed_result,
    _select_active,
    _select_job,
    _select_reusable,
    _timestamp,
    _touch,
)
from codex_usage_tracker.store.analysis_job_lifecycle import (
    ERROR_KEYS,
    PROGRESS_KEYS,
    REQUEST_ROOT_KEYS,
    RESULT_ROOT_KEYS,
    STATUSES,
    TERMINAL_STATUSES,
    can_transition,
    job_counts,
    lease_expired,
    monotonic_progress,
    prune_in_connection,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_PROCESS_OWNER_ID = f"process:{secrets.token_urlsafe(18)}"


class AnalysisJobRepository:
    """Persist normalized requests, lifecycle state, and bounded results."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        max_request_bytes: int = 16 * 1024,
        max_result_bytes: int = 1024 * 1024,
        max_terminal_jobs: int = 256,
        terminal_retention: timedelta = timedelta(days=30),
        owner_id: str = _PROCESS_OWNER_ID,
        lease_ttl: timedelta = timedelta(seconds=30),
    ) -> None:
        if max_request_bytes <= 0 or max_result_bytes <= 0:
            raise ValueError("job JSON budgets must be positive")
        if max_terminal_jobs <= 0:
            raise ValueError("max_terminal_jobs must be positive")
        if terminal_retention <= timedelta(0):
            raise ValueError("terminal_retention must be positive")
        if not owner_id:
            raise ValueError("owner_id must not be empty")
        if lease_ttl <= timedelta(0):
            raise ValueError("lease_ttl must be positive")
        self.db_path = db_path
        self.max_request_bytes = max_request_bytes
        self.max_result_bytes = max_result_bytes
        self.max_terminal_jobs = max_terminal_jobs
        self.terminal_retention = terminal_retention
        self.owner_id = owner_id
        self.lease_ttl = lease_ttl

    def create_or_reuse(
        self,
        *,
        job_id: str,
        job_kind: str,
        semantic_key: str,
        source_revision: str,
        request_schema: str,
        request: Mapping[str, object],
        result_schema: str,
        now: datetime | None = None,
    ) -> tuple[dict[str, object], bool]:
        request_json = _bounded_json(
            request,
            budget=self.max_request_bytes,
            label="request",
            reject_raw_context=True,
            allowed_root_keys=REQUEST_ROOT_KEYS.get(request_schema),
        )
        current = _as_utc(now)
        timestamp = _timestamp(current)
        lease_expires_at = _timestamp(current + self.lease_ttl)
        with connect(self.db_path) as conn:
            init_db(conn)
            conn.execute("BEGIN IMMEDIATE")
            active = _select_active(conn, job_kind, semantic_key)
            if active is not None and lease_expired(active, current):
                _interrupt_row(conn, str(active["job_id"]), timestamp)
                active = None
            if active is not None and _compatible(
                active,
                source_revision=source_revision,
                request_schema=request_schema,
                result_schema=result_schema,
            ):
                return _decode(active), False
            if active is not None:
                if str(active["owner_id"]) != self.owner_id:
                    return _decode(active), False
                _interrupt_row(conn, str(active["job_id"]), timestamp)
            completed = _select_reusable(
                conn,
                job_kind=job_kind,
                semantic_key=semantic_key,
                source_revision=source_revision,
                result_schema=result_schema,
            )
            if completed is not None:
                _touch(conn, str(completed["job_id"]), timestamp)
                refreshed = _select_job(conn, str(completed["job_id"]))
                if refreshed is None:
                    raise RuntimeError("reusable analysis job disappeared during selection")
                return _decode(refreshed), False
            conn.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id,
                    job_kind,
                    semantic_key,
                    status,
                    source_revision,
                    request_schema,
                    request_json,
                    progress_json,
                    result_schema,
                    result_json,
                    error_json,
                    owner_id,
                    lease_expires_at,
                    created_at,
                    started_at,
                    completed_at,
                    updated_at,
                    last_accessed_at
                ) VALUES (
                    ?, ?, ?, 'queued', ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, ?, ?
                )
                """,
                (
                    job_id,
                    job_kind,
                    semantic_key,
                    source_revision,
                    request_schema,
                    request_json,
                    _json_dump({"percent": 0, "stage": "queued"}),
                    result_schema,
                    self.owner_id,
                    lease_expires_at,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            row = _select_job(conn, job_id)
            if row is None:
                raise RuntimeError("analysis job insert did not persist")
            return _decode(row), True

    def update_status(
        self,
        job_id: str,
        *,
        state: str,
        progress: Mapping[str, object],
        result_schema: str | None = None,
        result: object = None,
        error: Mapping[str, object] | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if state not in STATUSES:
            raise ValueError("invalid analysis job state")
        result_json = _optional_bounded_json(
            result,
            budget=self.max_result_bytes,
            label="result",
            allowed_root_keys=RESULT_ROOT_KEYS.get(result_schema or ""),
        )
        error_json = _optional_bounded_json(
            error,
            budget=4096,
            label="error",
            allowed_root_keys=ERROR_KEYS,
        )
        _require_completed_result(state, result_schema, result_json)
        current_time = _as_utc(now)
        timestamp = _timestamp(current_time)
        lease_expires_at = _timestamp(current_time + self.lease_ttl)
        with connect(self.db_path) as conn:
            init_db(conn)
            conn.execute("BEGIN IMMEDIATE")
            current = _select_job(conn, job_id)
            if current is None:
                raise KeyError(job_id)
            current_state = str(current["status"])
            if str(current["owner_id"]) != self.owner_id or current_state in TERMINAL_STATUSES:
                return _decode(current)
            if not can_transition(current_state, state):
                return _decode(current)
            progress_json = _bounded_json(
                monotonic_progress(current, progress),
                budget=4096,
                label="progress",
                reject_raw_context=True,
                allowed_root_keys=PROGRESS_KEYS,
            )
            conn.execute(
                """
                UPDATE analysis_jobs
                SET
                    status = ?,
                    progress_json = ?,
                    result_schema = COALESCE(?, result_schema),
                    result_json = ?,
                    error_json = ?,
                    started_at = CASE
                        WHEN ? IN ('running', 'completed', 'failed')
                        THEN COALESCE(started_at, ?)
                        ELSE started_at
                    END,
                    completed_at = CASE
                        WHEN ? IN ('completed', 'failed', 'cancelled', 'interrupted')
                        THEN COALESCE(completed_at, ?)
                        ELSE NULL
                    END,
                    lease_expires_at = ?,
                    updated_at = ?,
                    last_accessed_at = ?
                WHERE job_id = ? AND owner_id = ?
                """,
                (
                    state,
                    progress_json,
                    result_schema,
                    result_json,
                    error_json,
                    state,
                    timestamp,
                    state,
                    timestamp,
                    lease_expires_at,
                    timestamp,
                    timestamp,
                    job_id,
                    self.owner_id,
                ),
            )
            row = _select_job(conn, job_id)
            if row is None:
                raise RuntimeError("updated analysis job disappeared during selection")
            decoded = _decode(row)
            if state in TERMINAL_STATUSES:
                prune_in_connection(
                    conn,
                    current=current_time,
                    terminal_retention=self.terminal_retention,
                    max_terminal_jobs=self.max_terminal_jobs,
                )
            return decoded

    def get(
        self,
        job_id: str,
        *,
        touch: bool = False,
        now: datetime | None = None,
    ) -> dict[str, object] | None:
        with connect(self.db_path) as conn:
            init_db(conn)
            row = _select_job(conn, job_id)
            if row is None:
                return None
            if touch:
                _touch(conn, job_id, _timestamp(now))
                row = _select_job(conn, job_id)
                if row is None:
                    raise RuntimeError("analysis job disappeared while updating access time")
            return _decode(row)

    def heartbeat(self, job_id: str, *, now: datetime | None = None) -> bool:
        """Extend one active lease only when this process still owns the job."""
        if not self.db_path.is_file():
            return False
        current = _as_utc(now)
        with connect(self.db_path) as conn:
            init_db(conn)
            cursor = conn.execute(
                """
                UPDATE analysis_jobs
                SET lease_expires_at = ?, updated_at = ?
                WHERE job_id = ?
                  AND owner_id = ?
                  AND status IN ('queued', 'running')
                """,
                (
                    _timestamp(current + self.lease_ttl),
                    _timestamp(current),
                    job_id,
                    self.owner_id,
                ),
            )
            return cursor.rowcount == 1

    def find_reusable(
        self,
        *,
        job_kind: str,
        semantic_key: str,
        source_revision: str,
        result_schema: str,
        now: datetime | None = None,
    ) -> dict[str, object] | None:
        current = _as_utc(now)
        with connect(self.db_path) as conn:
            init_db(conn)
            conn.execute("BEGIN IMMEDIATE")
            active = _select_active(conn, job_kind, semantic_key)
            if active is not None and lease_expired(active, current):
                _interrupt_row(conn, str(active["job_id"]), _timestamp(current))
                active = None
            row = (
                active
                if active is not None
                and _compatible(
                    active,
                    source_revision=source_revision,
                    request_schema=str(active["request_schema"]),
                    result_schema=result_schema,
                )
                else _select_reusable(
                    conn,
                    job_kind=job_kind,
                    semantic_key=semantic_key,
                    source_revision=source_revision,
                    result_schema=result_schema,
                )
            )
            if row is None:
                return None
            _touch(conn, str(row["job_id"]), _timestamp(current))
            refreshed = _select_job(conn, str(row["job_id"]))
            if refreshed is None:
                raise RuntimeError("reusable analysis job disappeared during selection")
            return _decode(refreshed)

    def completed_results(
        self,
        *,
        job_kind: str,
        result_schema: str,
        source_revision: str,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]:
        with connect(self.db_path) as conn:
            init_db(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM analysis_jobs
                WHERE job_kind = ?
                  AND result_schema = ?
                  AND source_revision = ?
                  AND status = 'completed'
                  AND result_json IS NOT NULL
                ORDER BY completed_at, job_id
                LIMIT ?
                """,
                (job_kind, result_schema, source_revision, limit),
            ).fetchall()
            return tuple(
                result
                for row in rows
                if isinstance((result := _decode(row).get("result")), Mapping)
            )

    def recover_interrupted(self, *, now: datetime | None = None) -> int:
        if not self.db_path.is_file():
            return 0
        current = _as_utc(now)
        timestamp = _timestamp(current)
        with connect(self.db_path) as conn:
            init_db(conn)
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT job_id
                FROM analysis_jobs
                WHERE status IN ('queued', 'running')
                  AND owner_id <> ?
                  AND lease_expires_at <= ?
                """,
                (self.owner_id, timestamp),
            ).fetchall()
            for row in rows:
                _interrupt_row(conn, str(row["job_id"]), timestamp)
            return len(rows)

    def prune(self, *, now: datetime | None = None) -> int:
        if not self.db_path.is_file():
            return 0
        current = _as_utc(now)
        with connect(self.db_path) as conn:
            init_db(conn)
            conn.execute("BEGIN IMMEDIATE")
            return prune_in_connection(
                conn,
                current=current,
                terminal_retention=self.terminal_retention,
                max_terminal_jobs=self.max_terminal_jobs,
            )

    def counts(self) -> dict[str, int]:
        return job_counts(self.db_path)
