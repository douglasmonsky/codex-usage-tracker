from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    CompressionCandidate,
    EstimateRange,
)
from codex_usage_tracker.store import compression_candidates as candidate_store
from codex_usage_tracker.store.compression_candidates import (
    get_compression_candidate,
    list_compression_candidates,
    replace_compression_candidates,
)
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    delete_stale_compression_runs,
    find_compression_run,
    get_compression_run,
    update_compression_run,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


class CacheKey(TypedDict):
    source_revision: str
    scope_hash: str
    detector_set_version: str
    estimator_version: str
    compression_schema_version: int
    scope: dict[str, bool]


def test_exact_cache_key_reuses_only_completed_run(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    created = create_compression_run(
        db_path,
        run_id="run-1",
        **cache_key("rev-1"),
    )

    assert created["status"] == "pending"
    assert find_compression_run(db_path, **cache_key("rev-1")) is None

    completed = update_compression_run(
        db_path,
        run_id="run-1",
        status="completed",
        progress_percent=100,
        stage="complete",
        aggregate_profile={"likely_savings": 321},
    )

    assert completed is not None
    assert completed["aggregate_profile"] == {"likely_savings": 321}
    cached = find_compression_run(db_path, **cache_key("rev-1"))
    assert cached is not None
    assert cached["run_id"] == "run-1"
    assert find_compression_run(db_path, **cache_key("rev-2")) is None


def test_run_updates_preserve_monotonic_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))

    update_compression_run(db_path, run_id="run-1", progress_percent=60, stage="detectors")
    run = update_compression_run(
        db_path,
        run_id="run-1",
        progress_percent=20,
        stage="stale-update",
    )

    assert run is not None
    assert run["progress_percent"] == 60
    assert run["stage"] == "stale-update"


def test_candidate_replace_lists_compact_rows_and_reconstructs_detail(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))
    candidates = [
        candidate("cmp_low", likely=30).as_dict(),
        candidate("cmp_high", likely=80).as_dict(),
    ]

    assert replace_compression_candidates(db_path, run_id="run-1", candidates=candidates) == 2
    assert replace_compression_candidates(db_path, run_id="run-1", candidates=candidates) == 2

    page = list_compression_candidates(
        db_path,
        run_id="run-1",
        min_likely_savings=50,
        limit=10,
    )
    assert page["total"] == 1
    assert page["rows"][0]["candidate_id"] == "cmp_high"
    assert "claims" not in page["rows"][0]
    assert "evidence_handles" not in page["rows"][0]

    detail = get_compression_candidate(db_path, candidate_id="cmp_high")
    assert detail is not None
    assert detail["claims"] == [
        {
            "record_id": "record-cmp_high",
            "component": "uncached_input",
            "exposure_tokens": 100,
            "estimate": {"low": 10, "likely": 80, "high": 90},
            "evidence_role": "supporting",
            "trace_handle": {"record_id": "record-cmp_high"},
        }
    ]
    assert detail["overlapping_candidate_ids"] == ["cmp_other"]

    replace_compression_candidates(
        db_path,
        run_id="run-1",
        candidates=[candidate("cmp_new", likely=40).as_dict()],
    )
    assert get_compression_candidate(db_path, candidate_id="cmp_high") is None
    run = get_compression_run(db_path, run_id="run-1")
    assert run is not None
    assert run["candidate_count"] == 1


