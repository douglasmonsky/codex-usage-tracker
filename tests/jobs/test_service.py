from __future__ import annotations

import json

import pytest

from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.jobs.adapters import (
    AnalysisJobAdapter,
    CompressionJobAdapter,
    DogfoodJobAdapter,
    RefreshJobAdapter,
    request_hash,
)
from codex_usage_tracker.jobs.service import JobService


def _reader(payload: dict[str, object]):
    return lambda _job_id, include_result=False: dict(payload)


@pytest.mark.parametrize(
    ("kind", "adapter", "expected_state", "expected_progress"),
    [
        (
            "refresh",
            RefreshJobAdapter(
                _reader(
                    {
                        "job_id": "refresh-1",
                        "status": "running",
                        "started_at": "2026-07-21T12:00:00Z",
                        "updated_at": "2026-07-21T12:01:00Z",
                        "progress": {"phase": "parsing", "percent": 34.8},
                    }
                ),
                request_hash=request_hash("private refresh key"),
            ),
            "running",
            34,
        ),
        (
            "analysis",
            AnalysisJobAdapter(
                _reader(
                    {
                        "job_id": "analysis-1",
                        "status": "pending",
                        "stage": "queued",
                        "created_at": "2026-07-21T12:00:00Z",
                        "updated_at": "2026-07-21T12:00:00Z",
                        "source_revision": "generation:3",
                        "progress": {"percent": None},
                    }
                ),
                kind="analysis",
                request_hash=request_hash("generation:3:raw-request"),
            ),
            "queued",
            0,
        ),
        (
            "allowance",
            AnalysisJobAdapter(
                _reader(
                    {
                        "job_id": "allowance-1",
                        "status": "completed",
                        "stage": "complete",
                        "created_at": "2026-07-21T12:00:00Z",
                        "updated_at": "2026-07-21T12:02:00Z",
                        "progress": {"percent": 100},
                        "result": {"ok": True},
                    }
                ),
                kind="allowance",
                request_hash=request_hash("allowance-private"),
            ),
            "completed",
            100,
        ),
        (
            "compression",
            CompressionJobAdapter(
                _reader(
                    {
                        "run_id": "compression-1",
                        "status": "completed_with_warnings",
                        "stage": "complete",
                        "progress_percent": 100,
                        "source_revision": "generation:4",
                        "created_at": "2026-07-21T12:00:00Z",
                        "updated_at": "2026-07-21T12:03:00Z",
                        "completed_at": "2026-07-21T12:03:00Z",
                        "public_profile": {"status": "completed_with_warnings"},
                    }
                ),
                request_hash=request_hash("/private/db|raw-request-key"),
            ),
            "completed",
            100,
        ),
        (
            "diagnostic",
            DogfoodJobAdapter(
                _reader(
                    {
                        "job_id": "dogfood-1",
                        "status": "failed",
                        "percent_complete": 8,
                        "current_stage": "failed\n/private/path",
                        "created_at": "2026-07-21T12:00:00Z",
                        "updated_at": "2026-07-21T12:04:00Z",
                        "completed_at": "2026-07-21T12:04:00Z",
                        "error": "RuntimeError: private details",
                    }
                ),
                request_hash=request_hash("dogfood-private"),
            ),
            "failed",
            8,
        ),
    ],
)
def test_adapters_normalize_existing_payload_families(
    kind: str, adapter: object, expected_state: str, expected_progress: int
) -> None:
    service = JobService()
    service.register(kind=kind, job_id=f"{kind}-1", adapter=adapter)  # type: ignore[arg-type]

    status = service.status(f"{kind}-1")
    encoded = json.dumps(status.to_payload())

    assert status.state == expected_state
    assert status.progress_percent == expected_progress
    assert "private refresh key" not in encoded
    assert "raw-request" not in encoded
    assert "/private/" not in encoded
    assert "RuntimeError" not in encoded


def test_unknown_job_is_truthful_bounded_failure() -> None:
    status = JobService().status("unknown")

    assert status.state == "failed"
    assert status.error is not None
    assert status.error.code == "job.not_found"
    assert serialized_size(status.to_payload()) <= 16 * 1024


def test_polling_preserves_monotonic_state_and_progress() -> None:
    payload: dict[str, object] = {
        "job_id": "analysis-1",
        "status": "running",
        "stage": "ranking",
        "created_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:01:00Z",
        "progress": {"percent": 80},
    }
    service = JobService()
    service.register(
        kind="analysis",
        job_id="analysis-1",
        adapter=AnalysisJobAdapter(
            _reader(payload), kind="analysis", request_hash=request_hash("request")
        ),
    )
    first = service.status("analysis-1")
    payload.update(status="pending", stage="queued", progress={"percent": 20})

    second = service.status("analysis-1")

    assert (first.state, first.progress_percent) == ("running", 80)
    assert (second.state, second.progress_percent) == ("running", 80)


