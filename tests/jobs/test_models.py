from __future__ import annotations

import pytest

from codex_usage_tracker.core.contracts import MessageV1, payload_mapping
from codex_usage_tracker.jobs.models import JobHandle, JobStatusV1


def test_job_status_v1_serializes_exact_design_schema() -> None:
    status = JobStatusV1(
        job_id="job-1",
        kind="analysis",
        state="running",
        progress_percent=42,
        stage="grouping",
        source_revision="generation:7",
        request_hash=f"sha256:{'a' * 64}",
        created_at="2026-07-21T12:00:00Z",
        updated_at="2026-07-21T12:01:00Z",
        completed_at=None,
        retryable=False,
        error=None,
        result_schema=None,
        result=None,
    )

    assert list(payload_mapping(status)) == [
        "completed_at",
        "created_at",
        "error",
        "job_id",
        "kind",
        "progress_percent",
        "request_hash",
        "result",
        "result_schema",
        "retryable",
        "schema",
        "source_revision",
        "stage",
        "state",
        "updated_at",
    ]
    assert payload_mapping(status)["schema"] == "codex-usage-tracker.job.v1"


@pytest.mark.parametrize("progress", [-1, 101])
def test_job_status_rejects_out_of_range_progress(progress: int) -> None:
    with pytest.raises(ValueError, match="progress_percent must be between 0 and 100"):
        JobStatusV1(
            job_id="job-1",
            kind="refresh",
            state="queued",
            progress_percent=progress,
            stage="queued",
            source_revision=None,
            request_hash=f"sha256:{'a' * 64}",
            created_at="2026-07-21T12:00:00Z",
            updated_at="2026-07-21T12:00:00Z",
            completed_at=None,
            retryable=False,
            error=None,
            result_schema=None,
            result=None,
        )


def test_job_handle_requires_explicit_positive_result_budget() -> None:
    with pytest.raises(ValueError, match="result_budget"):
        JobHandle(
            kind="diagnostic",
            job_id="job-1",
            adapter=lambda _job_id, include_result=False: {},  # type: ignore[arg-type]
            result_budget=0,
        )


def test_job_error_uses_stable_message_contract() -> None:
    error = MessageV1(code="job.failed", severity="blocking", message="The job failed.")
    assert payload_mapping(error)["code"] == "job.failed"


def test_job_status_normalizes_utc_timestamps() -> None:
    status = JobStatusV1(
        job_id="job-utc",
        kind="analysis",
        state="completed",
        progress_percent=100,
        stage="complete",
        source_revision="generation:7",
        request_hash=f"sha256:{'a' * 64}",
        created_at="2026-07-21T08:00:00-04:00",
        updated_at="2026-07-21T12:01:00+00:00",
        completed_at="2026-07-21T12:01:00Z",
        retryable=False,
        error=None,
        result_schema="analysis.result.v1",
        result=None,
    )

    assert status.created_at == "2026-07-21T12:00:00Z"
    assert status.updated_at == "2026-07-21T12:01:00Z"
    assert status.completed_at == "2026-07-21T12:01:00Z"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("retryable", 1, "retryable must be a bool"),
        ("created_at", "not-a-time", "created_at must be a canonical timestamp"),
        ("source_revision", "/private/source", "source_revision must be a safe identifier"),
        ("result_schema", "bad schema\n", "result_schema must be a safe identifier"),
        ("job_id", "../private/job", "job_id must be a safe identifier"),
    ],
)
def test_job_status_rejects_unsafe_contract_fields(field: str, value: object, message: str) -> None:
    values: dict[str, object] = {
        "job_id": "job-safe",
        "kind": "analysis",
        "state": "running",
        "progress_percent": 1,
        "stage": "running",
        "source_revision": "generation:7",
        "request_hash": f"sha256:{'a' * 64}",
        "created_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:00:01Z",
        "completed_at": None,
        "retryable": False,
        "error": None,
        "result_schema": None,
        "result": None,
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError), match=message):
        JobStatusV1(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("budget", [True, 1.5, 0, 1024 * 1024 + 1])
def test_job_handle_validates_bounded_exact_integer_budget(budget: object) -> None:
    with pytest.raises(ValueError, match="result_budget"):
        JobHandle(
            kind="diagnostic",
            job_id="job-budget",
            adapter=lambda _job_id, include_result=False: {},  # type: ignore[arg-type]
            result_budget=budget,  # type: ignore[arg-type]
        )
