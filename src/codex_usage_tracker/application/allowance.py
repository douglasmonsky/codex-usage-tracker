"""Transport-independent orchestration for canonical allowance operations."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import weakref
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_usage_tracker.allowance_intelligence.analysis import (
    ANALYSIS_SCHEMA,
    allowance_analysis_request,
    build_allowance_analysis,
    read_allowance_analysis,
)
from codex_usage_tracker.allowance_intelligence.service import (
    build_allowance_evidence,
    build_allowance_series,
    build_allowance_status,
)
from codex_usage_tracker.application.allowance_models import AllowanceRequest, AllowanceResult
from codex_usage_tracker.application.errors import RequestContextError, RequestValidationError
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.jobs.adapters import AnalysisJobAdapter, request_hash
from codex_usage_tracker.jobs.models import JobStatusV1
from codex_usage_tracker.jobs.service import MAX_SEMANTIC_JOBS, JobService
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_RANGE_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "8w": timedelta(weeks=8),
    "6m": timedelta(days=183),
}
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_JOB_RESULT_BUDGET = 60 * 1024


@dataclass
class _AnalysisRecord:
    job_id: str
    source_revision: str
    status: str
    created_at: str
    updated_at: str
    result: Mapping[str, object] | None = None


class AllowanceAnalysisRuntime:
    """Application-owned allowance worker registered through the generic job facade."""

    def __init__(self, job_service: JobService) -> None:
        self.job_service = job_service
        self._lock = threading.RLock()
        self._records: dict[str, _AnalysisRecord] = {}

    def start(
        self,
        *,
        semantic_key: str,
        source_revision: str,
        worker: Callable[[], Mapping[str, object]],
    ) -> JobStatusV1:
        with self._lock:
            reusable = self.job_service.reusable(
                semantic_key,
                source_revision=source_revision,
                result_schema=ANALYSIS_SCHEMA,
            )
            if reusable is not None:
                return reusable
            self._prune_records()
            if len(self._records) >= MAX_SEMANTIC_JOBS:
                raise RequestContextError("allowance analysis job capacity is temporarily full")
            now = _utc_now()
            job_id = f"allowance_{secrets.token_urlsafe(12)}"
            record = _AnalysisRecord(job_id, source_revision, "queued", now, now)
            self._records[job_id] = record
            adapter = AnalysisJobAdapter(
                self._read,
                kind="allowance",
                request_hash=semantic_key,
                result_schema=ANALYSIS_SCHEMA,
                result_budget=_JOB_RESULT_BUDGET,
            )
            self.job_service.register_semantic(
                kind="allowance",
                job_id=job_id,
                adapter=adapter,
                semantic_key=semantic_key,
            )
        threading.Thread(target=self._run, args=(record, worker), daemon=True).start()
        return self.job_service.status(job_id)

    def _prune_records(self) -> None:
        for job_id, record in tuple(self._records.items()):
            if len(self._records) < MAX_SEMANTIC_JOBS:
                break
            if record.status in {"completed", "failed"}:
                self._records.pop(job_id, None)
                self.job_service.discard_semantic_job(job_id)

    def _run(self, record: _AnalysisRecord, worker: Callable[[], Mapping[str, object]]) -> None:
        self._update(record, status="running")
        try:
            result = worker()
        except Exception:  # noqa: BLE001 - the generic adapter exposes a safe failure.
            self._update(record, status="failed")
        else:
            self._update(record, status="completed", result=result)

    def _update(
        self,
        record: _AnalysisRecord,
        *,
        status: str,
        result: Mapping[str, object] | None = None,
    ) -> None:
        with self._lock:
            record.status = status
            record.updated_at = _utc_now()
            record.result = result

    def _read(self, job_id: str, *, include_result: bool = False) -> Mapping[str, object]:
        with self._lock:
            record = self._records[job_id]
            terminal = record.status in {"completed", "failed"}
            return {
                "job_id": record.job_id,
                "status": record.status,
                "stage": "complete" if record.status == "completed" else record.status,
                "source_revision": record.source_revision,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "completed_at": record.updated_at if terminal else None,
                "progress": {"percent": 100 if record.status == "completed" else 0},
                "result": record.result if include_result else None,
            }


_RUNTIME_LOCK = threading.Lock()
_RUNTIMES: weakref.WeakKeyDictionary[JobService, AllowanceAnalysisRuntime] = (
    weakref.WeakKeyDictionary()
)


def get_allowance(
    request: AllowanceRequest,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    now: datetime | None = None,
    job_service: JobService | None = None,
    runtime: AllowanceAnalysisRuntime | None = None,
) -> AllowanceResult:
    """Execute one bounded allowance operation over canonical aggregate state."""
    resolved_now = now or datetime.now(timezone.utc)
    with _open_database(db_path) as connection:
        start_at, end_at = _range_bounds(connection, request.range)
        if request.operation == "status":
            payload = _status(connection, now=resolved_now)
            return _result(payload, start_at=None, end_at=end_at)
        if request.operation == "series":
            payload = build_allowance_series(
                connection,
                now=end_at,
                range_preset=request.range,
                start_at=start_at.isoformat(),
                end_at=end_at.isoformat(),
                window_kind=request.window,
                include_archived=False,
            )
            return _result(payload, start_at=start_at, end_at=end_at)
        if request.operation == "evidence":
            payload = build_allowance_evidence(
                connection,
                now=end_at,
                privacy_mode="strict",
                limit=request.limit,
                cursor=request.cursor,
                window_kind=request.window,
                cohort_id=None,
                start_at=start_at.isoformat(),
                end_at=end_at.isoformat(),
                order="desc",
                include_archived=False,
            )
            return _result(payload, start_at=start_at, end_at=end_at)
        identity = _analysis_identity(connection)
        snapshot_id = str(identity["snapshot_id"])
        if request.analysis_id is not None and request.analysis_id != snapshot_id:
            raise RequestValidationError(
                "analysis_id does not match the current persisted snapshot"
            )
        completed = _read_analysis(connection)
        if completed is not None:
            return _result(
                completed,
                start_at=None,
                end_at=end_at,
                analysis_id=snapshot_id,
            )
        if request.execution == "sync":
            built = _build_analysis_in_connection(connection)
            return _result(built, start_at=None, end_at=end_at, analysis_id=snapshot_id)

    if runtime is not None and job_service is not None and runtime.job_service is not job_service:
        raise RequestValidationError("runtime and polling JobService must be the same instance")
    service = job_service or (
        runtime.job_service if runtime is not None else _default_job_service()
    )
    coordinator = runtime or _runtime_for(service)
    semantic_key = _analysis_semantic_key(identity)
    job = coordinator.start(
        semantic_key=semantic_key,
        source_revision=str(identity["source_revision"]),
        worker=lambda: _build_analysis(db_path),
    )
    return AllowanceResult(
        payload=job.to_payload(),
        result_schema=job.schema,
        range_start=None,
        range_end=end_at.isoformat(),
        analysis_id=snapshot_id,
    )


def _status(connection: sqlite3.Connection, *, now: datetime) -> dict[str, object]:
    payload = build_allowance_status(
        connection,
        now=now,
        privacy_mode="strict",
        include_archived=False,
    )
    if payload.get("data_state") in {"stale", "empty"}:
        payload["next"] = {
            "action": "usage_refresh_start",
            "status_action": "usage_refresh_status",
            "then": "usage_allowance_status",
            "poll_after_ms": 60_000,
        }
    else:
        seconds = int(dict(payload.get("next") or {}).get("poll_after_seconds", 30))
        payload["next"] = {"action": "usage_allowance_status", "poll_after_ms": seconds * 1_000}
    return payload


def _result(
    payload: Mapping[str, object],
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    analysis_id: str | None = None,
) -> AllowanceResult:
    return AllowanceResult(
        payload=payload,
        result_schema=str(payload["schema"]),
        range_start=start_at.isoformat() if start_at is not None else None,
        range_end=end_at.isoformat() if end_at is not None else None,
        analysis_id=analysis_id,
    )


def _analysis_identity(connection: sqlite3.Connection) -> dict[str, object]:
    return allowance_analysis_request(
        connection,
        rate_card_revision=None,
        archive_scope="active",
        window_kind="weekly",
        cohort_key="codex",
        forecast_horizon=1,
        parameters=None,
    )


def _read_analysis(connection: sqlite3.Connection) -> dict[str, object] | None:
    return read_allowance_analysis(
        connection,
        rate_card_revision=None,
        archive_scope="active",
        window_kind="weekly",
        cohort_key="codex",
        forecast_horizon=1,
        parameters=None,
    )


def _build_analysis_in_connection(connection: sqlite3.Connection) -> dict[str, object]:
    return build_allowance_analysis(
        connection,
        rate_card_revision=None,
        archive_scope="active",
        window_kind="weekly",
        cohort_key="codex",
        forecast_horizon=1,
        parameters=None,
    )


def _analysis_semantic_key(identity: Mapping[str, object]) -> str:
    dimensions = {
        key: identity.get(key)
        for key in (
            "snapshot_id",
            "source_revision",
            "model_version",
            "rate_card_revision",
            "data_as_of",
            "parameters",
        )
    }
    return request_hash(json.dumps(dimensions, sort_keys=True, separators=(",", ":")))


def _build_analysis(db_path: Path) -> Mapping[str, object]:
    with _open_database(db_path) as connection:
        return _build_analysis_in_connection(connection)


def _range_bounds(connection: sqlite3.Connection, range_preset: str) -> tuple[datetime, datetime]:
    row = connection.execute(
        "SELECT latest_observed_at FROM allowance_source_state WHERE state_id=1"
    ).fetchone()
    end = _parse_timestamp(row[0]) if row and row[0] else _EPOCH
    return end - _RANGE_DELTAS[range_preset], end


def _parse_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RequestValidationError("allowance source timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise RequestValidationError("allowance source timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@contextmanager
def _open_database(db_path: Path) -> Iterator[sqlite3.Connection]:
    if db_path.exists() or db_path.is_symlink():
        with connect(db_path) as connection:
            yield connection
        return
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    try:
        yield connection
    finally:
        connection.close()


def _runtime_for(job_service: JobService) -> AllowanceAnalysisRuntime:
    with _RUNTIME_LOCK:
        runtime = _RUNTIMES.get(job_service)
        if runtime is None:
            runtime = AllowanceAnalysisRuntime(job_service)
            _RUNTIMES[job_service] = runtime
        return runtime


def _default_job_service() -> JobService:
    from codex_usage_tracker.application.refresh import default_job_service

    return default_job_service()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
