"""Thread-safe observational facade over existing job registries."""

from __future__ import annotations

import threading
from dataclasses import replace

from codex_usage_tracker.core.contracts import MessageV1, enforce_payload_budget, serialized_size
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.models import JobAdapter, JobHandle, JobKind, JobStatusV1

MAX_COMPACT_STATUS_BYTES = 16 * 1024
_STATE_RANK = {"queued": 0, "running": 1, "completed": 2, "failed": 2, "cancelled": 2}
_EPOCH = "1970-01-01T00:00:00Z"


class JobService:
    """Register adapters and normalize status without changing legacy registries."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handles: dict[str, JobHandle] = {}
        self._last: dict[str, JobStatusV1] = {}

    def register(self, *, kind: JobKind, job_id: str, adapter: JobAdapter) -> None:
        result_schema = getattr(adapter, "result_schema", None)
        result_budget = getattr(adapter, "result_budget", 64 * 1024)
        handle = JobHandle(
            kind=kind,
            job_id=job_id,
            adapter=adapter,
            result_schema=result_schema if isinstance(result_schema, str) else None,
            result_budget=result_budget if isinstance(result_budget, int) else 64 * 1024,
        )
        with self._lock:
            existing = self._handles.get(job_id)
            if existing is not None and existing.kind != kind:
                raise ValueError("job_id is already registered with a different kind")
            self._handles[job_id] = handle

    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1:
        with self._lock:
            handle = self._handles.get(job_id)
            if handle is None:
                status = _not_found(job_id)
                enforce_payload_budget(status.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
                return status
            try:
                payload = handle.adapter.status(job_id, include_result=include_result)
                normalized = JobStatusV1.from_mapping(payload)
            except Exception:  # noqa: BLE001 - facade failures must stay stable and privacy-safe.
                normalized = _adapter_failed(handle)
            previous = self._last.get(job_id)
            status = _monotonic(previous, normalized)
            status = _bounded_result(status, handle, include_result=include_result)
            if not include_result:
                enforce_payload_budget(status.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
            self._last[job_id] = replace(status, result=None)
            return status


def _monotonic(previous: JobStatusV1 | None, current: JobStatusV1) -> JobStatusV1:
    if previous is None:
        return current
    previous_terminal = previous.state in {"completed", "failed", "cancelled"}
    terminal_changed = previous_terminal and current.state != previous.state
    if terminal_changed or _STATE_RANK[current.state] < _STATE_RANK[previous.state]:
        return replace(
            current,
            state=previous.state,
            stage=previous.stage,
            progress_percent=previous.progress_percent,
            completed_at=previous.completed_at,
            retryable=previous.retryable,
            error=previous.error,
            result_schema=previous.result_schema,
            result=None,
        )
    return replace(
        current, progress_percent=max(previous.progress_percent, current.progress_percent)
    )


def _bounded_result(status: JobStatusV1, handle: JobHandle, *, include_result: bool) -> JobStatusV1:
    if not include_result or status.state != "completed":
        return replace(status, result=None)
    if status.result is None:
        return replace(
            status,
            error=MessageV1(
                code="job.result_unavailable",
                severity="warning",
                message="The completed job has no result available through this adapter.",
            ),
        )
    if serialized_size(status.result) > handle.result_budget:
        return replace(
            status,
            result=None,
            error=MessageV1(
                code="job.result_too_large",
                severity="warning",
                message="The completed result exceeds its originating tool budget.",
            ),
        )
    return status


def _not_found(job_id: str) -> JobStatusV1:
    bounded_job_id = job_id if len(job_id) <= 128 else f"{job_id[:48]}…{request_hash(job_id)[-64:]}"
    return JobStatusV1(
        job_id=bounded_job_id,
        kind="diagnostic",
        state="failed",
        progress_percent=0,
        stage="not_found",
        source_revision=None,
        request_hash=request_hash(job_id),
        created_at=_EPOCH,
        updated_at=_EPOCH,
        completed_at=_EPOCH,
        retryable=False,
        error=MessageV1(
            code="job.not_found",
            severity="blocking",
            message="The job is not registered with this service.",
        ),
        result_schema=None,
        result=None,
    )


def _adapter_failed(handle: JobHandle) -> JobStatusV1:
    fingerprint = getattr(handle.adapter, "request_hash", None)
    safe_hash = fingerprint if isinstance(fingerprint, str) else request_hash(handle.job_id)
    return JobStatusV1(
        job_id=handle.job_id,
        kind=handle.kind,
        state="failed",
        progress_percent=0,
        stage="adapter_failed",
        source_revision=None,
        request_hash=safe_hash,
        created_at=_EPOCH,
        updated_at=_EPOCH,
        completed_at=_EPOCH,
        retryable=True,
        error=MessageV1(
            code="job.adapter_failed",
            severity="blocking",
            message="The originating job registry could not be read safely.",
        ),
        result_schema=None,
        result=None,
    )
