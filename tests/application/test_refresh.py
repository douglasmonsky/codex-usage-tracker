from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from codex_usage_tracker.application import refresh as refresh_module
from codex_usage_tracker.application.refresh import (
    MAX_SYNC_ADDED_BYTES,
    MAX_SYNC_SOURCE_FILES,
    RefreshPlan,
    plan_refresh,
    refresh_usage,
)
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.sources import SourceParsePlan


def test_planner_constants_and_missing_database_have_no_side_effect(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "usage.sqlite3"
    plan = plan_refresh(RefreshRequest(), codex_home=tmp_path / ".codex", db_path=db_path)

    assert MAX_SYNC_SOURCE_FILES == 4
    assert MAX_SYNC_ADDED_BYTES == 4_194_304
    assert plan.execution == "sync"
    assert plan.changed_source_files == 0
    assert not db_path.exists()


def test_explicit_sync_preserves_history_and_aggregate_only(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def refresh(**kwargs: object) -> RefreshResult:
        calls.append(dict(kwargs))
        return RefreshResult(2, 3, 3, str(tmp_path / "usage.sqlite3"), 1, {"bad": 1})

    completed = refresh_usage(
        RefreshRequest(history="all", aggregate_only=False, execution="sync"),
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        refresh_fn=refresh,
        planner=lambda *_args, **_kwargs: RefreshPlan("async", "synthetic", 5, 9),
    )

    assert completed.job is None
    assert completed.result is not None
    assert completed.result["schema"] == "codex-usage-tracker.refresh.v2"
    assert completed.result["refresh"]["parsed_events"] == 3  # type: ignore[index]
    assert completed.result["planner"]["reason"] == "explicit_sync"  # type: ignore[index]
    assert completed.result["accounting"] == {
        "canonical_rows": 0,
        "copied_rows_excluded": 0,
        "credit_coverage": None,
        "history_scope": "all",
        "physical_rows": 0,
        "pricing_coverage": None,
        "privacy_mode": "normal",
        "schema": "codex-usage-tracker.accounting-context.v1",
        "service_tier_coverage": None,
    }
    assert calls[0]["include_archived"] is True
    assert calls[0]["aggregate_only"] is False


def test_same_injected_service_reuses_active_equivalent_async_job(tmp_path: Path) -> None:
    release = threading.Event()
    service = JobService()

    def refresh(**_kwargs: object) -> RefreshResult:
        assert release.wait(timeout=2)
        return RefreshResult(0, 0, 0, str(tmp_path / "usage.sqlite3"))

    kwargs = {
        "codex_home": tmp_path / ".codex",
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "job_service": service,
        "refresh_fn": refresh,
        "planner": lambda *_args, **_kwargs: RefreshPlan("async", "synthetic", 5, 9),
    }
    first = refresh_usage(RefreshRequest(execution="async"), **kwargs)  # type: ignore[arg-type]
    second = refresh_usage(RefreshRequest(execution="async"), **kwargs)  # type: ignore[arg-type]
    release.set()

    assert first.job is not None
    assert second.job is not None
    assert second.job.job_id == first.job.job_id


def _planner_db(path: Path, tracked: list[tuple[str, int]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE source_files (source_file TEXT, is_archived INTEGER)")
        conn.executemany("INSERT INTO source_files VALUES (?, ?)", tracked or [])


@pytest.mark.parametrize(
    ("case", "plans"),
    [
        ("untracked", lambda path: [SourceParsePlan(path)]),
        ("truncated", lambda path: [SourceParsePlan(path, replace_existing=True)]),
        ("identity_changed", lambda path: [SourceParsePlan(path, replace_existing=True)]),
        ("prefix_mismatch", lambda path: [SourceParsePlan(path, replace_existing=True)]),
        ("parser_state_changed", lambda path: [SourceParsePlan(path, replace_existing=True)]),
    ],
)
def test_full_replacement_classifications_are_async(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    plans: object,
) -> None:
    del case
    source = tmp_path / "events.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    db_path = tmp_path / "usage.sqlite3"
    _planner_db(db_path)
    monkeypatch.setattr(refresh_module, "find_session_logs", lambda *_args, **_kwargs: [source])
    monkeypatch.setattr(
        refresh_module,
        "source_logs_requiring_parse",
        lambda _conn, _logs: plans(source),  # type: ignore[operator]
    )

    plan = plan_refresh(RefreshRequest(), codex_home=tmp_path, db_path=db_path)

    assert plan.execution == "async"
    assert plan.reason == "unsafe_source_change"


@pytest.mark.parametrize(
    ("count", "added_bytes", "expected"),
    [
        (1, 64, "sync"),
        (MAX_SYNC_SOURCE_FILES, 64, "sync"),
        (MAX_SYNC_SOURCE_FILES + 1, 64, "async"),
        (1, MAX_SYNC_ADDED_BYTES, "sync"),
        (1, MAX_SYNC_ADDED_BYTES + 1, "async"),
    ],
)
def test_append_threshold_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    added_bytes: int,
    expected: str,
) -> None:
    sources = [tmp_path / f"events-{index}.jsonl" for index in range(count)]
    for source in sources:
        source.write_bytes(b"x" * added_bytes)
    db_path = tmp_path / "usage.sqlite3"
    _planner_db(db_path, [(str(source), 0) for source in sources])
    monkeypatch.setattr(refresh_module, "find_session_logs", lambda *_args, **_kwargs: sources)
    monkeypatch.setattr(
        refresh_module,
        "source_logs_requiring_parse",
        lambda _conn, _logs: [
            SourceParsePlan(source, start_byte=0, replace_existing=False) for source in sources
        ],
    )

    plan = plan_refresh(RefreshRequest(), codex_home=tmp_path, db_path=db_path)

    assert plan.execution == expected


def test_missing_and_unreadable_sources_are_async(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _planner_db(db_path, [(str(tmp_path / "missing.jsonl"), 0)])
    monkeypatch.setattr(refresh_module, "find_session_logs", lambda *_args, **_kwargs: [])
    assert (
        plan_refresh(RefreshRequest(), codex_home=tmp_path, db_path=db_path).reason
        == "missing_source"
    )

    unreadable = tmp_path / "unreadable.jsonl"
    unreadable.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(refresh_module, "find_session_logs", lambda *_args, **_kwargs: [unreadable])
    monkeypatch.setattr(refresh_module.os, "access", lambda *_args: False)
    plan = plan_refresh(RefreshRequest(), codex_home=tmp_path, db_path=db_path)
    assert plan.execution == "async"
    assert plan.reason == "uncertain_source_state"


def test_auto_async_replans_in_worker_and_failure_is_privacy_safe(tmp_path: Path) -> None:
    planner_calls = 0
    service = JobService()

    def planner(*_args: object, **_kwargs: object) -> RefreshPlan:
        nonlocal planner_calls
        planner_calls += 1
        return RefreshPlan("async", "unsafe_source_change", 1, 0)

    def fail(**_kwargs: object) -> RefreshResult:
        raise RuntimeError("SYNTHETIC_PRIVATE_REFRESH_FAILURE")

    outcome = refresh_usage(
        RefreshRequest(execution="auto"),
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        job_service=service,
        refresh_fn=fail,
        planner=planner,
    )
    assert outcome.job is not None
    for _attempt in range(100):
        status = service.status(outcome.job.job_id)
        if status.state == "failed":
            break
        time.sleep(0.005)

    assert planner_calls == 2
    assert status.state == "failed"
    assert status.error is not None
    assert "SYNTHETIC_PRIVATE_REFRESH_FAILURE" not in json.dumps(status.to_payload())
