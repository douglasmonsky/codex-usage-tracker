from __future__ import annotations

import multiprocessing
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from codex_usage_tracker.kernel.lease import RefreshLeaseRepository
from codex_usage_tracker.kernel.operational import initialize_operational_database


def _acquire_in_process(
    path: str,
    ready: Any,
    release: Any,
    results: Any,
) -> None:
    lease = RefreshLeaseRepository(Path(path), lease_seconds=10.0).acquire(
        "sha256:first",
        "process-owner",
        now=100.0,
    )
    results.put((lease.refresh_run_id, lease.created))
    ready.set()
    release.wait(timeout=5)


def test_compatible_job_joins_and_foreign_job_is_not_duplicated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    repository = RefreshLeaseRepository(path)

    first = repository.acquire("sha256:request", "owner-1", now=100.0)
    joined = repository.acquire("sha256:request", "owner-2", now=101.0)

    assert first.created
    assert not joined.created
    assert joined.refresh_run_id == first.refresh_run_id


def test_stale_owner_recovers_without_interrupting_live_foreign_owner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    repository = RefreshLeaseRepository(path, lease_seconds=10.0)
    first = repository.acquire("sha256:first", "owner-1", now=100.0)

    live = repository.acquire("sha256:second", "owner-2", now=105.0)
    recovered = repository.acquire("sha256:second", "owner-2", now=111.0)

    assert live.busy and live.refresh_run_id == first.refresh_run_id
    assert recovered.created and recovered.refresh_run_id != first.refresh_run_id


def test_second_process_joins_live_owner_then_recovers_stale_lease(
    tmp_path: Path,
) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    results = context.Queue()
    owner = context.Process(
        target=_acquire_in_process,
        args=(str(path), ready, release, results),
    )
    owner.start()
    assert ready.wait(timeout=5)
    first_run_id, created = results.get(timeout=5)

    repository = RefreshLeaseRepository(path, lease_seconds=10.0)
    joined = repository.acquire("sha256:first", "main-owner", now=105.0)
    recovered = repository.acquire("sha256:second", "main-owner", now=111.0)

    release.set()
    owner.join(timeout=5)
    assert owner.exitcode == 0
    assert created
    assert joined.refresh_run_id == first_run_id
    assert joined.created is False
    assert recovered.created
    assert recovered.refresh_run_id != first_run_id


def test_long_parse_heartbeat_prevents_live_lease_theft(tmp_path: Path) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    repository = RefreshLeaseRepository(path, lease_seconds=0.15)
    lease = repository.acquire(
        "sha256:request",
        "owner-1",
        now=time.time(),
    )

    with repository.maintain(lease.refresh_run_id, "owner-1"):
        threading.Event().wait(0.22)
        joined = repository.acquire(
            "sha256:request",
            "owner-2",
            now=time.time(),
        )

    assert joined.created is False
    assert joined.refresh_run_id == lease.refresh_run_id
    assert repository.renew(lease.refresh_run_id, "wrong-owner") is False


def test_stale_owner_is_fenced_after_takeover(tmp_path: Path) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    repository = RefreshLeaseRepository(path, lease_seconds=10.0)
    lease = repository.acquire("sha256:first", "owner-1", now=time.time())

    with repository.maintain(lease.refresh_run_id, "owner-1") as guard:
        recovered = repository.acquire(
            "sha256:second",
            "owner-2",
            now=time.time() + 100.0,
        )
        assert recovered.created
        try:
            guard.check()
        except RuntimeError as exc:
            assert str(exc) == "refresh lease ownership lost"
        else:
            raise AssertionError("stale owner was not fenced")


def test_progress_and_completion_persist_exact_counters(tmp_path: Path) -> None:
    path = tmp_path / "operational.sqlite3"
    initialize_operational_database(path)
    repository = RefreshLeaseRepository(path)
    lease = repository.acquire("sha256:request", "owner-1")
    repository.progress(
        lease.refresh_run_id,
        "owner-1",
        stage="writing",
        percent=45,
        high_water={"src_synthetic": 123},
        changed_sources=2,
        inserted=7,
        deleted=3,
        timings={"parsing": 0.25},
    )
    repository.complete(
        lease.refresh_run_id,
        generation=4,
        result={
            "changed_sources": 2,
            "inserted_calls": 5,
            "inserted_tools": 2,
            "deleted_rows": 3,
        },
    )

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT state, stage, progress_percent, output_generation,
                   changed_source_count, inserted_count, deleted_count,
                   planned_high_water_json, stage_timings_json
            FROM refresh_runs WHERE refresh_run_id = ?
            """,
            (lease.refresh_run_id,),
        ).fetchone()
    assert row == (
        "completed",
        "complete",
        100.0,
        4,
        2,
        7,
        3,
        '{"src_synthetic": 123}',
        '{"parsing": 0.25}',
    )
