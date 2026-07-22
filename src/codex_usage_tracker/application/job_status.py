"""Application service for generic job polling."""

from __future__ import annotations

from typing import Protocol

from codex_usage_tracker.application.requests import JobStatusRequest
from codex_usage_tracker.jobs.models import JobStatusV1


class JobStatusService(Protocol):
    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1: ...


def get_job_status(
    request: JobStatusRequest, *, job_service: JobStatusService | None = None
) -> JobStatusV1:
    if job_service is None:
        from codex_usage_tracker.application.refresh import default_job_service

        job_service = default_job_service()
    return job_service.status(request.job_id, include_result=request.include_result)
