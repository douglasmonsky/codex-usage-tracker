from __future__ import annotations

import threading
import time
from pathlib import Path

from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.refresh import refresh_usage
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.server import usage_refresh as usage_refresh_module
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
    assert progress["phase"] == "complete"
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


def test_dashboard_and_mcp_refresh_join_one_durable_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    paths = ApplicationPaths(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
    )
    dashboard_container = build_application_container(paths)
    mcp_container = build_application_container(paths)
    registry = RefreshJobRegistry(job_service=dashboard_container.jobs)
    refresh_started = threading.Event()
    release_refresh = threading.Event()
    original_refresh = usage_refresh_module.refresh_usage_index

    def blocking_refresh(**kwargs):
        refresh_started.set()
        assert release_refresh.wait(timeout=5)
        return original_refresh(**kwargs)

    monkeypatch.setattr(usage_refresh_module, "refresh_usage_index", blocking_refresh)
    dashboard_job = registry.start_refresh(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        include_archived=False,
        aggregate_only=False,
        refresh_lock=threading.Lock(),
    )
    assert refresh_started.wait(timeout=5)

    mcp_outcome = refresh_usage(
        RefreshRequest(history="active", aggregate_only=False, execution="async"),
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        job_service=mcp_container.jobs,
    )

    assert mcp_outcome.job is not None
    assert mcp_outcome.job.job_id == dashboard_job["job_id"]
    release_refresh.set()
    deadline = time.monotonic() + 5
    status = registry.status(str(dashboard_job["job_id"]))
    while status["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        status = registry.status(str(dashboard_job["job_id"]))
    assert status["status"] == "completed"
