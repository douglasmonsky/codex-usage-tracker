from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.application import allowance
from codex_usage_tracker.application.allowance import AllowanceAnalysisRuntime, get_allowance
from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.application.errors import RequestContextError, RequestValidationError
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def _seed(db_path: Path, *, revision: str = "allowance-r1") -> None:
    with connect(db_path) as connection:
        init_db(connection)
        connection.execute(
            "INSERT INTO allowance_source_state VALUES "
            "(1, 1, ?, 2, '2026-07-22T11:00:00+00:00', 'reset-aware-v2', "
            "'2026-07-22T11:00:00+00:00')",
            (revision,),
        )
        connection.executemany(
            """INSERT INTO allowance_cycles
            (cycle_id,window_kind,window_key,cohort_key,is_archived,reset_at,
             first_observed_at,last_observed_at,latest_used_percent,
             observation_count,canonical_observation_count,canonical_tokens,
             quality_grade,status,cycle_state,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    "week",
                    "weekly",
                    "primary",
                    "codex",
                    0,
                    1_786_000_000,
                    "2026-07-21T10:00:00+00:00",
                    "2026-07-22T11:00:00+00:00",
                    40,
                    2,
                    2,
                    100,
                    "high",
                    "open",
                    "open",
                    revision,
                    "reset-aware-v2",
                ),
                (
                    "five",
                    "five_hour",
                    "secondary",
                    "codex",
                    0,
                    1_785_000_000,
                    "2026-07-22T10:00:00+00:00",
                    "2026-07-22T11:00:00+00:00",
                    10,
                    2,
                    2,
                    50,
                    "high",
                    "open",
                    "open",
                    revision,
                    "reset-aware-v2",
                ),
            ),
        )
        connection.executemany(
            """INSERT INTO allowance_intervals
            (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,
             end_observed_at,end_used_percent,point_kind,source_revision,model_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    "evidence-1",
                    "week",
                    "weekly",
                    "primary",
                    "codex",
                    0,
                    "2026-07-22T10:00:00+00:00",
                    39,
                    "positive",
                    revision,
                    "reset-aware-v2",
                ),
                (
                    "evidence-2",
                    "week",
                    "weekly",
                    "primary",
                    "codex",
                    0,
                    "2026-07-22T11:00:00+00:00",
                    40,
                    "positive",
                    revision,
                    "reset-aware-v2",
                ),
            ),
        )


def test_empty_and_stale_status_preserve_refresh_next_semantics(tmp_path: Path) -> None:
    empty = get_allowance(
        AllowanceRequest("status"), db_path=tmp_path / "empty.sqlite3", now=NOW
    ).payload
    assert empty["data_state"] == "empty"
    assert empty["next"] == {
        "action": "usage_refresh_start",
        "status_action": "usage_refresh_status",
        "then": "usage_allowance_status",
        "poll_after_ms": 60_000,
    }

    db_path = tmp_path / "stale.sqlite3"
    _seed(db_path)
    stale = get_allowance(
        AllowanceRequest("status"),
        db_path=db_path,
        now=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
    ).payload
    assert stale["data_state"] == "stale"
    assert stale["next"] == empty["next"]