def test_candidate_record_metadata_migration_backfills_existing_claims(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))
    replace_compression_candidates(
        db_path,
        run_id="run-1",
        candidates=[candidate("cmp_old", likely=40).as_dict()],
    )
    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO usage_events (
                record_id, session_id, event_timestamp, source_file, line_number,
                model, effort, thread_key, input_tokens, cached_input_tokens,
                output_tokens, reasoning_output_tokens, total_tokens,
                cumulative_input_tokens, cumulative_cached_input_tokens,
                cumulative_output_tokens, cumulative_reasoning_output_tokens,
                cumulative_total_tokens, uncached_input_tokens, cache_ratio,
                reasoning_output_ratio, context_window_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            """,
            (
                "record-cmp_old",
                "session-old",
                "2026-07-12T12:00:00+00:00",
                "/synthetic/old.jsonl",
                1,
                "gpt-migrated",
                "high",
                "thread:migrated",
            ),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version = 19")
        conn.execute("PRAGMA user_version = 18")
    with connect(db_path) as conn:
        init_db(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 26
    with connect(db_path) as conn:
        conn.execute("DELETE FROM usage_events WHERE record_id = ?", ("record-cmp_old",))

    detail = get_compression_candidate(db_path, candidate_id="cmp_old")
    assert detail is not None
    assert detail["claims"][0]["model"] == "gpt-migrated"
    assert detail["claims"][0]["thread_key"] == "thread:migrated"
    assert detail["claims"][0]["event_timestamp"] == "2026-07-12T12:00:00+00:00"
    page = list_compression_candidates(
        db_path,
        run_id="run-1",
        model="gpt-migrated",
        thread="thread:migrated",
    )
    assert [row["candidate_id"] for row in page["rows"]] == ["cmp_old"]


def test_candidate_page_count_and_rows_share_one_sqlite_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))
    replace_compression_candidates(
        db_path,
        run_id="run-1",
        candidates=[candidate("cmp_snapshot", likely=40).as_dict()],
    )
    original_connect = candidate_store.connect
    writer_committed = False

    @contextmanager
    def interleaved_connect(path: Path) -> Iterator[sqlite3.Connection]:
        nonlocal writer_committed
        with original_connect(path) as conn:

            def interleave(statement: str) -> None:
                nonlocal writer_committed
                if writer_committed or "SELECT c.*" not in statement:
                    return
                with sqlite3.connect(path) as writer:
                    writer.execute("DELETE FROM compression_candidate_records")
                    writer.execute("DELETE FROM compression_candidates")
                writer_committed = True

            conn.set_trace_callback(interleave)
            yield conn

    monkeypatch.setattr(candidate_store, "connect", interleaved_connect)
    page = candidate_store.list_compression_candidates(db_path, run_id="run-1")

    assert writer_committed is True
    assert page["total"] == 1
    assert [row["candidate_id"] for row in page["rows"]] == ["cmp_snapshot"]


def test_delete_stale_runs_leaves_active_and_recent_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    create_compression_run(
        db_path,
        run_id="old-complete",
        status="completed",
        created_at=old,
        **cache_key("rev-old"),
    )
    create_compression_run(
        db_path,
        run_id="old-running",
        status="running",
        created_at=old,
        **cache_key("rev-running"),
    )
    create_compression_run(db_path, run_id="recent", **cache_key("rev-recent"))

    assert delete_stale_compression_runs(db_path, before=cutoff) == 1
    assert get_compression_run(db_path, run_id="old-complete") is None
    assert get_compression_run(db_path, run_id="old-running") is not None
    assert get_compression_run(db_path, run_id="recent") is not None


def cache_key(source_revision: str) -> CacheKey:
    return {
        "source_revision": source_revision,
        "scope_hash": "scope-1",
        "detector_set_version": "detectors-v1",
        "estimator_version": "estimator-v1",
        "compression_schema_version": 1,
        "scope": {"include_archived": False},
    }


def candidate(candidate_id: str, *, likely: int) -> CompressionCandidate:
    estimate = EstimateRange(low=10, likely=likely, high=90)
    record_id = f"record-{candidate_id}"
    draft = CandidateDraft(
        candidate_id=candidate_id,
        family="stale_context",
        pattern="Large context with little output",
        pattern_key=f"thread:{candidate_id}",
        detector_version="stale-v1",
        estimator_version="estimator-v1",
        record_ids=(record_id,),
        thread_keys=("thread-1",),
        observation_count=1,
        observed_exposure=ComponentExposure(uncached_input=100),
        claims=(
            ComponentClaim(
                record_id=record_id,
                component="uncached_input",
                exposure_tokens=100,
                estimate=estimate,
            ),
        ),
        gross_estimate=estimate,
        confidence_grade="medium",
        confidence_score=0.7,
        confidence_reasons=("synthetic evidence",),
        estimator_tier="fallback",
        estimator_name="synthetic-estimator",
        estimator_assumptions=("test assumption",),
        evidence_handles=({"record_id": record_id},),
        intervention={"family": "fresh_handoff"},
        verification={"tool": "usage_compression_profile"},
        first_seen="2026-07-01T00:00:00+00:00",
        last_seen="2026-07-02T00:00:00+00:00",
    )
    return CompressionCandidate(
        draft=draft,
        adjusted_estimate=estimate,
        overlapping_candidate_ids=("cmp_other",),
    )
