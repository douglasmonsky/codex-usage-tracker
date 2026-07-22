from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

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


def test_broken_adapter_request_hash_is_recomputed_without_leaking() -> None:
    class BrokenAdapter:
        request_hash = "raw/private/request-key"
        result_schema = "analysis.result.v1"
        result_budget = 4096

        def status(self, job_id: str, *, include_result: bool = False) -> dict[str, object]:
            raise RuntimeError("SYNTHETIC_PRIVATE_ADAPTER_FAILURE")

    service = JobService()
    service.register(kind="analysis", job_id="broken-hash", adapter=BrokenAdapter())

    status = service.status("broken-hash")
    encoded = json.dumps(status.to_payload())

    assert status.error is not None
    assert status.error.code == "job.adapter_failed"
    assert status.request_hash == request_hash("broken-hash")
    assert "raw/private" not in encoded
    assert "SYNTHETIC_PRIVATE_ADAPTER_FAILURE" not in encoded


def test_blocking_adapter_does_not_block_unrelated_status_or_registration() -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocked(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=2)
        return _analysis_payload("blocked", 10)

    service = JobService()
    service.register(
        kind="analysis",
        job_id="blocked",
        adapter=AnalysisJobAdapter(blocked, kind="analysis", request_hash=request_hash("blocked")),
    )
    service.register(
        kind="analysis",
        job_id="quick",
        adapter=AnalysisJobAdapter(
            _reader(_analysis_payload("quick", 20)),
            kind="analysis",
            request_hash=request_hash("quick"),
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        blocked_future = pool.submit(service.status, "blocked")
        assert entered.wait(timeout=1)
        quick_future = pool.submit(service.status, "quick")
        assert quick_future.result(timeout=1).progress_percent == 20
        service.register(
            kind="analysis",
            job_id="new",
            adapter=AnalysisJobAdapter(
                _reader(_analysis_payload("new", 1)),
                kind="analysis",
                request_hash=request_hash("new"),
            ),
        )
        release.set()
        assert blocked_future.result(timeout=1).job_id == "blocked"


def test_reentrant_adapter_can_poll_another_job_without_deadlock() -> None:
    service = JobService()
    service.register(
        kind="analysis",
        job_id="inner",
        adapter=AnalysisJobAdapter(
            _reader(_analysis_payload("inner", 50)),
            kind="analysis",
            request_hash=request_hash("inner"),
        ),
    )

    def reentrant(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        assert service.status("inner").progress_percent == 50
        return _analysis_payload("outer", 60)

    service.register(
        kind="analysis",
        job_id="outer",
        adapter=AnalysisJobAdapter(reentrant, kind="analysis", request_hash=request_hash("outer")),
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(service.status, "outer").result(timeout=1).progress_percent == 60


def test_concurrent_polls_commit_monotonic_progress() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    calls = 0

    def reader(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
            return _analysis_payload("race", 20)
        return _analysis_payload("race", 80)

    service = JobService()
    service.register(
        kind="analysis",
        job_id="race",
        adapter=AnalysisJobAdapter(reader, kind="analysis", request_hash=request_hash("race")),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(service.status, "race")
        assert first_entered.wait(timeout=1)
        fast = pool.submit(service.status, "race")
        assert fast.result(timeout=1).progress_percent == 80
        release_first.set()
        assert slow.result(timeout=1).progress_percent == 80


def test_same_kind_reregistration_discards_blocked_stale_poll() -> None:
    entered = threading.Event()
    release = threading.Event()

    def old(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=2)
        return _analysis_payload("replace", 10)

    service = JobService()
    service.register(
        kind="analysis",
        job_id="replace",
        adapter=AnalysisJobAdapter(old, kind="analysis", request_hash=request_hash("old")),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.status, "replace")
        assert entered.wait(timeout=1)
        service.register(
            kind="analysis",
            job_id="replace",
            adapter=AnalysisJobAdapter(
                _reader(_analysis_payload("replace", 90)),
                kind="analysis",
                request_hash=request_hash("new"),
            ),
        )
        release.set()
        status = future.result(timeout=1)

    assert status.progress_percent == 90
    assert status.request_hash == request_hash("new")


def test_compact_first_adapter_reads_are_ordered_and_state_gated() -> None:
    running_calls: list[bool] = []
    completed_calls: list[bool] = []

    def running(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        running_calls.append(include_result)
        return _analysis_payload("running", 30)

    def completed(_job_id: str, *, include_result: bool = False) -> dict[str, object]:
        completed_calls.append(include_result)
        payload = _analysis_payload("completed", 100, state="completed")
        if include_result:
            payload["result"] = {"safe_total": 3}
        return payload

    service = JobService()
    service.register(
        kind="analysis",
        job_id="running",
        adapter=AnalysisJobAdapter(running, kind="analysis", request_hash=request_hash("running")),
    )
    service.register(
        kind="analysis",
        job_id="completed",
        adapter=AnalysisJobAdapter(
            completed, kind="analysis", request_hash=request_hash("completed")
        ),
    )

    assert service.status("running", include_result=True).result is None
    assert service.status("completed", include_result=True).result == {"safe_total": 3}
    assert running_calls == [False]
    assert completed_calls == [False, True]


def test_adversarial_nested_result_is_projected_without_private_values() -> None:
    legacy = {
        "safe_total": 7,
        "ok": True,
        "nested": [
            {"note": "prefix /Users/Alice/secret.json suffix", "safe_count": 2},
            "file:///private/tmp/report.json",
            "~/Library/Application Support/private.db",
            r"C:\\Users\\Alice\\secret.txt",
            r"\\server\\share\\secret.txt",
            "s3://private-bucket/report.json",
            "custom+private://opaque-host/report.json",
            object(),
        ],
        "artifact_id": "artifact-secret",
        "worker_internal": "worker-secret",
        "request_key": "request-secret",
        "request-key": "request-dash-secret",
        "request.key": "request-dot-secret",
        "requestKey": "request-camel-secret",
        "source-file": "source-file-secret",
        "sourcePath": "source-path-secret",
        "exception.message": "exception-secret",
        "/tmp/path-key": "value",
        "traceback": "Traceback: private exception",
    }
    payload = _analysis_payload("privacy", 100, state="completed")
    payload["result"] = legacy
    original_keys = set(legacy)
    original_nested = list(legacy["nested"])
    before_safe_total = legacy["safe_total"]
    service = JobService()
    service.register(
        kind="analysis",
        job_id="privacy",
        adapter=AnalysisJobAdapter(
            _reader(payload), kind="analysis", request_hash=request_hash("privacy")
        ),
    )

    status = service.status("privacy", include_result=True)
    encoded = json.dumps(status.to_payload())

    assert status.result is not None
    assert status.result["safe_total"] == 7  # type: ignore[index]
    assert status.result["ok"] is True  # type: ignore[index]
    assert "safe_count" in encoded
    for private in (
        "/Users/",
        "file://",
        "~/",
        "C:\\\\",
        "\\\\server",
        "s3://",
        "custom+private://",
        "artifact-secret",
        "worker-secret",
        "request-secret",
        "request-dash-secret",
        "request-dot-secret",
        "request-camel-secret",
        "source-file-secret",
        "source-path-secret",
        "exception-secret",
        "Traceback",
    ):
        assert private not in encoded
    assert before_safe_total == legacy["safe_total"]
    assert set(legacy) == original_keys
    assert legacy["nested"] == original_nested


def test_benign_error_rate_text_survives_result_projection() -> None:
    payload = _analysis_payload("benign-text", 100, state="completed")
    payload["result"] = {
        "safe_total": 3,
        "summary": "model error rate is 2%",
        "label": "no exception occurred",
    }
    service = JobService()
    service.register(
        kind="analysis",
        job_id="benign-text",
        adapter=AnalysisJobAdapter(
            _reader(payload), kind="analysis", request_hash=request_hash("benign-text")
        ),
    )

    status = service.status("benign-text", include_result=True)

    assert status.result == {
        "safe_total": 3,
        "summary": "model error rate is 2%",
        "label": "no exception occurred",
    }


@pytest.mark.parametrize(
    ("job_id", "private_text"),
    [
        ("runtime-repr", "RuntimeError('private detail')"),
        ("value-repr", 'ValueError("private detail")'),
        ("lower-error", "error: private detail"),
    ],
)
def test_nested_exception_representations_are_redacted(job_id: str, private_text: str) -> None:
    legacy = {"safe_total": 3, "nested": [private_text]}
    payload = _analysis_payload(job_id, 100, state="completed")
    payload["result"] = legacy
    service = JobService()
    service.register(
        kind="analysis",
        job_id=job_id,
        adapter=AnalysisJobAdapter(
            _reader(payload), kind="analysis", request_hash=request_hash(job_id)
        ),
    )

    status = service.status(job_id, include_result=True)

    assert status.result == {
        "safe_total": 3,
        "nested": ("[redacted-private-text]",),
    }
    assert legacy == {"safe_total": 3, "nested": [private_text]}


def test_whole_status_budget_and_unsafe_result_fail_stably() -> None:
    payload = _analysis_payload("budget", 100, state="completed")
    payload["result"] = {"safe": "x"}
    service = JobService()
    service.register(
        kind="analysis",
        job_id="budget",
        adapter=AnalysisJobAdapter(
            _reader(payload),
            kind="analysis",
            request_hash=request_hash("budget"),
            result_budget=100,
        ),
    )
    budgeted = service.status("budget", include_result=True)
    assert budgeted.result is None
    assert budgeted.error is not None
    assert budgeted.error.code == "job.result_too_large"
    assert serialized_size(budgeted.to_payload()) <= 16 * 1024

    class UnsafeAdapter:
        result_schema = "analysis.result.v1"
        result_budget = 4096
        request_hash = request_hash("unsafe")

        def status(self, job_id: str, *, include_result: bool = False) -> dict[str, object]:
            return {
                "job_id": job_id,
                "kind": "analysis",
                "state": "completed",
                "progress_percent": 100,
                "stage": "complete",
                "request_hash": self.request_hash,
                "source_revision": None,
                "created_at": "2026-07-21T12:00:00Z",
                "updated_at": "2026-07-21T12:01:00Z",
                "completed_at": "2026-07-21T12:01:00Z",
                "retryable": False,
                "error": None,
                "result_schema": self.result_schema,
                "result": {"unsafe": object()} if include_result else None,
            }

    unsafe_service = JobService()
    unsafe_service.register(kind="analysis", job_id="unsafe", adapter=UnsafeAdapter())
    unsafe = unsafe_service.status("unsafe", include_result=True)
    assert unsafe.result is None
    assert unsafe.error is not None
    assert unsafe.error.code == "job.result_unsafe"


def test_unknown_job_does_not_echo_arbitrary_input() -> None:
    requested = "../private/user-controlled\njob"
    status = JobService().status(requested)
    assert requested not in status.job_id
    assert status.job_id.startswith("unknown-")


def _analysis_payload(job_id: str, progress: int, *, state: str = "running") -> dict[str, object]:
    return {
        "job_id": job_id,
        "status": state,
        "stage": "complete" if state == "completed" else "working",
        "created_at": "2026-07-21T12:00:00Z",
        "updated_at": "2026-07-21T12:01:00Z",
        "progress": {"percent": progress},
    }
