from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.recommendation_engine.materialization import (
    backfill_recommendation_facts,
)
from codex_usage_tracker.store.allowance_observations import (
    sync_allowance_observations_for_record_ids,
)
from codex_usage_tracker.store.api import connect, init_db, upsert_usage_events
from codex_usage_tracker.store.deduplication_schema import _rebuild_canonical_derivatives
from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries
from tests.store.test_store_migrations import _write_legacy_usage_database
from tests.store.test_usage_deduplication import _event


def test_new_database_has_canonical_usage_schema_and_index(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(usage_events)")}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(usage_events)")}
        view = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='canonical_usage_events'"
        ).fetchone()
        plan = [
            str(row["detail"])
            for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT record_id FROM usage_events "
                "WHERE usage_fingerprint=? AND is_duplicate=0 LIMIT 1",
                ("usage-fingerprint-v2:test",),
            )
        ]

    assert {
        "upstream_usage_id",
        "usage_fingerprint",
        "canonical_record_id",
        "is_duplicate",
        "duplicate_reason",
    } <= columns
    assert {
        "idx_usage_fingerprint",
        "idx_usage_canonical_record_id",
        "idx_usage_duplicate_reason",
        "idx_usage_canonical_fingerprint",
    } <= indexes
    assert view is not None and "WHEREis_duplicate=0" in str(view["sql"]).replace(" ", "")
    assert any("idx_usage_" in detail for detail in plan)


def test_v23_backfill_marks_copied_legacy_usage_duplicate(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path)
    with sqlite3.connect(db_path) as raw:
        raw.execute(
            "INSERT INTO usage_events SELECT ?, ?, event_timestamp, ?, ?, input_tokens, "
            "cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens, "
            "cumulative_input_tokens, cumulative_cached_input_tokens, cumulative_output_tokens, "
            "cumulative_reasoning_output_tokens, cumulative_total_tokens, uncached_input_tokens, "
            "cache_ratio, reasoning_output_ratio, context_window_percent FROM usage_events",
            ("copied-record", "copied-session", "/tmp/copied.jsonl", 99),
        )
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            "SELECT usage_fingerprint, canonical_record_id, is_duplicate, duplicate_reason "
            "FROM usage_events ORDER BY record_id"
        ).fetchall()
        canonical = conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0]

    assert len({row["usage_fingerprint"] for row in rows}) == 1
    assert len({row["canonical_record_id"] for row in rows}) == 1
    assert canonical == 1
    assert [row["duplicate_reason"] for row in rows if row["is_duplicate"]] == [
        "copied_usage_fingerprint"
    ]


def test_v25_reclassifies_clone_rewritten_timestamps(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    original = _event("original", "/original.jsonl")
    copied = replace(
        original,
        record_id="copy",
        session_id="clone",
        source_file="/clone.jsonl",
        event_timestamp="2026-07-15T12:00:00Z",
        turn_timestamp="2026-07-15T12:00:00Z",
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=300,
    )
    original = replace(
        original,
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=300,
    )
    upsert_usage_events([original, copied], db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE usage_events SET usage_fingerprint='usage-fingerprint-v1:' || record_id, "
            "canonical_record_id='legacy-' || record_id, is_duplicate=0, duplicate_reason=NULL"
        )
        rebuild_thread_summaries(conn)
        sync_allowance_observations_for_record_ids(conn, ["original", "copy"])
        backfill_recommendation_facts(conn)
        conn.execute("DELETE FROM schema_migrations WHERE version=25")
        conn.execute("PRAGMA user_version=24")

    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            "SELECT usage_fingerprint, is_duplicate FROM usage_events ORDER BY record_id"
        ).fetchall()
        thread_calls = conn.execute(
            "SELECT SUM(call_count) FROM thread_summaries WHERE is_archived_scope='active'"
        ).fetchone()[0]
        allowance_count = conn.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0]
        recommendation_count = conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[
            0
        ]

    assert len({row["usage_fingerprint"] for row in rows}) == 1
    assert [row["is_duplicate"] for row in rows] == [1, 0]
    assert thread_calls == 1
    assert allowance_count == 1
    assert recommendation_count == 1


def test_canonical_rebuild_discards_stale_allowance_intelligence(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with connect(db_path) as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO allowance_source_state "
            "(state_id, allowance_generation, source_revision, observation_count, "
            "latest_observed_at, model_version, rebuilt_at) "
            "VALUES (1, 1, 'stale', 1, '2026-07-15T00:00:00Z', 'v1', '2026-07-15T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO allowance_cycles "
            "(cycle_id, window_kind, window_key, cohort_key, source_revision) "
            "VALUES ('stale-cycle', 'primary', 'primary', 'codex', 'stale')"
        )
        conn.execute(
            "INSERT INTO allowance_intervals "
            "(interval_id, cycle_id, window_kind, window_key, cohort_key, point_kind, source_revision) "
            "VALUES ('stale-interval', 'stale-cycle', 'primary', 'primary', 'codex', 'anchor', 'stale')"
        )
        _rebuild_canonical_derivatives(conn)
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("allowance_source_state", "allowance_cycles", "allowance_intervals")
        ]

    assert counts == [0, 0, 0]
