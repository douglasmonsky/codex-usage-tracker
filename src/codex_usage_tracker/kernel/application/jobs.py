"""Read-only refresh job snapshots and bounded host-side waiting."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_WAIT_SECONDS = 30.0
_TERMINAL_STATES = frozenset({"completed", "failed", "interrupted"})


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    request_hash: str
    state: str
    stage: str
    progress_percent: float
    input_generation: int | None
    output_generation: int | None
    changed_sources: int
    inserted_rows: int
    updated_rows: int
    deleted_rows: int
    heartbeat_at: str | None
    error_code: str | None
    result: dict[str, Any] | None
    terminal: bool


class JobReader:
    def __init__(self, operational_path: Path) -> None:
        self._path = operational_path.resolve()

    def get(
        self,
        job_id: str,
        *,
        wait_seconds: float = 0,
        include_result: bool = False,
    ) -> JobSnapshot:
        wait = _wait_seconds(wait_seconds)
        deadline = time.monotonic() + wait
        while True:
            snapshot = self._read(
                "WHERE refresh_run_id = ?",
                (job_id,),
                include_result=include_result,
            )
            if snapshot is None:
                raise ValueError("refresh job not found")
            if snapshot.terminal or time.monotonic() >= deadline:
                return snapshot
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def active(self, *, include_result: bool = False) -> JobSnapshot | None:
        return self._read(
            "WHERE state IN ('queued', 'running') "
            "AND CAST(lease_expires_at AS REAL) > ? ORDER BY rowid LIMIT 1",
            (time.time(),),
            include_result=include_result,
        )

    def latest(self, *, include_result: bool = False) -> JobSnapshot | None:
        return self._read(
            "ORDER BY rowid DESC LIMIT 1",
            (),
            include_result=include_result,
        )

    def _read(
        self,
        clause: str,
        parameters: tuple[Any, ...],
        *,
        include_result: bool,
    ) -> JobSnapshot | None:
        if not self._path.is_file():
            return None
        uri = f"{self._path.as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"SELECT * FROM refresh_runs {clause}",
                parameters,
            ).fetchone()
        return _snapshot(row, include_result=include_result) if row else None


def _snapshot(row: sqlite3.Row, *, include_result: bool) -> JobSnapshot:
    raw_result = row["completed_result_json"]
    result = (
        json.loads(str(raw_result))
        if include_result and raw_result is not None
        else None
    )
    return JobSnapshot(
        job_id=str(row["refresh_run_id"]),
        request_hash=str(row["request_hash"]),
        state=str(row["state"]),
        stage=str(row["stage"]),
        progress_percent=float(row["progress_percent"]),
        input_generation=_optional_int(row["input_generation"]),
        output_generation=_optional_int(row["output_generation"]),
        changed_sources=int(row["changed_source_count"]),
        inserted_rows=int(row["inserted_count"]),
        updated_rows=int(row["updated_count"]),
        deleted_rows=int(row["deleted_count"]),
        heartbeat_at=_optional_text(row["heartbeat_at"]),
        error_code=_optional_text(row["terminal_error_code"]),
        result=result,
        terminal=str(row["state"]) in _TERMINAL_STATES,
    )


def _wait_seconds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("wait_seconds must be numeric")
    if not 0 <= value <= MAX_WAIT_SECONDS:
        raise ValueError("wait_seconds is out of bounds")
    return float(value)


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None
