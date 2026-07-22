"""Pure normalizers for existing subsystem job payloads."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from codex_usage_tracker.core.contracts import MessageV1
from codex_usage_tracker.jobs.models import JobKind, JobState

StatusReader = Callable[..., Mapping[str, object]]
_EPOCH = "1970-01-01T00:00:00Z"
_STAGE_UNSAFE = re.compile(r"[^a-z0-9_.-]+")


def request_hash(value: object) -> str:
    """Return a privacy-safe one-way request fingerprint."""
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class _PayloadAdapter:
    reader: StatusReader
    kind: JobKind
    request_hash: str
    result_schema: str
    result_budget: int
    family: str

    def status(self, job_id: str, *, include_result: bool = False) -> Mapping[str, object]:
        payload = self.reader(job_id, include_result=include_result)
        return _normalize(
            payload,
            job_id=job_id,
            kind=self.kind,
            request_fingerprint=self.request_hash,
            result_schema=self.result_schema,
            include_result=include_result,
            family=self.family,
        )


class RefreshJobAdapter(_PayloadAdapter):
    def __init__(
        self,
        reader: StatusReader,
        *,
        request_hash: str,
        result_schema: str = "codex-usage-tracker.refresh-result.v1",
        result_budget: int = 64 * 1024,
    ) -> None:
        super().__init__(reader, "refresh", request_hash, result_schema, result_budget, "refresh")


class AnalysisJobAdapter(_PayloadAdapter):
    def __init__(
        self,
        reader: StatusReader,
        *,
        kind: JobKind,
        request_hash: str,
        result_schema: str = "codex-usage-tracker.analysis-result.v1",
        result_budget: int = 64 * 1024,
    ) -> None:
        if kind not in {"analysis", "allowance", "diagnostic"}:
            raise ValueError("analysis adapter kind is invalid")
        super().__init__(reader, kind, request_hash, result_schema, result_budget, "analysis")


class CompressionJobAdapter(_PayloadAdapter):
    def __init__(
        self,
        reader: StatusReader,
        *,
        request_hash: str,
        result_schema: str = "codex-usage-tracker.compression-profile.v1",
        result_budget: int = 128 * 1024,
    ) -> None:
        super().__init__(
            reader, "compression", request_hash, result_schema, result_budget, "compression"
        )


class DogfoodJobAdapter(_PayloadAdapter):
    def __init__(
        self,
        reader: StatusReader,
        *,
        request_hash: str,
        result_schema: str = "codex-usage-tracker.diagnostic-result.v1",
        result_budget: int = 64 * 1024,
    ) -> None:
        super().__init__(
            reader, "diagnostic", request_hash, result_schema, result_budget, "dogfood"
        )


def _normalize(
    payload: Mapping[str, object],
    *,
    job_id: str,
    kind: JobKind,
    request_fingerprint: str,
    result_schema: str,
    include_result: bool,
    family: str,
) -> dict[str, object]:
    raw_state = str(payload.get("status") or "missing")
    state, error, retryable = _state(raw_state)
    progress = _progress(payload, family=family, state=state)
    updated_at = _timestamp(payload.get("updated_at"))
    created_at = _timestamp(payload.get("created_at") or payload.get("started_at"), updated_at)
    completed_at = _terminal_timestamp(payload, state, updated_at)
    result = _result(payload, family=family) if include_result and state == "completed" else None
    return {
        "job_id": job_id,
        "kind": kind,
        "state": state,
        "progress_percent": progress,
        "stage": _safe_stage(payload, family=family, state=state),
        "source_revision": _optional_string(payload.get("source_revision")),
        "request_hash": request_fingerprint,
        "created_at": created_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "retryable": retryable,
        "error": error,
        "result_schema": result_schema if state == "completed" else None,
        "result": result,
    }


def _state(raw: str) -> tuple[JobState, MessageV1 | None, bool]:
    if raw in {"pending", "queued"}:
        return "queued", None, False
    if raw == "running":
        return "running", None, False
    if raw in {"completed", "completed_with_warnings"}:
        warning = (
            MessageV1(
                code="job.completed_with_warnings",
                severity="warning",
                message="The job completed with warnings.",
            )
            if raw == "completed_with_warnings"
            else None
        )
        return "completed", warning, False
    if raw == "interrupted":
        return (
            "cancelled",
            MessageV1(
                code="job.interrupted",
                severity="warning",
                message="The originating worker no longer owns this job.",
            ),
            True,
        )
    if raw in {"missing", "not_found"}:
        return (
            "failed",
            MessageV1(
                code="job.not_found",
                severity="blocking",
                message="The job was not found in its originating registry.",
            ),
            False,
        )
    return (
        "failed",
        MessageV1(
            code="job.failed",
            severity="blocking",
            message="The job failed in its originating subsystem.",
        ),
        True,
    )


def _progress(payload: Mapping[str, object], *, family: str, state: JobState) -> int:
    value: object = payload.get("progress_percent")
    if family == "dogfood":
        value = payload.get("percent_complete")
    elif family in {"refresh", "analysis"} or (family == "compression" and value is None):
        progress = payload.get("progress")
        value = progress.get("percent") if isinstance(progress, Mapping) else None
    if state == "completed":
        return 100
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        return 0
    return max(0, min(100, int(value)))


def _safe_stage(payload: Mapping[str, object], *, family: str, state: JobState) -> str:
    key = "current_stage" if family == "dogfood" else "stage"
    if family == "refresh":
        progress = payload.get("progress")
        raw = progress.get("phase") if isinstance(progress, Mapping) else None
    else:
        raw = payload.get(key)
    fallback = "complete" if state == "completed" else state
    normalized = _STAGE_UNSAFE.sub("_", str(raw or fallback).lower()).strip("_.-")
    return (normalized or fallback)[:64]


def _timestamp(value: object, fallback: str = _EPOCH) -> str:
    return value[:64] if isinstance(value, str) and value else fallback


def _terminal_timestamp(
    payload: Mapping[str, object], state: JobState, updated_at: str
) -> str | None:
    if state not in {"completed", "failed", "cancelled"}:
        return None
    return _timestamp(payload.get("completed_at") or payload.get("finished_at"), updated_at)


def _result(payload: Mapping[str, object], *, family: str) -> object | None:
    value = payload.get("public_profile") if family == "compression" else payload.get("result")
    return _safe_result(value)


def _safe_result(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_result(item)
            for key, item in value.items()
            if not _private_result_key(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_safe_result(item) for item in value]
    if isinstance(value, str) and (value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value)):
        return "[redacted-local-path]"
    return value


def _private_result_key(key: str) -> bool:
    normalized = key.lower()
    return any(
        marker in normalized
        for marker in ("path", "artifact", "request_key", "worker", "exception", "traceback")
    )


def _optional_string(value: object) -> str | None:
    return value[:256] if isinstance(value, str) and value else None
