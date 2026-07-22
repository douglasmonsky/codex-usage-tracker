from __future__ import annotations

from codex_usage_tracker.application.job_status import get_job_status
from codex_usage_tracker.application.requests import JobStatusRequest
from codex_usage_tracker.jobs.service import JobService


def test_job_status_uses_injected_service_without_echoing_unknown_id() -> None:
    status = get_job_status(JobStatusRequest("missing-job"), job_service=JobService())

    assert status.error is not None
    assert status.error.code == "job.not_found"
    assert status.job_id.startswith("unknown-")
