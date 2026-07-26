"""Durable single-owner refresh leases with host-side heartbeats."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LeaseResult:
    refresh_run_id: str
    created: bool
    busy: bool


@dataclass(frozen=True)
class LeaseGuard:
    repository: RefreshLeaseRepository
    refresh_run_id: str
    owner_id: str
    lost: threading.Event

    def check(self) -> None:
        """Fence every durable write and promotion against stale ownership."""

        if self.lost.is_set() or not self.repository.assert_owned(
            self.refresh_run_id,
            self.owner_id,
        ):
            self.lost.set()
            raise RuntimeError("refresh lease ownership lost")


class RefreshLeaseRepository:
    """Own one durable lease per operational sidecar."""

    def __init__(self, path: Path, *, lease_seconds: float = 30.0) -> None:
        self._path = path.resolve()
        self._lease_seconds = lease_seconds

    def acquire(
        self,
        request_hash: str,
        owner_id: str,
        *,
        now: float | None = None,
    ) -> LeaseResult:
        observed = time.time() if now is None else now
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                """
                SELECT refresh_run_id, request_hash, lease_expires_at
                FROM refresh_runs
                WHERE state IN ('queued', 'running')
                ORDER BY rowid
                LIMIT 1
                """
            ).fetchone()
            if active is not None:
                run_id = str(active["refresh_run_id"])
                expires = float(active["lease_expires_at"] or 0)
                if expires > observed:
                    return LeaseResult(
                        refresh_run_id=run_id,
                        created=False,
                        busy=str(active["request_hash"]) != request_hash,
                    )
                connection.execute(
                    """
                    UPDATE refresh_runs
                    SET state = 'interrupted',
                        terminal_error_code = 'refresh.lease_expired',
                        terminal_error_message = 'stale owner recovered'
                    WHERE refresh_run_id = ?
                    """,
                    (run_id,),
                )
            run_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO refresh_runs(
                    refresh_run_id, request_hash, owner_id, lease_expires_at,
                    state, stage, progress_percent, planned_high_water_json,
                    changed_source_count, inserted_count, updated_count,
                    deleted_count, stage_timings_json
                )
                VALUES (?, ?, ?, ?, 'running', 'planning', 0, '{}',
                        0, 0, 0, 0, '{}')
                """,
                (
                    run_id,
                    request_hash,
                    owner_id,
                    str(observed + self._lease_seconds),
                ),
            )
        return LeaseResult(refresh_run_id=run_id, created=True, busy=False)

    def complete(
        self,
        refresh_run_id: str,
        *,
        generation: int,
        result: dict[str, Any],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET state = 'completed', stage = 'complete',
                    progress_percent = 100, output_generation = ?,
                    changed_source_count = ?, inserted_count = ?,
                    deleted_count = ?, completed_result_json = ?,
                    heartbeat_at = CURRENT_TIMESTAMP
                WHERE refresh_run_id = ?
                """,
                (
                    generation,
                    int(result.get("changed_sources", 0)),
                    int(result.get("inserted_calls", 0))
                    + int(result.get("inserted_tools", 0)),
                    int(result.get("deleted_rows", 0)),
                    json.dumps(result, sort_keys=True, separators=(",", ":")),
                    refresh_run_id,
                ),
            )

    def progress(
        self,
        refresh_run_id: str,
        owner_id: str,
        *,
        stage: str,
        percent: float,
        high_water: dict[str, int] | None = None,
        changed_sources: int = 0,
        inserted: int = 0,
        updated: int = 0,
        deleted: int = 0,
        timings: dict[str, float] | None = None,
    ) -> None:
        """Persist bounded externally observable refresh progress."""

        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE refresh_runs
                SET stage = ?, progress_percent = ?,
                    planned_high_water_json = ?,
                    changed_source_count = ?, inserted_count = ?,
                    updated_count = ?, deleted_count = ?,
                    stage_timings_json = ?, heartbeat_at = CURRENT_TIMESTAMP
                WHERE refresh_run_id = ? AND owner_id = ? AND state = 'running'
                """,
                (
                    stage[:64],
                    max(0.0, min(100.0, percent)),
                    json.dumps(high_water or {}, sort_keys=True),
                    changed_sources,
                    inserted,
                    updated,
                    deleted,
                    json.dumps(timings or {}, sort_keys=True),
                    refresh_run_id,
                    owner_id,
                ),
            )
        if cursor.rowcount != 1:
            raise RuntimeError("refresh lease ownership lost")

    def fail(self, refresh_run_id: str, code: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET state = 'failed', stage = 'failed',
                    terminal_error_code = ?, heartbeat_at = CURRENT_TIMESTAMP
                WHERE refresh_run_id = ?
                """,
                (code[:64], refresh_run_id),
            )

    def renew(
        self,
        refresh_run_id: str,
        owner_id: str,
        *,
        now: float | None = None,
    ) -> bool:
        observed = time.time() if now is None else now
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE refresh_runs
                SET lease_expires_at = ?, heartbeat_at = CURRENT_TIMESTAMP
                WHERE refresh_run_id = ?
                  AND owner_id = ?
                  AND state = 'running'
                """,
                (
                    str(observed + self._lease_seconds),
                    refresh_run_id,
                    owner_id,
                ),
            )
        return cursor.rowcount == 1

    def assert_owned(
        self,
        refresh_run_id: str,
        owner_id: str,
        *,
        now: float | None = None,
    ) -> bool:
        observed = time.time() if now is None else now
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM refresh_runs
                WHERE refresh_run_id = ? AND owner_id = ?
                  AND state = 'running'
                  AND CAST(lease_expires_at AS REAL) > ?
                """,
                (refresh_run_id, owner_id, observed),
            ).fetchone()
        return row is not None

    @contextmanager
    def maintain(
        self,
        refresh_run_id: str,
        owner_id: str,
    ) -> Iterator[LeaseGuard]:
        """Renew a live lease while parsing proceeds outside SQLite."""

        stop = threading.Event()
        lost = threading.Event()
        interval = max(0.1, self._lease_seconds / 3)

        def heartbeat() -> None:
            while not stop.wait(interval):
                try:
                    renewed = self.renew(refresh_run_id, owner_id)
                except sqlite3.Error:
                    lost.set()
                    return
                if not renewed:
                    lost.set()
                    return

        thread = threading.Thread(
            target=heartbeat,
            name=f"kernel-refresh-heartbeat-{refresh_run_id[:8]}",
            daemon=True,
        )
        thread.start()
        try:
            guard = LeaseGuard(self, refresh_run_id, owner_id, lost)
            guard.check()
            yield guard
        finally:
            stop.set()
            thread.join(timeout=min(5.0, interval + 1.0))

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._path.chmod(0o600)
        connection = sqlite3.connect(self._path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()
