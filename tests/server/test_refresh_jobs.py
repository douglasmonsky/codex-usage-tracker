from __future__ import annotations

import threading
import time
from pathlib import Path

from codex_usage_tracker.server.usage_refresh import RefreshJobRegistry
from tests.store_dashboard_helpers import _make_codex_home


def test_refresh_job_registry_reports_progress_and_result(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    registry = RefreshJobRegistry()

    started = registry.start_refresh(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=False,
        aggregate_only=False,
        refresh_lock=threading.Lock(),
    )

    job_id = str(started["job_id"])
    assert started["status"] in {"running", "completed"}
    started_progress = started["progress"]
    assert isinstance(started_progress, dict)
    assert "phase" in started_progress

    deadline = time.monotonic() + 5
    status = registry.status(job_id)
    while status["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        status = registry.status(job_id)

    assert status["status"] == "completed"
    progress = status["progress"]
    result = status["result"]
    assert isinstance(progress, dict)
    assert isinstance(result, dict)
    assert progress["phase"] == "finalizing"
    assert progress["status"] == "completed"
    assert int(result["parsed_events"]) > 0
    generic = registry.job_service.status(job_id, include_result=True)
    assert generic.kind == "refresh"
    assert generic.state == "completed"
    assert generic.result is not None
    assert "db_path" not in generic.result  # type: ignore[operator]


def test_refresh_job_registry_reports_missing_job() -> None:
    payload = RefreshJobRegistry().status("missing-job")

    assert payload["status"] == "missing"
    assert payload["job_id"] == "missing-job"
