"""Conversion helpers at the generic job persistence boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from codex_usage_tracker.core.contracts import MessageV1, enforce_payload_budget, serialized_size
from codex_usage_tracker.core.contracts.common import MessageSeverity
from codex_usage_tracker.jobs.models import (
    MAX_RESULT_BUDGET_BYTES,
    JobHandle,
    JobKind,
    JobState,
    JobStatusV1,
)

NULL_SOURCE_REVISION = "source:none"
MAX_COMPACT_STATUS_BYTES = 16 * 1024


def persisted_status(
    row: Mapping[str, object],
    *,
    include_result: bool,
) -> JobStatusV1:
    """Convert one store-owned mapping into the generic job contract."""
    raw_state = str(row["status"])
    state = "failed" if raw_state == "interrupted" else raw_state
    progress = row.get("progress")
    progress_mapping = progress if isinstance(progress, Mapping) else {}
    return JobStatusV1(
        job_id=str(row["job_id"]),
        kind=cast(JobKind, str(row["job_kind"])),
        state=cast(JobState, state),
        progress_percent=int(progress_mapping.get("percent", 0)),
        stage=str(progress_mapping.get("stage", state)),
        source_revision=(
            None
            if str(row["source_revision"]) == NULL_SOURCE_REVISION
            else str(row["source_revision"])
        ),
        request_hash=str(row["semantic_key"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=(str(row["completed_at"]) if row.get("completed_at") is not None else None),
        retryable=raw_state in {"failed", "interrupted"},
        error=_persisted_message(row.get("error")),
        result_schema=(str(row["result_schema"]) if row.get("result_schema") is not None else None),
        result=row.get("result") if include_result and raw_state == "completed" else None,
    )


def message_payload(message: MessageV1 | None) -> Mapping[str, object] | None:
    """Return the compact JSON-safe representation of one job error."""
    if message is None:
        return None
    payload: dict[str, object] = {
        "code": message.code,
        "severity": message.severity,
        "message": message.message,
    }
    if message.remediation is not None:
        payload["remediation"] = message.remediation
    return payload


def enforce_status_boundaries(
    status: JobStatusV1,
    handle: JobHandle | None,
    *,
    include_result: bool,
) -> JobStatusV1:
    """Apply compact/result byte budgets to memory and durable status rows."""
    if not include_result or status.state != "completed":
        compact = replace(status, result=None)
        enforce_payload_budget(compact.to_payload(), MAX_COMPACT_STATUS_BYTES, "job_status")
        return compact
    if status.result is None:
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
    result_budget = handle.result_budget if handle is not None else MAX_RESULT_BUDGET_BYTES
    if actual > result_budget:
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


def compatible_completed_result(
    status: JobStatusV1,
    *,
    source_revision: str | None,
    result_schema: str,
) -> bool:
    """Return whether one completed status can join a compatible result page."""
    return (
        status.state == "completed"
        and status.source_revision == source_revision
        and status.result_schema == result_schema
        and isinstance(status.result, Mapping)
    )


def is_reusable_compact(
    status: JobStatusV1,
    *,
    source_revision: str | None,
) -> bool:
    """Return whether a compact in-memory status remains reusable."""
    return (
        status.source_revision == source_revision
        and status.state not in {"failed", "cancelled"}
        and status.state in {"queued", "running", "completed"}
    )


def has_completed_result(status: JobStatusV1, *, result_schema: str) -> bool:
    """Return whether a detailed status contains the expected completed result."""
    return (
        status.state == "completed"
        and status.result_schema == result_schema
        and status.result is not None
    )


def _persisted_message(value: object) -> MessageV1 | None:
    if not isinstance(value, Mapping):
        return None
    raw_severity = str(value.get("severity", "warning"))
    severity: MessageSeverity = (
        "blocking"
        if raw_severity == "blocking"
        else "info"
        if raw_severity == "info"
        else "warning"
    )
    return MessageV1(
        code=str(value.get("code", "job.failed")),
        severity=severity,
        message=str(value.get("message", "The job did not complete.")),
        remediation=(str(value["remediation"]) if value.get("remediation") is not None else None),
    )
