from __future__ import annotations

import threading
import time
from typing import cast

from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry


def test_analysis_jobs_deduplicate_active_work_and_publish_monotonic_progress() -> None:
    release = threading.Event()
    worker_started = threading.Event()

    def work(progress):
        progress(stage="scanning", completed_units=2, total_units=10, current_unit="calls")
        worker_started.set()
        assert release.wait(timeout=2)
        progress(stage="persisting", completed_units=10, total_units=10, current_unit="snapshots")
        return {"refreshed_sections": 10}

    registry = AnalysisJobRegistry()
    first = registry.start(
        job_kind="diagnostic-refresh",
        request_key="generation:7:all",
        source_revision="generation:7",
        total_units=10,
        work=work,
    )
    assert worker_started.wait(timeout=2)
    reused = registry.start(
        job_kind="diagnostic-refresh",
        request_key="generation:7:all",
        source_revision="generation:7",
        total_units=10,
        work=lambda _progress: {"unexpected": True},
    )

    assert reused["job_id"] == first["job_id"]
    assert reused["cache"] == {"request_reused": "active"}
    assert reused["next"] == {
        "action": "poll",
        "job_id": first["job_id"],
        "poll_after_ms": 500,
    }
    reused_progress = cast(dict[str, object], reused["progress"])
    assert reused_progress["completed_units"] == 2
    assert reused_progress["percent"] == 20.0

    release.set()
    completed = wait_for_terminal(registry, str(first["job_id"]))
    assert completed["status"] == "completed"
    assert completed["stage"] == "complete"
    assert completed["progress"] == {
        "completed_units": 10,
        "total_units": 10,
        "percent": 100.0,
        "current_unit": None,
    }
    assert completed["result"] == {"refreshed_sections": 10}
    assert completed["next"] == {"action": "reload_persisted_results"}
    generic = registry.job_service.status(str(first["job_id"]), include_result=True)
    assert generic.kind == "diagnostic"
    assert generic.state == "completed"
    assert generic.result == {"refreshed_sections": 10}
    assert "generation:7:all" not in generic.request_hash


def test_analysis_job_status_is_read_only_and_worker_survives_abandoned_observer() -> None:
    release = threading.Event()

    def work(progress):
        progress(stage="scanning", completed_units=1, total_units=2)
        assert release.wait(timeout=2)
        return {"done": True}

    registry = AnalysisJobRegistry()
    started = registry.start(
        job_kind="diagnostic-refresh",
        request_key="generation:8:overview",
        source_revision="generation:8",
        total_units=2,
        work=work,
    )
    job_id = str(started["job_id"])
    first_poll = registry.status(job_id)
    second_poll = registry.status(job_id)

    assert first_poll == second_poll
    assert first_poll["status"] == "running"

    # Dropping the returned handle models a browser observer navigating away.
    del started
    release.set()
    assert wait_for_terminal(registry, job_id)["status"] == "completed"


def test_analysis_job_failure_is_structured_and_releases_request_key() -> None:
    def fail(_progress):
        raise RuntimeError("private worker detail")

    registry = AnalysisJobRegistry()
    started = registry.start(
        job_kind="diagnostic-refresh",
        request_key="generation:9:commands",
        source_revision="generation:9",
        total_units=1,
        work=fail,
    )

    failed = wait_for_terminal(registry, str(started["job_id"]))
    assert failed["status"] == "failed"
    assert failed["error"] == {
        "code": "analysis_job_failed",
        "type": "RuntimeError",
    }
    assert "private worker detail" not in str(failed)
    assert failed["next"] == {"action": "retry"}

    restarted = registry.start(
        job_kind="diagnostic-refresh",
        request_key="generation:9:commands",
        source_revision="generation:9",
        total_units=1,
        work=lambda _progress: {"done": True},
    )
    assert restarted["job_id"] != failed["job_id"]


def wait_for_terminal(registry: AnalysisJobRegistry, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = registry.status(job_id)
        if status["status"] not in {"pending", "running"}:
            return status
        time.sleep(0.01)
    raise AssertionError("analysis job did not finish")
