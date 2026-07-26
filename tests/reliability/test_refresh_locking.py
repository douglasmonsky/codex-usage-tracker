from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic

import pytest

import codex_usage_tracker.application.refresh_launcher as launcher_module
from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.refresh import (
    REFRESH_SCHEMA,
    RefreshCoordinator,
)
from codex_usage_tracker.application.refresh_worker import run_refresh_worker
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.recommendation_engine.api import (
    refresh_usage_index as refresh_usage_with_facts,
)
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository
from codex_usage_tracker.store.connection import configure_connection, connect
from codex_usage_tracker.store.schema import init_db


def test_application_container_startup_is_read_only_during_refresh_writer_lock(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
    writer = configure_connection(sqlite3.connect(db_path, timeout=0))
    writer.execute("BEGIN IMMEDIATE")
    started_at = monotonic()
    try:
        container = build_application_container(
            ApplicationPaths(
                codex_home=tmp_path / ".codex",
                db_path=db_path,
                pricing_path=tmp_path / "pricing.json",
                allowance_path=tmp_path / "allowance.json",
                rate_card_path=tmp_path / "rate-card.json",
                thresholds_path=tmp_path / "thresholds.json",
                projects_path=tmp_path / "projects.json",
            )
        )
    finally:
        writer.rollback()
        writer.close()

    assert container.paths.db_path == db_path
    assert monotonic() - started_at < 0.5


def test_no_change_refresh_is_read_only_during_usage_writer_lock(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    db_path = tmp_path / "usage.sqlite3"
    refresh_kwargs = {
        "codex_home": codex_home,
        "db_path": db_path,
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
    }
    refresh_usage_with_facts(**refresh_kwargs)
    writer = configure_connection(sqlite3.connect(db_path, timeout=0))
    writer.execute("BEGIN IMMEDIATE")
    started_at = monotonic()
    try:
        result = refresh_usage_with_facts(**refresh_kwargs)
    finally:
        writer.rollback()
        writer.close()

    assert result.parsed_events == 0
    assert result.inserted_or_updated_events == 0
    assert monotonic() - started_at < 0.5


def test_independent_services_join_and_poll_one_durable_refresh(tmp_path: Path) -> None:
    job_db = tmp_path / "usage.jobs.sqlite3"
    first_service = JobService(repository=AnalysisJobRepository(job_db, owner_id="refresh-owner-a"))
    second_service = JobService(
        repository=AnalysisJobRepository(job_db, owner_id="refresh-owner-a")
    )
    first = RefreshCoordinator(first_service)
    second = RefreshCoordinator(second_service)
    running = threading.Event()
    release = threading.Event()
    executions = 0

    def worker(progress):
        nonlocal executions
        executions += 1
        progress({"phase": "derived_facts", "percent": 67})
        running.set()
        assert release.wait(timeout=2)
        return {
            "schema": REFRESH_SCHEMA,
            "refresh": {},
            "planner": {},
            "scope": {},
            "freshness": {},
            "accounting": {},
        }

    request = RefreshRequest(execution="async")
    first_status = first.start(
        "refresh-v1:synthetic",
        worker,
        source_revision="sha256:" + "a" * 64,
        request=request,
    )
    assert running.wait(timeout=2)
    joined = second.start(
        "refresh-v1:synthetic",
        worker,
        source_revision="sha256:" + "b" * 64,
        request=request,
    )
    observed = second_service.status(first_status.job_id)
    release.set()

    assert joined.job_id == first_status.job_id
    assert observed.state == "running"
    assert observed.stage == "derived_facts"
    assert observed.progress_percent == 67
    assert executions == 1


def test_simultaneous_processes_register_one_detached_refresh(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    gate = tmp_path / "start"
    script = """
from pathlib import Path
from time import sleep
from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.refresh import refresh_usage
from codex_usage_tracker.application.requests import RefreshRequest
root = Path(__import__("sys").argv[1])
gate = root / "start"
while not gate.exists():
    sleep(0.01)
paths = ApplicationPaths(
    codex_home=root / "codex",
    db_path=root / "usage.sqlite3",
    pricing_path=root / "pricing.json",
    allowance_path=root / "allowance.json",
    rate_card_path=root / "rate-card.json",
    thresholds_path=root / "thresholds.json",
    projects_path=root / "projects.json",
)
container = build_application_container(paths)
outcome = refresh_usage(
    RefreshRequest(execution="async"),
    codex_home=paths.codex_home,
    db_path=paths.db_path,
    pricing_path=paths.pricing_path,
    source_repository=container.repositories.sources,
    job_service=container.jobs,
)
assert outcome.job is not None
print(outcome.job.job_id)
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _index in range(2)
    ]
    gate.touch()
    completed = [process.communicate(timeout=10) for process in processes]

    assert all(process.returncode == 0 for process in processes), completed
    job_ids = [stdout.strip() for stdout, _stderr in completed]
    assert len(set(job_ids)) == 1

    paths = ApplicationPaths(
        codex_home=codex_home,
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
    )
    observer = build_application_container(paths)
    deadline = monotonic() + 10
    status = observer.jobs.status(job_ids[0], include_result=True)
    while status.state in {"queued", "running"} and monotonic() < deadline:
        time.sleep(0.05)
        status = observer.jobs.status(job_ids[0], include_result=True)

    assert status.state == "completed"
    repository = observer.jobs.persistence
    assert isinstance(repository, AnalysisJobRepository)
    with sqlite3.connect(repository.db_path) as conn:
        refresh_jobs = conn.execute(
            "SELECT COUNT(*) FROM analysis_jobs WHERE job_kind = 'refresh'"
        ).fetchone()
    assert refresh_jobs is not None
    assert refresh_jobs[0] == 1


def test_detached_start_returns_post_handshake_failure(tmp_path: Path) -> None:
    repository = AnalysisJobRepository(
        tmp_path / "usage.jobs.sqlite3",
        owner_id="detached-start-owner",
    )
    coordinator = RefreshCoordinator(JobService(repository=repository))

    def failed_launcher(job_id: str) -> None:
        repository.update_status(
            job_id,
            state="failed",
            progress={"percent": 0, "stage": "failed"},
            error={
                "code": "refresh.failed",
                "severity": "recoverable",
                "message": "worker exited before startup",
                "remediation": "retry the refresh",
            },
        )

    status = coordinator.start(
        "refresh-v1:detached-start-failure",
        lambda _progress: pytest.fail("detached refresh worker ran in-process"),
        source_revision="source:none",
        request=RefreshRequest(execution="async"),
        detached_launcher=failed_launcher,
    )

    assert status.state == "failed"
    assert status.stage == "failed"
    assert status.error is not None
    assert status.error.code == "refresh.failed"


def test_detached_worker_retries_a_transient_startup_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_db = tmp_path / "usage.jobs.sqlite3"
    owner_id = "retry-owner"
    job_id = "retry-refresh"
    request = RefreshRequest(execution="async")
    repository = AnalysisJobRepository(job_db, owner_id=owner_id)
    repository.create_or_reuse(
        job_id=job_id,
        job_kind="refresh",
        semantic_key=request_hash("refresh-v1:retry"),
        source_revision="source:none",
        request_schema="refresh.request.v1",
        request={
            "history": request.history,
            "aggregate_only": request.aggregate_only,
            "execution": request.execution,
        },
        result_schema=REFRESH_SCHEMA,
    )
    original_update = AnalysisJobRepository.update_status
    original_get = AnalysisJobRepository.get
    startup_attempts = 0

    def transiently_locked(self, *args, **kwargs):
        nonlocal startup_attempts
        if kwargs.get("state") == "running" and startup_attempts == 0:
            startup_attempts += 1
            raise sqlite3.OperationalError("database is locked")
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(AnalysisJobRepository, "update_status", transiently_locked)
    monkeypatch.setattr(
        AnalysisJobRepository,
        "get",
        lambda *_args, **_kwargs: pytest.fail(
            "detached worker reread its registered source revision"
        ),
    )

    exit_code = run_refresh_worker(
        job_id=job_id,
        owner_id=owner_id,
        job_db_path=job_db,
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        source_revision="source:none",
        request=request,
    )

    assert exit_code == 0
    assert startup_attempts == 1
    assert original_get(repository, job_id, touch=False)["status"] == "completed"


def test_detached_launcher_retries_an_early_worker_exit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_db = tmp_path / "usage.jobs.sqlite3"
    owner_id = "launcher-owner"
    job_id = "launcher-refresh"
    request = RefreshRequest(execution="async")
    repository = AnalysisJobRepository(job_db, owner_id=owner_id)
    repository.create_or_reuse(
        job_id=job_id,
        job_kind="refresh",
        semantic_key=request_hash("refresh-v1:launcher-retry"),
        source_revision="source:none",
        request_schema="refresh.request.v1",
        request={
            "history": request.history,
            "aggregate_only": request.aggregate_only,
            "execution": request.execution,
        },
        result_schema=REFRESH_SCHEMA,
    )
    service = JobService(repository=repository)
    launches = 0

    class Process:
        def __init__(self, exit_code: int | None) -> None:
            self.exit_code = exit_code

        def poll(self) -> int | None:
            return self.exit_code

    def popen(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        if launches == 1:
            return Process(1)
        repository.update_status(
            job_id,
            state="running",
            progress={"percent": 0, "stage": "planning"},
        )
        return Process(None)

    monkeypatch.setattr(launcher_module.subprocess, "Popen", popen)
    launcher = launcher_module.detached_refresh_launcher(
        request=request,
        source_revision="source:none",
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        job_service=service,
        enabled=True,
    )

    assert launcher is not None
    launcher(job_id)

    assert launches == 2
    assert repository.get(job_id, touch=False)["status"] == "running"


def test_detached_launcher_retries_a_transient_spawn_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_db = tmp_path / "usage.jobs.sqlite3"
    owner_id = "launcher-owner"
    job_id = "launcher-refresh"
    request = RefreshRequest(execution="async")
    repository = AnalysisJobRepository(job_db, owner_id=owner_id)
    repository.create_or_reuse(
        job_id=job_id,
        job_kind="refresh",
        semantic_key=request_hash("refresh-v1:launcher-spawn-retry"),
        source_revision="source:none",
        request_schema="refresh.request.v1",
        request={
            "history": request.history,
            "aggregate_only": request.aggregate_only,
            "execution": request.execution,
        },
        result_schema=REFRESH_SCHEMA,
    )
    service = JobService(repository=repository)
    launches = 0

    class Process:
        def poll(self) -> None:
            return None

    def popen(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        if launches == 1:
            raise OSError("synthetic transient spawn failure")
        repository.update_status(
            job_id,
            state="running",
            progress={"percent": 0, "stage": "planning"},
        )
        return Process()

    monkeypatch.setattr(launcher_module.subprocess, "Popen", popen)
    launcher = launcher_module.detached_refresh_launcher(
        request=request,
        source_revision="source:none",
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        job_service=service,
        enabled=True,
    )

    assert launcher is not None
    launcher(job_id)

    assert launches == 2
    assert repository.get(job_id, touch=False)["status"] == "running"


def test_expired_refresh_lease_is_replaced_by_one_new_worker(tmp_path: Path) -> None:
    job_db = tmp_path / "usage.jobs.sqlite3"
    request_key = "refresh-v1:expired-synthetic"
    source_revision = "sha256:" + "b" * 64
    request = RefreshRequest(execution="async")
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    expired = AnalysisJobRepository(
        job_db,
        owner_id="expired-owner",
        lease_ttl=timedelta(seconds=30),
    )
    expired.create_or_reuse(
        job_id="expired-refresh",
        job_kind="refresh",
        semantic_key=request_hash(request_key),
        source_revision=source_revision,
        request_schema="refresh.request.v1",
        request={
            "history": request.history,
            "aggregate_only": request.aggregate_only,
            "execution": request.execution,
        },
        result_schema=REFRESH_SCHEMA,
        now=expired_at,
    )
    expired.update_status(
        "expired-refresh",
        state="running",
        progress={"percent": 10, "stage": "parsing"},
        now=expired_at,
    )
    fresh_repository = AnalysisJobRepository(job_db, owner_id="fresh-owner")
    coordinator = RefreshCoordinator(JobService(repository=fresh_repository))
    executed = threading.Event()

    def worker(_progress):
        executed.set()
        return {
            "schema": REFRESH_SCHEMA,
            "refresh": {},
            "planner": {},
            "scope": {},
            "freshness": {},
            "accounting": {},
        }

    status = coordinator.start(
        request_key,
        worker,
        source_revision=source_revision,
        request=request,
    )
    assert executed.wait(timeout=2)
    deadline = monotonic() + 2
    observed = coordinator.job_service.status(status.job_id, include_result=True)
    while observed.state in {"queued", "running"} and monotonic() < deadline:
        time.sleep(0.01)
        observed = coordinator.job_service.status(status.job_id, include_result=True)

    assert status.job_id != "expired-refresh"
    assert observed.state == "completed"
    interrupted = fresh_repository.get("expired-refresh")
    assert interrupted is not None
    assert interrupted["status"] == "interrupted"


def test_detached_refresh_survives_initiating_process_and_is_pollable(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    script = """
from pathlib import Path
from codex_usage_tracker.application.container import build_application_container
from codex_usage_tracker.application.paths import ApplicationPaths
from codex_usage_tracker.application.refresh import refresh_usage
from codex_usage_tracker.application.requests import RefreshRequest
root = Path(__import__("sys").argv[1])
paths = ApplicationPaths(
    codex_home=root / "codex",
    db_path=root / "usage.sqlite3",
    pricing_path=root / "pricing.json",
    allowance_path=root / "allowance.json",
    rate_card_path=root / "rate-card.json",
    thresholds_path=root / "thresholds.json",
    projects_path=root / "projects.json",
)
container = build_application_container(paths)
outcome = refresh_usage(
    RefreshRequest(execution="async"),
    codex_home=paths.codex_home,
    db_path=paths.db_path,
    pricing_path=paths.pricing_path,
    source_repository=container.repositories.sources,
    job_service=container.jobs,
)
print(outcome.job.job_id)
"""
    initiated = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    job_id = initiated.stdout.strip()
    paths = ApplicationPaths(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
    )
    observer = build_application_container(paths)
    deadline = monotonic() + 10
    status = observer.jobs.status(job_id, include_result=True)
    while status.state in {"queued", "running"} and monotonic() < deadline:
        time.sleep(0.05)
        status = observer.jobs.status(job_id, include_result=True)

    assert status.state == "completed"
    assert status.result_schema == REFRESH_SCHEMA
    assert status.result is not None
    assert status.result["refresh"]["parsed_events"] == 0  # type: ignore[index]
    assert db_path.is_file()
