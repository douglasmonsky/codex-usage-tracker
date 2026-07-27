from __future__ import annotations

import shutil
import threading
from pathlib import Path

from codex_usage_tracker.kernel.application import (
    KernelApplication,
    RuntimePaths,
    build_application,
)
from codex_usage_tracker.kernel.application.jobs import JobReader
from codex_usage_tracker.kernel.ingest import refresh_request_hash
from codex_usage_tracker.kernel.lease import RefreshLeaseRepository
from codex_usage_tracker.kernel.operational import initialize_operational_database

from .support import ORACLE_ROOT, active_runtime, synthetic_sources


def test_read_use_cases_share_one_generation_and_never_write(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    app = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )
    operational_before = runtime.kernel.operational.read_bytes()
    analytical_before = runtime.kernel.analytical.read_bytes()

    status = app.status()
    query = app.query(
        {
            "requests": [
                {
                    "dataset": "calls",
                    "operation": "rows",
                    "dimensions": ["call", "model"],
                    "measures": ["total_tokens"],
                    "limit": 10,
                }
            ]
        }
    )
    selector = query["results"][0]["evidence_selectors"][0]
    evidence = app.evidence(
        {"selector": selector, "view": "summary", "limit": 10}
    )
    allowance = app.allowance({"limit": 10})
    stream = app.live(last_event_id=0, limit=10, origin="http://127.0.0.1")

    assert status["generation"] == 1
    assert query["results"][0]["generation"] == 1
    assert evidence["generation"] == 1
    assert allowance["generation"] == 1
    assert stream[0].startswith("id: 1\nevent: generation_committed")
    assert runtime.kernel.operational.read_bytes() == operational_before
    assert runtime.kernel.analytical.read_bytes() == analytical_before


def test_refresh_joins_compatible_live_job_without_launching_worker(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.codex_home.mkdir(parents=True)
    initialize_operational_database(runtime.kernel.operational)
    sources = synthetic_sources()
    repository = RefreshLeaseRepository(runtime.kernel.operational)
    lease = repository.acquire(
        refresh_request_hash(list(sources)),
        "existing-owner",
    )
    launches: list[RuntimePaths] = []
    app = KernelApplication(
        runtime,
        worker_launcher=launches.append,
        source_provider=lambda _home: sources,
    )

    result = app.refresh()

    assert result["disposition"] == "joined"
    assert result["job"]["job_id"] == lease.refresh_run_id
    assert launches == []


def test_concurrent_refresh_callers_launch_one_worker(tmp_path: Path) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.codex_home.mkdir(parents=True)
    sources = synthetic_sources()
    repository = RefreshLeaseRepository(runtime.kernel.operational)
    launches = 0
    launch_lock = threading.Lock()

    def launch(_paths: RuntimePaths) -> None:
        nonlocal launches
        with launch_lock:
            launches += 1
        repository.acquire(
            refresh_request_hash(list(sources)),
            "concurrent-owner",
        )

    app = KernelApplication(
        runtime,
        worker_launcher=launch,
        source_provider=lambda _home: sources,
    )
    results: list[dict[str, object]] = []
    callers = [
        threading.Thread(target=lambda: results.append(app.refresh()))
        for _index in range(2)
    ]

    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=5)

    assert launches == 1
    assert sorted(result["disposition"] for result in results) == [
        "joined",
        "started",
    ]


def test_expired_refresh_is_recovered_and_replaced_once(tmp_path: Path) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.codex_home.mkdir(parents=True)
    initialize_operational_database(runtime.kernel.operational)
    sources = synthetic_sources()
    repository = RefreshLeaseRepository(runtime.kernel.operational)
    expired = repository.acquire(
        refresh_request_hash(list(sources)),
        "dead-owner",
        now=1,
    )
    launches = 0

    def launch(_paths: RuntimePaths) -> None:
        nonlocal launches
        launches += 1
        repository.acquire(
            refresh_request_hash(list(sources)),
            "replacement-owner",
        )

    app = KernelApplication(
        runtime,
        worker_launcher=launch,
        source_provider=lambda _home: sources,
    )

    result = app.refresh()

    assert launches == 1
    assert result["disposition"] == "started"
    assert result["job"]["job_id"] != expired.refresh_run_id
    assert JobReader(runtime.kernel.operational).get(
        expired.refresh_run_id
    ).state == "interrupted"


def test_job_status_waits_on_host_and_returns_one_terminal_snapshot(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    initialize_operational_database(runtime.kernel.operational)
    repository = RefreshLeaseRepository(runtime.kernel.operational)
    lease = repository.acquire("sha256:synthetic", "owner")
    app = KernelApplication(runtime, worker_launcher=lambda _paths: None)

    def complete() -> None:
        threading.Event().wait(0.05)
        repository.complete(
            lease.refresh_run_id,
            generation=2,
            result={
                "changed_sources": 1,
                "inserted_calls": 2,
                "inserted_tools": 3,
                "deleted_rows": 0,
            },
        )

    worker = threading.Thread(target=complete)
    worker.start()
    result = app.job_status(
        lease.refresh_run_id,
        wait_seconds=1,
        include_result=True,
    )
    worker.join(timeout=1)

    assert result["state"] == "completed"
    assert result["stage"] == "complete"
    assert result["progress_percent"] == 100
    assert result["terminal"] is True
    assert result["result"]["inserted_tools"] == 3
    assert JobReader(runtime.kernel.operational).active() is None


def test_refresh_waits_for_a_new_job_after_a_previous_terminal_run(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    initialize_operational_database(runtime.kernel.operational)
    repository = RefreshLeaseRepository(runtime.kernel.operational)
    previous = repository.acquire("sha256:previous", "previous-owner")
    repository.complete(previous.refresh_run_id, generation=1, result={})
    sources = synthetic_sources()

    def launch(_paths: RuntimePaths) -> None:
        repository.acquire(refresh_request_hash(list(sources)), "new-owner")

    app = KernelApplication(
        runtime,
        worker_launcher=launch,
        source_provider=lambda _home: sources,
    )

    result = app.refresh()

    assert result["job"]["job_id"] != previous.refresh_run_id
    assert result["job"]["state"] == "running"


def test_real_background_worker_reaches_terminal_on_synthetic_input(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    shutil.copytree(ORACLE_ROOT / "logs", runtime.codex_home / "sessions")
    app = build_application(runtime)

    result = app.refresh(wait_seconds=30)

    assert result["disposition"] == "started"
    assert result["job"]["state"] == "completed"
    assert result["job"]["terminal"] is True
    assert result["job"]["output_generation"] == 1
    assert result["job"]["inserted_rows"] > 0
    assert app.status()["generation"] == 1