def test_series_uses_finite_source_anchored_range_and_limits_target(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    result = get_allowance(AllowanceRequest("series"), db_path=db_path, now=NOW)

    assert result.payload["requested_range"] == {
        "preset": "8w",
        "start_at": "2026-05-27T11:00:00+00:00",
        "end_at": "2026-07-22T11:00:00+00:00",
    }
    assert result.range_start == "2026-05-27T11:00:00+00:00"
    assert result.range_end == "2026-07-22T11:00:00+00:00"


def test_evidence_cursor_binds_revision_window_and_source_anchored_range(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    first = get_allowance(AllowanceRequest("evidence", limit=1), db_path=db_path, now=NOW)
    cursor = first.payload["next_cursor"]
    assert cursor is not None

    second = get_allowance(
        AllowanceRequest("evidence", limit=1, cursor=str(cursor)),
        db_path=db_path,
        now=NOW.replace(hour=13),
    )
    assert second.payload["rows"]
    with pytest.raises(ValueError, match="scope"):
        get_allowance(
            AllowanceRequest("evidence", window="five_hour", limit=1, cursor=str(cursor)),
            db_path=db_path,
            now=NOW,
        )
    with pytest.raises(ValueError, match="scope"):
        get_allowance(
            AllowanceRequest("evidence", range="7d", limit=1, cursor=str(cursor)),
            db_path=db_path,
            now=NOW,
        )
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE allowance_source_state SET source_revision = 'allowance-r2' WHERE state_id=1"
        )
    with pytest.raises(ValueError, match="revision"):
        get_allowance(
            AllowanceRequest("evidence", limit=1, cursor=str(cursor)),
            db_path=db_path,
            now=NOW,
        )


@pytest.mark.parametrize(
    "analysis_status",
    ("insufficient_evidence", "supported_change", "supported_changes"),
)
def test_analysis_returns_every_existing_completed_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, analysis_status: str
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    completed = {
        "schema": "codex-usage-tracker-allowance-analysis-v2",
        "snapshot_id": "snapshot-current",
        "status": analysis_status,
        "boundaries": [] if analysis_status == "insufficient_evidence" else [{"id": "one"}],
    }
    monkeypatch.setattr(allowance, "_analysis_identity", lambda *_args, **_kwargs: completed)
    monkeypatch.setattr(allowance, "read_allowance_analysis", lambda *_args, **_kwargs: completed)

    result = get_allowance(
        AllowanceRequest("analysis", analysis_id="snapshot-current"), db_path=db_path
    )

    assert result.payload == completed
    assert result.result_schema == completed["schema"]
    with pytest.raises(RequestValidationError, match="analysis_id"):
        get_allowance(AllowanceRequest("analysis", analysis_id="snapshot-other"), db_path=db_path)


def test_analysis_execution_modes_reuse_one_generic_semantic_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    identity = {
        "snapshot_id": "a" * 64,
        "source_revision": "allowance-r1",
        "model_version": "detector-v1",
        "rate_card_revision": "rate-v1",
        "data_as_of": "2026-07-22T11:00:00+00:00",
        "parameters": {"min_cycles_per_regime": 4},
    }
    completed = {
        "schema": "codex-usage-tracker-allowance-analysis-v2",
        "snapshot_id": identity["snapshot_id"],
        "status": "insufficient_evidence",
        "boundaries": [],
    }
    monkeypatch.setattr(allowance, "_analysis_identity", lambda *_args, **_kwargs: identity)
    monkeypatch.setattr(allowance, "read_allowance_analysis", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(allowance, "build_allowance_analysis", lambda *_args, **_kwargs: completed)
    jobs = JobService()
    runtime = AllowanceAnalysisRuntime(jobs)

    synchronous = get_allowance(
        AllowanceRequest("analysis", execution="sync"),
        db_path=db_path,
        job_service=jobs,
        runtime=runtime,
    )
    assert synchronous.payload == completed

    first = get_allowance(
        AllowanceRequest("analysis", execution="async"),
        db_path=db_path,
        job_service=jobs,
        runtime=runtime,
    )
    second = get_allowance(
        AllowanceRequest("analysis"), db_path=db_path, job_service=jobs, runtime=runtime
    )
    assert first.payload["job_id"] == second.payload["job_id"]
    assert first.payload["kind"] == "allowance"
    deadline = time.monotonic() + 2
    while jobs.status(str(first.payload["job_id"])).state != "completed":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    detailed = jobs.status(str(first.payload["job_id"]), include_result=True).result
    assert isinstance(detailed, Mapping)
    assert detailed["snapshot_id"] == completed["snapshot_id"]
    assert detailed["status"] == completed["status"]


def test_analysis_runtime_atomically_reuses_one_semantic_job() -> None:
    jobs = JobService()
    runtime = AllowanceAnalysisRuntime(jobs)

    def worker() -> Mapping[str, object]:
        return {"schema": "codex-usage-tracker-allowance-analysis-v2"}

    def start() -> str:
        return runtime.start(
            semantic_key=request_hash("same-snapshot"),
            source_revision="allowance-r1",
            worker=worker,
        ).job_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(start) for _index in range(8)]
        job_ids = [future.result(timeout=2) for future in futures]
    assert len(set(job_ids)) == 1
    assert len(runtime._records) == 1


def test_analysis_runtime_bounds_records_and_reports_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(allowance, "MAX_SEMANTIC_JOBS", 2)
    jobs = JobService()
    runtime = AllowanceAnalysisRuntime(jobs)
    release = threading.Event()

    def blocked_worker() -> Mapping[str, object]:
        release.wait(timeout=2)
        return {"schema": "codex-usage-tracker-allowance-analysis-v2"}

    statuses = []
    for index in range(2):
        statuses.append(
            runtime.start(
                semantic_key=request_hash(f"snapshot-{index}"),
                source_revision="allowance-r1",
                worker=blocked_worker,
            )
        )
    with pytest.raises(RequestContextError, match="capacity"):
        runtime.start(
            semantic_key=request_hash("snapshot-over-capacity"),
            source_revision="allowance-r1",
            worker=lambda: {},
        )
    release.set()
    deadline = time.monotonic() + 2
    while any(jobs.status(status.job_id).state != "completed" for status in statuses):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    runtime.start(
        semantic_key=request_hash("snapshot-after-prune"),
        source_revision="allowance-r1",
        worker=lambda: {"schema": "codex-usage-tracker-allowance-analysis-v2"},
    )
    assert len(runtime._records) <= 2


def test_async_oversized_result_is_safely_omitted_from_generic_status() -> None:
    jobs = JobService()
    runtime = AllowanceAnalysisRuntime(jobs)
    status = runtime.start(
        semantic_key=request_hash("oversized-allowance-result"),
        source_revision="allowance-r1",
        worker=lambda: {
            "schema": "codex-usage-tracker-allowance-analysis-v2",
            "aggregate": ["x" * 4096 for _index in range(20)],
        },
    )
    deadline = time.monotonic() + 2
    while jobs.status(status.job_id).state != "completed":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    detailed = jobs.status(status.job_id, include_result=True)
    assert detailed.result is None
    assert detailed.error is not None
    assert detailed.error.code == "job.result_too_large"


def test_analysis_runtime_must_share_the_polling_job_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    identity = {
        "snapshot_id": "b" * 64,
        "source_revision": "allowance-r1",
        "model_version": "detector-v1",
        "rate_card_revision": "rate-v1",
        "data_as_of": "2026-07-22T11:00:00+00:00",
        "parameters": {},
    }
    monkeypatch.setattr(allowance, "_analysis_identity", lambda *_args: identity)
    monkeypatch.setattr(allowance, "read_allowance_analysis", lambda *_args, **_kwargs: None)

    with pytest.raises(RequestValidationError, match="JobService"):
        get_allowance(
            AllowanceRequest("analysis", execution="async"),
            db_path=db_path,
            job_service=JobService(),
            runtime=AllowanceAnalysisRuntime(JobService()),
        )
