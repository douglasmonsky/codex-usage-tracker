"""Thread-safe observational facade over existing job registries."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import replace
from typing import cast

from codex_usage_tracker.core.contracts import MessageV1, enforce_payload_budget, serialized_size
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.models import JobAdapter, JobHandle, JobKind, JobStatusV1

MAX_COMPACT_STATUS_BYTES = 16 * 1024
MAX_SEMANTIC_JOBS = 256
_STATE_RANK = {"queued": 0, "running": 1, "completed": 2, "failed": 2, "cancelled": 2}
_EPOCH = "1970-01-01T00:00:00Z"
_REQUEST_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


class JobService:
    """Register adapters and normalize status without changing legacy registries."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handles: dict[str, JobHandle] = {}
        self._versions: dict[str, int] = {}
        self._last: dict[str, JobStatusV1] = {}
        self._semantic: OrderedDict[str, str] = OrderedDict()

    def register(self, *, kind: JobKind, job_id: str, adapter: JobAdapter) -> None:
        result_schema = getattr(adapter, "result_schema", None)
        result_budget = getattr(adapter, "result_budget", 64 * 1024)
        handle = JobHandle(
            kind=kind,
            job_id=job_id,
            adapter=adapter,
            result_schema=result_schema if isinstance(result_schema, str) else None,
            result_budget=cast(int, result_budget),
        )
        with self._lock:
            existing = self._handles.get(job_id)
            if existing is not None and existing.kind != kind:
                raise ValueError("job_id is already registered with a different kind")
            self._handles[job_id] = handle
            self._versions[job_id] = self._versions.get(job_id, 0) + 1
            self._last.pop(job_id, None)

    def register_semantic(
        self, *, kind: JobKind, job_id: str, adapter: JobAdapter, semantic_key: str
    ) -> None:
        if not _REQUEST_HASH.fullmatch(semantic_key):
            raise ValueError("semantic_key must be a sha256 fingerprint")
        self.register(kind=kind, job_id=job_id, adapter=adapter)
        with self._lock:
            self._semantic[semantic_key] = job_id
            self._semantic.move_to_end(semantic_key)
            while len(self._semantic) > MAX_SEMANTIC_JOBS:
                _, evicted_id = self._semantic.popitem(last=False)
                if evicted_id not in self._semantic.values():
                    self._handles.pop(evicted_id, None)
                    self._versions.pop(evicted_id, None)
                    self._last.pop(evicted_id, None)

    def reusable(
        self, semantic_key: str, *, source_revision: str | None, result_schema: str
    ) -> JobStatusV1 | None:
        with self._lock:
            job_id = self._semantic.get(semantic_key)
            handle = self._handles.get(job_id) if job_id is not None else None
        if job_id is None or handle is None or handle.result_schema != result_schema:
            return None
        compact = self.status(job_id)
        if compact.source_revision != source_revision or compact.state in {"failed", "cancelled"}:
            return None
        if compact.state in {"queued", "running"}:
            return compact
        if compact.state != "completed":
            return None
        completed = self.status(job_id, include_result=True)
        if completed.result_schema != result_schema or completed.result is None:
            return None
        return completed

    def discard_semantic_job(self, job_id: str) -> None:
        with self._lock:
            for key, indexed_id in tuple(self._semantic.items()):
                if indexed_id == job_id:
                    self._semantic.pop(key, None)
            self._handles.pop(job_id, None)
            self._versions.pop(job_id, None)
            self._last.pop(job_id, None)

    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1:
        for _attempt in range(3):
            with self._lock:
                handle = self._handles.get(job_id)
                version = self._versions.get(job_id, 0)
            if handle is None:
                return _enforce_boundaries(_not_found(job_id), None, include_result=False)

            candidate = _read_candidate(handle, include_result=include_result)

            with self._lock:
                if self._handles.get(job_id) is not handle or self._versions.get(job_id) != version:
                    continue
                status = _monotonic(self._last.get(job_id), candidate)
                self._last[job_id] = replace(status, result=None)
            return _enforce_boundaries(status, handle, include_result=include_result)
        return _enforce_boundaries(_registration_changed(job_id), None, include_result=False)


def _read_candidate(handle: JobHandle, *, include_result: bool) -> JobStatusV1:
    compact = _read_adapter(handle, include_result=False)
    if not include_result or compact.state != "completed":
        return replace(compact, result=None)
    detailed = _read_adapter(handle, include_result=True)
    if detailed.state != "completed":
        return replace(compact, result=None)
    return replace(compact, result=detailed.result, result_schema=detailed.result_schema)


def _read_adapter(handle: JobHandle, *, include_result: bool) -> JobStatusV1:
    try:
        payload = handle.adapter.status(handle.job_id, include_result=include_result)
        return JobStatusV1.from_mapping(payload)
    except Exception:  # noqa: BLE001 - facade failures must stay stable and privacy-safe.
        return _adapter_failed(handle)


def _monotonic(previous: JobStatusV1 | None, current: JobStatusV1) -> JobStatusV1:
    if previous is None:
        return current
    previous_terminal = previous.state in {"completed", "failed", "cancelled"}
    if previous_terminal:
        return replace(
            previous,
            result=current.result if current.state == previous.state else None,
        )
    if _STATE_RANK[current.state] < _STATE_RANK[previous.state]:
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


def _enforce_boundaries(
    status: JobStatusV1, handle: JobHandle | None, *, include_result: bool
) -> JobStatusV1:
    if not include_result or status.state != "completed":
        compact = replace(status, result=None)
        enforce_payload_budget(compact.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
        return compact
    if status.result is None or handle is None:
        compact = replace(
            status,
            result=None,
            error=MessageV1(
                code="job.result_unavailable",
                severity="warning",
                message="The completed job has no result available through this adapter.",
            ),
        )
        enforce_payload_budget(compact.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
        return compact
    try:
        actual = serialized_size(status.to_payload())
    except (TypeError, ValueError):
        compact = replace(
            status,
            result=None,
            error=MessageV1(
                code="job.result_unsafe",
                severity="warning",
                message="The completed result could not be serialized safely.",
            ),
        )
        enforce_payload_budget(compact.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
        return compact
    if actual > handle.result_budget:
        compact = replace(
            status,
            result=None,
            error=MessageV1(
                code="job.result_too_large",
                severity="warning",
                message="The completed result exceeds its originating tool budget.",
            ),
        )
        enforce_payload_budget(compact.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
        return compact
    return status


def _not_found(job_id: str) -> JobStatusV1:
    bounded_job_id = f"unknown-{request_hash(job_id)[-24:]}"
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


def _registration_changed(job_id: str) -> JobStatusV1:
    return JobStatusV1(
        job_id=f"changed-{request_hash(job_id)[-24:]}",
        kind="diagnostic",
        state="failed",
        progress_percent=0,
        stage="registration_changed",
        source_revision=None,
        request_hash=request_hash(job_id),
        created_at=_EPOCH,
        updated_at=_EPOCH,
        completed_at=_EPOCH,
        retryable=True,
        error=MessageV1(
            code="job.registration_changed",
            severity="warning",
            message="The job registration changed while status was being read.",
        ),
        result_schema=None,
        result=None,
    )


def _adapter_failed(handle: JobHandle) -> JobStatusV1:
    fingerprint = getattr(handle.adapter, "request_hash", None)
    safe_hash = (
        fingerprint
        if isinstance(fingerprint, str) and _REQUEST_HASH.fullmatch(fingerprint)
        else request_hash(handle.job_id)
    )
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