def test_terminal_state_does_not_regress_or_change_across_polls() -> None:
    payload: dict[str, object] = {
        "job_id": "analysis-terminal",
        "status": "completed",
        "stage": "complete",
        "created_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:01:00Z",
        "progress": {"percent": 100},
        "result": {"ok": True},
    }
    service = JobService()
    service.register(
        kind="analysis",
        job_id="analysis-terminal",
        adapter=AnalysisJobAdapter(
            _reader(payload), kind="analysis", request_hash=request_hash("request")
        ),
    )
    first = service.status("analysis-terminal")
    payload.update(status="failed", stage="failed", progress={"percent": 0})

    second = service.status("analysis-terminal")

    assert first.state == "completed"
    assert second.state == "completed"
    assert second.progress_percent == 100
    assert second.error is None


def test_result_is_complete_only_and_enforces_originating_budget() -> None:
    payload: dict[str, object] = {
        "job_id": "analysis-1",
        "status": "completed",
        "stage": "complete",
        "created_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:01:00Z",
        "progress": {"percent": 100},
        "result": {"content": "x" * 500},
    }
    service = JobService()
    service.register(
        kind="analysis",
        job_id="analysis-1",
        adapter=AnalysisJobAdapter(
            _reader(payload),
            kind="analysis",
            request_hash=request_hash("request"),
            result_schema="analysis.result.v1",
            result_budget=128,
        ),
    )

    compact = service.status("analysis-1")
    oversized = service.status("analysis-1", include_result=True)

    assert compact.result is None
    assert compact.error is None
    assert serialized_size(compact.to_payload()) <= 16 * 1024
    assert oversized.result is None
    assert oversized.error is not None
    assert oversized.error.code == "job.result_too_large"
    assert "x" * 100 not in json.dumps(oversized.to_payload())


def test_completed_job_with_missing_result_is_deterministic() -> None:
    service = JobService()
    service.register(
        kind="diagnostic",
        job_id="dogfood-1",
        adapter=DogfoodJobAdapter(
            _reader(
                {
                    "job_id": "dogfood-1",
                    "status": "completed",
                    "percent_complete": 100,
                    "current_stage": "complete",
                    "created_at": "2026-07-21T12:00:00Z",
                    "updated_at": "2026-07-21T12:01:00Z",
                }
            ),
            request_hash=request_hash("request"),
        ),
    )

    status = service.status("dogfood-1", include_result=True)

    assert status.state == "completed"
    assert status.error is not None
    assert status.error.code == "job.result_unavailable"


@pytest.mark.parametrize(
    ("adapter", "job_id", "expected_state", "error_code"),
    [
        (
            CompressionJobAdapter(
                _reader(
                    {
                        "run_id": "compression-2",
                        "status": "interrupted",
                        "stage": "detecting",
                        "progress": {"percent": 63},
                    }
                ),
                request_hash=request_hash("compression request"),
            ),
            "compression-2",
            "cancelled",
            "job.interrupted",
        ),
        (
            DogfoodJobAdapter(
                _reader({"job_id": "dogfood-2", "status": "not_found"}),
                request_hash=request_hash("dogfood request"),
            ),
            "dogfood-2",
            "failed",
            "job.not_found",
        ),
    ],
)
def test_interrupted_and_not_found_payloads_use_documented_states(
    adapter: object, job_id: str, expected_state: str, error_code: str
) -> None:
    kind = "compression" if job_id.startswith("compression") else "diagnostic"
    service = JobService()
    service.register(kind=kind, job_id=job_id, adapter=adapter)  # type: ignore[arg-type]

    status = service.status(job_id)

    assert status.state == expected_state
    assert status.error is not None
    assert status.error.code == error_code
    if expected_state == "cancelled":
        assert status.progress_percent == 63


def test_polling_does_not_mutate_legacy_payload() -> None:
    payload: dict[str, object] = {
        "job_id": "refresh-2",
        "status": "completed",
        "started_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:01:00Z",
        "finished_at": "2026-07-21T12:01:00Z",
        "progress": {"phase": "complete", "percent": 100},
        "result": {"db_path": "/private/usage.sqlite3", "parsed_events": 2},
    }
    before = json.dumps(payload, sort_keys=True)
    service = JobService()
    service.register(
        kind="refresh",
        job_id="refresh-2",
        adapter=RefreshJobAdapter(_reader(payload), request_hash=request_hash("refresh")),
    )

    status = service.status("refresh-2", include_result=True)

    assert json.dumps(payload, sort_keys=True) == before
    assert status.result == {"parsed_events": 2}


def test_adapter_exception_is_stable_and_does_not_leak_text() -> None:
    def fail(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        raise RuntimeError("SYNTHETIC_SENSITIVE_EXCEPTION_TEXT")

    service = JobService()
    service.register(
        kind="refresh",
        job_id="refresh-failed-adapter",
        adapter=RefreshJobAdapter(fail, request_hash=request_hash("refresh")),
    )

    status = service.status("refresh-failed-adapter")
    encoded = json.dumps(status.to_payload())

    assert status.error is not None
    assert status.error.code == "job.adapter_failed"
    assert "SYNTHETIC_SENSITIVE_EXCEPTION_TEXT" not in encoded
    assert "RuntimeError" not in encoded
