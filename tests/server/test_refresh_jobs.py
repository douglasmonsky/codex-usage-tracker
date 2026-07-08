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
    assert "phase" in started["progress"]

    deadline = time.monotonic() + 5
    status = registry.status(job_id)
    while status["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        status = registry.status(job_id)

    assert status["status"] == "completed"
    assert status["progress"]["phase"] == "finalizing"
    assert status["progress"]["status"] == "completed"
    assert status["result"]["parsed_events"] > 0


def test_refresh_job_registry_reports_missing_job() -> None:
    payload = RefreshJobRegistry().status("missing-job")

    assert payload["status"] == "missing"
    assert payload["job_id"] == "missing-job"
