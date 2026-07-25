"""Bounded refresh planning and application-owned asynchronous coordination."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, Literal, TypeVar

from codex_usage_tracker.allowance_intelligence.materialization import (
    sync_refresh_allowance_intelligence,
)
from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.protocols import SourceRepository
from codex_usage_tracker.application.refresh_launcher import (
    DetachedRefreshLauncher,
    detached_refresh_launcher,
)
from codex_usage_tracker.application.refresh_observability import (
    pending_source_tail as _pending_source_tail,
)
from codex_usage_tracker.application.refresh_observability import (
    refresh_source_revision as _refresh_source_revision,
)
from codex_usage_tracker.application.requests import RefreshRequest, RequestScope
from codex_usage_tracker.core.contracts import payload_mapping
from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.jobs.adapters import RefreshJobAdapter, request_hash
from codex_usage_tracker.jobs.models import JobStatusV1
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.parser.api import find_session_logs
from codex_usage_tracker.store.api import refresh_usage_index as _refresh_usage_index
from codex_usage_tracker.store.connection import connect_read_only
from codex_usage_tracker.store.refresh_parse import RefreshProgressCallback
from codex_usage_tracker.store.sources import source_logs_requiring_parse

MAX_SYNC_SOURCE_FILES = 4
MAX_SYNC_ADDED_BYTES = 4_194_304
REFRESH_SCHEMA = "codex-usage-tracker.refresh.v2"
REFRESH_JOB_RESULT_BUDGET = 48 * 1024

T = TypeVar("T")


def refresh_usage_index(
    codex_home: Path,
    db_path: Path,
    include_archived: bool = False,
    aggregate_only: bool = False,
    otel_dir: Path | None = None,
    progress_callback: RefreshProgressCallback | None = None,
) -> RefreshResult:
    """Refresh store state and materialize application-owned allowance facts."""
    return _refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        otel_dir=otel_dir if otel_dir is not None else db_path.parent / "otel",
        progress_callback=progress_callback,
        derived_fact_sync=sync_refresh_allowance_intelligence,
    )


RefreshFunction = Callable[..., RefreshResult]
Planner = Callable[..., "RefreshPlan"]


@dataclass(frozen=True)
class RefreshPlan:
    execution: Literal["sync", "async"]
    reason: str
    changed_source_files: int
    added_bytes: int

    def to_payload(self) -> dict[str, object]:
        return {
            "execution": self.execution,
            "reason": self.reason,
            "changed_source_files": self.changed_source_files,
            "added_bytes": self.added_bytes,
        }


@dataclass(frozen=True)
class CompletedOrJob(Generic[T]):
    result: T | None = None
    job: JobStatusV1 | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.job is None):
            raise ValueError("exactly one of result or job is required")


@dataclass
class _JobRecord:
    job_id: str
    request_key: str
    status: str
    created_at: str
    updated_at: str
    progress_percent: int = 0
    stage: str = "queued"
    result: dict[str, object] | None = None


class RefreshCoordinator:
    """Coordinate refresh work through the generic durable job boundary."""

    def __init__(self, job_service: JobService | None = None) -> None:
        self.job_service = job_service or JobService()
        self._lock = threading.RLock()
        self._records: dict[str, _JobRecord] = {}
        self._active: dict[str, str] = {}

    def start(
        self,
        request_key: str,
        worker: Callable[[RefreshProgressCallback], dict[str, object]],
        *,
        source_revision: str,
        request: RefreshRequest,
        detached_launcher: DetachedRefreshLauncher | None = None,
    ) -> JobStatusV1:
        with self._lock:
            active_id = self._active.get(request_key)
            if active_id is not None:
                active = self._records.get(active_id)
                if active is not None and active.status in {"queued", "running"}:
                    return self.job_service.status(active_id)
            job_id = secrets.token_urlsafe(18)
            now = _utc_now()
            record = _JobRecord(job_id, request_key, "queued", now, now)
            self._records[job_id] = record
            adapter = RefreshJobAdapter(
                self._reader,
                request_hash=request_hash(request_key),
                result_schema=REFRESH_SCHEMA,
                result_budget=REFRESH_JOB_RESULT_BUDGET,
            )
            registration = self.job_service.register_semantic(
                request_hash(request_key),
                kind="refresh",
                job_id=job_id,
                adapter=adapter,
                source_revision=source_revision,
                request_schema="refresh.request.v1",
                request={
                    "history": request.history,
                    "aggregate_only": request.aggregate_only,
                    "execution": request.execution,
                },
            )
            if not registration.should_start:
                self._records.pop(job_id, None)
                return registration.status
            if detached_launcher is not None:
                self._records.pop(job_id, None)
                self.job_service.discard_semantic_job(job_id)
                detached_launcher(job_id)
                return registration.status
            self._active[request_key] = job_id
        threading.Thread(
            target=self._run,
            args=(record, worker),
            daemon=False,
            name=f"usage-refresh-{job_id[:8]}",
        ).start()
        return registration.status

    def _run(
        self,
        record: _JobRecord,
        worker: Callable[[RefreshProgressCallback], dict[str, object]],
    ) -> None:
        self._update(record, status="running", stage="planning", progress_percent=0)

        def progress(payload: dict[str, object]) -> None:
            raw_percent = payload.get("percent", record.progress_percent)
            percent = int(raw_percent) if isinstance(raw_percent, int | float) else 0
            phase = payload.get("phase")
            stage = str(phase) if isinstance(phase, str) else record.stage
            self._update(
                record,
                status="running",
                stage=stage,
                progress_percent=max(0, min(99, percent)),
            )

        try:
            result = worker(progress)
        except Exception:  # noqa: BLE001 - job errors cross a privacy-safe adapter boundary.
            self._update(
                record,
                status="failed",
                stage="failed",
                progress_percent=record.progress_percent,
            )
        else:
            self._update(
                record,
                status="completed",
                stage="complete",
                progress_percent=100,
                result=result,
            )
        finally:
            with self._lock:
                if self._active.get(record.request_key) == record.job_id:
                    self._active.pop(record.request_key, None)

    def _update(
        self,
        record: _JobRecord,
        *,
        status: str,
        stage: str,
        progress_percent: int,
        result: dict[str, object] | None = None,
    ) -> None:
        with self._lock:
            record.status = status
            record.updated_at = _utc_now()
            record.stage = stage
            record.progress_percent = progress_percent
            record.result = result
        self.job_service.checkpoint(record.job_id)

    def _reader(self, job_id: str, *, include_result: bool = False) -> dict[str, object]:
        with self._lock:
            record = self._records[job_id]
            return {
                "job_id": record.job_id,
                "status": record.status,
                "stage": record.stage,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "progress": {
                    "phase": record.stage,
                    "percent": record.progress_percent,
                },
                "completed_at": (
                    record.updated_at if record.status in {"completed", "failed"} else None
                ),
                "result": record.result if include_result else None,
            }


_DEFAULT_COORDINATOR = RefreshCoordinator()
_COORDINATORS_GUARD = threading.Lock()
_COORDINATORS_BY_SERVICE: weakref.WeakKeyDictionary[JobService, RefreshCoordinator] = (
    weakref.WeakKeyDictionary()
)
_REFRESH_LOCKS_GUARD = threading.Lock()
_REFRESH_LOCKS: dict[str, threading.Lock] = {}


def default_job_service() -> JobService:
    return _DEFAULT_COORDINATOR.job_service


def plan_refresh(
    request: RefreshRequest,
    *,
    codex_home: Path,
    db_path: Path,
    source_repository: SourceRepository | None = None,
) -> RefreshPlan:
    """Plan from bounded file/store facts without creating or migrating a database."""
    logs = (
        source_repository.session_logs(include_archived=request.history == "all")
        if source_repository is not None
        else find_session_logs(codex_home, include_archived=request.history == "all")
    )
    if not db_path.exists():
        return RefreshPlan(
            "sync" if not logs else "async",
            "no_changes" if not logs else "untracked_source",
            len(logs),
            0,
        )
    if not db_path.is_file():
        return RefreshPlan("async", "uncertain_database", len(logs), 0)
    try:
        for path in logs:
            path.stat()
            if not os.access(path, os.R_OK):
                raise OSError("source is unreadable")
        with connect_read_only(db_path) as conn:
            archived_clause = "" if request.history == "all" else "WHERE is_archived = 0"
            tracked = {
                str(row["source_file"])
                for row in conn.execute(
                    f"SELECT source_file FROM source_files {archived_clause}"  # nosec B608
                )
            }
            discovered = {str(path) for path in logs}
            if tracked - discovered:
                return RefreshPlan("async", "missing_source", len(tracked - discovered), 0)
            plans = source_logs_requiring_parse(conn, logs)
    except (OSError, sqlite3.Error, ValueError):
        return RefreshPlan("async", "uncertain_source_state", len(logs), 0)
    if any(plan.replace_existing for plan in plans):
        return RefreshPlan("async", "unsafe_source_change", len(plans), 0)
    try:
        added_bytes = sum(
            max(
                0,
                (plan.end_byte if plan.end_byte is not None else plan.path.stat().st_size)
                - plan.start_byte,
            )
            for plan in plans
        )
    except OSError:
        return RefreshPlan("async", "uncertain_source_state", len(plans), 0)
    if len(plans) > MAX_SYNC_SOURCE_FILES:
        return RefreshPlan("async", "source_limit", len(plans), added_bytes)
    if added_bytes > MAX_SYNC_ADDED_BYTES:
        return RefreshPlan("async", "byte_limit", len(plans), added_bytes)
    return RefreshPlan(
        "sync", "no_changes" if not plans else "append_safe", len(plans), added_bytes
    )


def refresh_usage(
    request: RefreshRequest,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    source_repository: SourceRepository | None = None,
    job_service: JobService | None = None,
    coordinator: RefreshCoordinator | None = None,
    refresh_fn: RefreshFunction = refresh_usage_index,
    planner: Planner = plan_refresh,
) -> CompletedOrJob[dict[str, object]]:
    """Complete a bounded refresh or return one truthful registered job status."""
    runtime = coordinator
    if runtime is None:
        runtime = (
            _DEFAULT_COORDINATOR if job_service is None else _coordinator_for_service(job_service)
        )
    elif job_service is not None and runtime.job_service is not job_service:
        raise ValueError("coordinator and job_service must share one service")
    lock = _refresh_lock(db_path)

    def execute(
        plan: RefreshPlan,
        progress_callback: RefreshProgressCallback | None = None,
    ) -> dict[str, object]:
        result = refresh_fn(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=request.history == "all",
            aggregate_only=request.aggregate_only,
            progress_callback=progress_callback,
        )
        return _completed_payload(
            request,
            result,
            plan,
            codex_home,
            db_path,
            pricing_path,
        )

    if request.execution == "sync":
        with lock:
            observed = _plan_refresh(
                planner,
                request,
                codex_home=codex_home,
                db_path=db_path,
                source_repository=source_repository,
            )
            explicit = RefreshPlan(
                "sync", "explicit_sync", observed.changed_source_files, observed.added_bytes
            )
            return CompletedOrJob(result=execute(explicit))
    if request.execution == "auto":
        with lock:
            observed = _plan_refresh(
                planner,
                request,
                codex_home=codex_home,
                db_path=db_path,
                source_repository=source_repository,
            )
            if observed.execution == "sync":
                return CompletedOrJob(result=execute(observed))

    key = _refresh_request_identity(
        request,
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
    )

    def worker(progress_callback: RefreshProgressCallback) -> dict[str, object]:
        with lock:
            observed = _plan_refresh(
                planner,
                request,
                codex_home=codex_home,
                db_path=db_path,
                source_repository=source_repository,
            )
            async_plan = RefreshPlan(
                "async",
                "explicit_async" if request.execution == "async" else observed.reason,
                observed.changed_source_files,
                observed.added_bytes,
            )
            return execute(async_plan, progress_callback)

    source_revision = _refresh_source_revision(
        request,
        codex_home=codex_home,
        source_repository=source_repository,
    )
    detached_launcher = detached_refresh_launcher(
        request=request,
        source_revision=source_revision,
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        job_service=runtime.job_service,
        enabled=refresh_fn is refresh_usage_index and planner is plan_refresh,
    )
    return CompletedOrJob(
        job=runtime.start(
            key,
            worker,
            source_revision=source_revision,
            request=request,
            detached_launcher=detached_launcher,
        )
    )


def _plan_refresh(
    planner: Planner,
    request: RefreshRequest,
    *,
    codex_home: Path,
    db_path: Path,
    source_repository: SourceRepository | None,
) -> RefreshPlan:
    if source_repository is None:
        return planner(request, codex_home=codex_home, db_path=db_path)
    return planner(
        request,
        codex_home=codex_home,
        db_path=db_path,
        source_repository=source_repository,
    )


def _completed_payload(
    request: RefreshRequest,
    result: RefreshResult,
    plan: RefreshPlan,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
) -> dict[str, object]:
    context = build_request_context(
        db_path=db_path,
        pricing_path=pricing_path,
        scope=RequestScope(history=request.history),
    )
    source_boundary = {
        "changed_source_files": plan.changed_source_files,
        "added_bytes": plan.added_bytes,
        "newline_aligned": True,
        "exclusive_end": True,
    }
    tail = _pending_source_tail(
        request,
        codex_home=codex_home,
        db_path=db_path,
    )
    return {
        "schema": REFRESH_SCHEMA,
        "refresh": {
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "skipped_events": result.skipped_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "parser_diagnostics": dict(result.parser_diagnostics),
            "fixed_source_boundary": source_boundary,
            **tail,
        },
        "planner": plan.to_payload(),
        "scope": payload_mapping(context.scope),
        "freshness": payload_mapping(context.freshness),
        "accounting": payload_mapping(context.accounting),
    }


def _refresh_lock(db_path: Path) -> threading.Lock:
    key = str(db_path.resolve())
    with _REFRESH_LOCKS_GUARD:
        return _REFRESH_LOCKS.setdefault(key, threading.Lock())


def _refresh_request_identity(
    request: RefreshRequest,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
) -> str:
    payload = {
        "aggregate_only": request.aggregate_only,
        "codex_home": _normalized_path(codex_home),
        "db_path": _normalized_path(db_path),
        "execution": request.execution,
        "history": request.history,
        "pricing_path": _normalized_path(pricing_path),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"refresh-v1:{hashlib.sha256(encoded).hexdigest()}"


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))





def _coordinator_for_service(job_service: JobService) -> RefreshCoordinator:
    with _COORDINATORS_GUARD:
        coordinator = _COORDINATORS_BY_SERVICE.get(job_service)
        if coordinator is None:
            coordinator = RefreshCoordinator(job_service)
            _COORDINATORS_BY_SERVICE[job_service] = coordinator
        return coordinator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
