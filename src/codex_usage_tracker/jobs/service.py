"""Thread-safe observational facade over existing job registries."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from codex_usage_tracker.core.contracts import MessageV1
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.models import (
    JobAdapter,
    JobHandle,
    JobKind,
    JobPersistence,
    JobRegistration,
    JobStatusV1,
)
from codex_usage_tracker.jobs.persistence import (
    NULL_SOURCE_REVISION,
    compatible_completed_result,
    enforce_status_boundaries,
    has_completed_result,
    is_reusable_compact,
    message_payload,
    persisted_status,
)

MAX_SEMANTIC_JOBS = 256
_STATE_RANK = {"queued": 0, "running": 1, "completed": 2, "failed": 2, "cancelled": 2}
_EPOCH = "1970-01-01T00:00:00Z"
_REQUEST_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


class JobService:
    """Register adapters and normalize status without changing legacy registries."""

    def __init__(
        self,
        repository: JobPersistence | None = None,
        *,
        recover_interrupted: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._handles: dict[str, JobHandle] = {}
        self._versions: dict[str, int] = {}
        self._last: dict[str, JobStatusV1] = {}
        self._semantic: OrderedDict[str, str] = OrderedDict()
        self._persisted_ids: set[str] = set()
        self._repository = repository
        if repository is not None and recover_interrupted:
            repository.recover_interrupted()
            repository.prune()

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
        self,
        semantic_key: str,
        *,
        kind: JobKind,
        job_id: str,
        adapter: JobAdapter,
        source_revision: str | None = None,
        request_schema: str = "job.request.v1",
        request: Mapping[str, object] | None = None,
    ) -> JobRegistration:
        if not _REQUEST_HASH.fullmatch(semantic_key):
            raise ValueError("semantic_key must be a sha256 fingerprint")
        repository = self._repository
        if repository is not None:
            result_schema = getattr(adapter, "result_schema", None)
            if not isinstance(result_schema, str):
                raise ValueError("persisted semantic jobs require a result schema")
            row, created = repository.create_or_reuse(
                job_id=job_id,
                job_kind=kind,
                semantic_key=semantic_key,
                source_revision=source_revision or NULL_SOURCE_REVISION,
                request_schema=request_schema,
                request=request or {},
                result_schema=result_schema,
            )
            persisted = persisted_status(row, include_result=True)
            if not created:
                return JobRegistration(status=persisted, should_start=False)
        self.register(kind=kind, job_id=job_id, adapter=adapter)
        with self._lock:
            if repository is not None:
                self._persisted_ids.add(job_id)
            self._semantic[semantic_key] = job_id
            self._semantic.move_to_end(semantic_key)
            while len(self._semantic) > MAX_SEMANTIC_JOBS:
                _, evicted_id = self._semantic.popitem(last=False)
                if evicted_id not in self._semantic.values():
                    self._handles.pop(evicted_id, None)
                    self._versions.pop(evicted_id, None)
                    self._last.pop(evicted_id, None)
        return JobRegistration(status=self.status(job_id), should_start=True)

    def reusable(
        self,
        semantic_key: str,
        *,
        source_revision: str | None,
        result_schema: str,
        kind: JobKind = "analysis",
    ) -> JobStatusV1 | None:
        durable = self._durable_reusable(
            semantic_key,
            source_revision=source_revision,
            result_schema=result_schema,
            kind=kind,
        )
        if durable is not None:
            return durable
        return self._memory_reusable(
            semantic_key,
            source_revision=source_revision,
            result_schema=result_schema,
        )

    def _durable_reusable(
        self,
        semantic_key: str,
        *,
        source_revision: str | None,
        result_schema: str,
        kind: JobKind,
    ) -> JobStatusV1 | None:
        repository = self._repository
        if repository is None:
            return None
        row = repository.find_reusable(
            job_kind=kind,
            semantic_key=semantic_key,
            source_revision=source_revision or NULL_SOURCE_REVISION,
            result_schema=result_schema,
        )
        if row is None:
            return None
        status = persisted_status(row, include_result=True)
        return status if status.state in {"queued", "running", "completed"} else None

    def _memory_reusable(
        self,
        semantic_key: str,
        *,
        source_revision: str | None,
        result_schema: str,
    ) -> JobStatusV1 | None:
        with self._lock:
            job_id = self._semantic.get(semantic_key)
            handle = self._handles.get(job_id) if job_id is not None else None
        if job_id is None:
            return None
        if handle is None:
            return None
        if handle.result_schema != result_schema:
            return None
        compact = self.status(job_id)
        if not is_reusable_compact(compact, source_revision=source_revision):
            return None
        if compact.state in {"queued", "running"}:
            return compact
        completed = self.status(job_id, include_result=True)
        return completed if has_completed_result(completed, result_schema=result_schema) else None

    def discard_semantic_job(self, job_id: str) -> None:
        with self._lock:
            for key, indexed_id in tuple(self._semantic.items()):
                if indexed_id == job_id:
                    self._semantic.pop(key, None)
            self._handles.pop(job_id, None)
            self._versions.pop(job_id, None)
            self._last.pop(job_id, None)
            self._persisted_ids.discard(job_id)

    def completed_results(
        self,
        *,
        kind: JobKind,
        result_schema: str,
        source_revision: str | None,
        limit: int = MAX_SEMANTIC_JOBS,
    ) -> tuple[Mapping[str, object], ...]:
        """Enumerate compatible completed results deterministically through a bounded read seam."""
        if type(limit) is not int or not 1 <= limit <= MAX_SEMANTIC_JOBS:
            raise ValueError(f"limit must be between 1 and {MAX_SEMANTIC_JOBS}")
        if self._repository is not None:
            return self._repository.completed_results(
                job_kind=kind,
                result_schema=result_schema,
                source_revision=source_revision or NULL_SOURCE_REVISION,
                limit=limit,
            )
        with self._lock:
            job_ids = sorted(
                job_id for job_id, handle in self._handles.items() if handle.kind == kind
            )[:limit]
        results: list[Mapping[str, object]] = []
        for job_id in job_ids:
            status = self.status(job_id, include_result=True)
            result = status.result
            if compatible_completed_result(
                status,
                source_revision=source_revision,
                result_schema=result_schema,
            ):
                results.append(cast(Mapping[str, object], result))
        return tuple(results)

    def checkpoint(self, job_id: str) -> JobStatusV1:
        """Persist one active adapter snapshot and return the durable view."""
        repository = self._repository
        with self._lock:
            handle = self._handles.get(job_id)
            persisted = job_id in self._persisted_ids
        if repository is None or not persisted:
            if handle is None:
                return _not_found(job_id)
            candidate = _read_candidate(handle, include_result=True)
            with self._lock:
                status = _monotonic(self._last.get(job_id), candidate)
                self._last[job_id] = replace(status, result=None)
            return enforce_status_boundaries(status, handle, include_result=True)
        if handle is None:
            row = repository.get(job_id, touch=True)
            return (
                persisted_status(row, include_result=True)
                if row is not None
                else _not_found(job_id)
            )
        candidate = _read_candidate(handle, include_result=True)
        row = repository.update_status(
            job_id,
            state=candidate.state,
            progress={
                "percent": candidate.progress_percent,
                "stage": candidate.stage,
            },
            result_schema=candidate.result_schema,
            result=candidate.result,
            error=message_payload(candidate.error),
        )
        persisted = persisted_status(row, include_result=True)
        with self._lock:
            self._last[job_id] = persisted
        return persisted

    def heartbeat(self, job_id: str) -> bool:
        """Extend the lease for one active job owned by this process."""
        repository = self._repository
        with self._lock:
            persisted = job_id in self._persisted_ids
        return repository.heartbeat(job_id) if repository is not None and persisted else False

    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1:
        repository = self._repository
        with self._lock:
            has_handle = job_id in self._handles
            is_persisted = job_id in self._persisted_ids
        if repository is not None and (not has_handle or is_persisted):
            durable = self._durable_status(
                job_id,
                has_handle=has_handle,
                include_result=include_result,
            )
            if durable is not None:
                return durable
        return self._memory_status(job_id, include_result=include_result)

    def _durable_status(
        self,
        job_id: str,
        *,
        has_handle: bool,
        include_result: bool,
    ) -> JobStatusV1 | None:
        repository = self._repository
        if repository is None:
            return None
        row = None if has_handle else repository.get(job_id, touch=True)
        if row is not None:
            status = persisted_status(row, include_result=include_result)
            return enforce_status_boundaries(status, None, include_result=include_result)
        if not has_handle:
            return None
        persisted = self.checkpoint(job_id)
        with self._lock:
            handle = self._handles.get(job_id)
        status = replace(persisted, result=persisted.result if include_result else None)
        return enforce_status_boundaries(status, handle, include_result=include_result)

    def _memory_status(self, job_id: str, *, include_result: bool) -> JobStatusV1:
        for _attempt in range(3):
            with self._lock:
                handle = self._handles.get(job_id)
                version = self._versions.get(job_id, 0)
            if handle is None:
                return enforce_status_boundaries(_not_found(job_id), None, include_result=False)

            candidate = _read_candidate(handle, include_result=include_result)

            with self._lock:
                if self._handles.get(job_id) is not handle or self._versions.get(job_id) != version:
                    continue
                status = _monotonic(self._last.get(job_id), candidate)
                self._last[job_id] = replace(status, result=None)
            return enforce_status_boundaries(status, handle, include_result=include_result)
        return enforce_status_boundaries(
            _registration_changed(job_id),
            None,
            include_result=False,
        )


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
