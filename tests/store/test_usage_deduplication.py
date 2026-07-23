from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.recommendation_engine.materialization import (
    backfill_recommendation_facts,
)
from codex_usage_tracker.store.allowance_materialization import materialize_allowance_intelligence
from codex_usage_tracker.store.api import connect, upsert_usage_events
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_event_count,
    query_dashboard_events,
    query_dashboard_token_summary,
)
from codex_usage_tracker.store.dedupe_queries import (
    query_dedupe_counts,
    query_dedupe_diagnostics,
)
from codex_usage_tracker.store.summary_queries import query_summary
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_event_count,
    query_usage_api_events,
)
from codex_usage_tracker.store.usage_record_queries import query_most_expensive_calls


def test_clone_copy_is_physical_but_not_billable(tmp_path: Path) -> None:
    original = _event("original", "/original.jsonl")
    copied = replace(
        original,
        record_id="clone",
        session_id="clone",
        source_file="/clone.jsonl",
        event_timestamp="2026-07-14T12:01:00Z",
        turn_timestamp="2026-07-14T12:01:00Z",
    )
    new = replace(
        copied,
        record_id="new",
        event_timestamp="2026-07-14T12:02:00Z",
        turn_id="new-turn",
        turn_timestamp="2026-07-14T12:02:00Z",
    )
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original, copied, new], db_path)
    with connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM usage_events").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0] == 2
        assert (
            conn.execute(
                "SELECT duplicate_reason FROM usage_events WHERE is_duplicate=1"
            ).fetchone()[0]
            == "copied_usage_fingerprint"
        )


def test_copied_allowance_rows_do_not_contribute_intervals_or_generation(tmp_path: Path) -> None:
    first = replace(
        _event("first", "/first.jsonl"),
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=10080,
        rate_limit_primary_resets_at=2_000_000_000,
        total_tokens=100,
        cumulative_total_tokens=100,
    )
    second = replace(
        first,
        record_id="second",
        turn_id="second-turn",
        source_file="/second.jsonl",
        event_timestamp="2026-07-14T12:01:00Z",
        turn_timestamp="2026-07-14T12:01:00Z",
        rate_limit_primary_used_percent=20.0,
        total_tokens=200,
        cumulative_total_tokens=300,
    )
    copied_first = replace(first, record_id="copied-first", session_id="copy", source_file="/copy-1.jsonl")
    copied_second = replace(second, record_id="copied-second", session_id="copy", source_file="/copy-2.jsonl")
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([first, second, copied_first, copied_second], db_path)

    with connect(db_path) as conn:
        assert materialize_allowance_intelligence(
            conn, now=datetime(2026, 7, 14, tzinfo=timezone.utc)
        )
        assert conn.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0] == 2
        assert conn.execute("SELECT canonical_tokens FROM allowance_cycles").fetchone()[0] == 300
        assert conn.execute("SELECT total_tokens FROM allowance_intervals").fetchone()[0] == 200
        generation, revision = conn.execute(
            "SELECT allowance_generation, source_revision FROM allowance_source_state"
        ).fetchone()

        conn.execute(
            "UPDATE usage_events SET rate_limit_primary_used_percent=99 WHERE record_id='copied-second'"
        )
        assert not materialize_allowance_intelligence(conn, now=datetime(2026, 7, 14, tzinfo=timezone.utc))
        assert tuple(
            conn.execute(
                "SELECT allowance_generation, source_revision FROM allowance_source_state"
            ).fetchone()
        ) == (generation, revision)

    updated_second = replace(second, rate_limit_primary_used_percent=25.0)
    upsert_usage_events([updated_second], db_path)
    with connect(db_path) as conn:
        assert materialize_allowance_intelligence(
            conn, now=datetime(2026, 7, 14, tzinfo=timezone.utc)
        )
        updated_generation, updated_revision = conn.execute(
            "SELECT allowance_generation, source_revision FROM allowance_source_state"
        ).fetchone()
        assert updated_generation == generation + 1
        assert updated_revision != revision


def test_source_replacement_promotes_surviving_copy(tmp_path: Path) -> None:
    original = replace(
        _event("original", "/original.jsonl"),
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=300,
    )
    copied = replace(original, record_id="copy", session_id="copy", source_file="/copy.jsonl")
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original, copied], db_path)
    with connect(db_path) as conn:
        backfill_recommendation_facts(conn)
    upsert_usage_events([], db_path, replace_source_files=[Path("/original.jsonl")])
    with connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0] == 1
        row = conn.execute("SELECT is_duplicate, duplicate_reason FROM usage_events").fetchone()
        allowance_record_ids = {
            value[0] for value in conn.execute("SELECT record_id FROM allowance_observations")
        }
        recommendation_record_ids = {
            value[0] for value in conn.execute("SELECT record_id FROM recommendation_facts")
        }
        recommendation_state = conn.execute(
            "SELECT COUNT(*) FROM recommendation_fact_state"
        ).fetchone()[0]
    assert tuple(row) == (0, None)
    assert allowance_record_ids == {"copy"}
    assert recommendation_record_ids == set()
    assert recommendation_state == 0


def test_default_usage_surfaces_exclude_copied_clone_rows(tmp_path: Path) -> None:
    original = replace(
        _event("original", "/original.jsonl"),
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=300,
    )
    copied = replace(
        original,
        record_id="clone",
        session_id="clone",
        source_file="/clone.jsonl",
        event_timestamp="2026-07-14T12:01:00Z",
        turn_timestamp="2026-07-14T12:01:00Z",
    )
    new = replace(
        copied,
        record_id="new",
        event_timestamp="2026-07-14T12:02:00Z",
        turn_id="new-turn",
        turn_timestamp="2026-07-14T12:02:00Z",
        total_tokens=125,
    )
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original, copied, new], db_path)

    assert query_dashboard_event_count(db_path) == 2
    assert len(query_dashboard_events(db_path)) == 2
    assert query_dashboard_token_summary(db_path)["total_tokens"] == 225
    assert query_usage_api_event_count(db_path) == 2
    assert len(query_usage_api_events(db_path)) == 2
    assert query_summary(db_path, group_by="model")[0]["model_calls"] == 2
    assert len(query_most_expensive_calls(db_path)) == 2
    with connect(db_path) as conn:
        recommendation_rows = backfill_recommendation_facts(conn)
        active_threads = conn.execute(
            """
            SELECT SUM(call_count), SUM(total_tokens)
            FROM thread_summaries
            WHERE is_archived_scope = 'active'
            """
        ).fetchone()
        allowance_rows = conn.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0]
    assert tuple(active_threads) == (2, 225)
    assert allowance_rows == 2
    assert recommendation_rows == 2

    diagnostics = query_dedupe_diagnostics(db_path, limit=10)
    assert query_dedupe_counts(db_path) == {
        "physical_rows": 3,
        "canonical_rows": 2,
        "excluded_copied_rows": 1,
    }
    assert diagnostics["summary"] == {
        "dedupe_enabled": True,
        "fingerprint_version": "usage-fingerprint-v2",
        "physical_rows": 3,
        "canonical_rows": 2,
        "excluded_copied_rows": 1,
        "duplicate_fingerprint_groups": 1,
        "physical_total_tokens": 325,
        "excluded_total_tokens": 100,
        "canonical_total_tokens": 225,
        "duplicate_reasons": {"copied_usage_fingerprint": 1},
    }
    assert diagnostics["row_count"] == 1
    assert diagnostics["rows"][0]["record_id"] == "clone"
    assert diagnostics["rows"][0]["duplicate_of_record_id"] == "original"
    assert diagnostics["rows"][0]["source_file"] == "/clone.jsonl"


def _event(record_id: str, source_file: str) -> UsageEvent:
    return UsageEvent(
        record_id,
        "original",
        None,
        None,
        "2026-07-14T12:00:00Z",
        source_file,
        1,
        "turn",
        "2026-07-14T11:59:00Z",
        None,
        "gpt-5.5",
        "high",
        None,
        None,
        None,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        258400,
        90,
        20,
        10,
        5,
        100,
        190,
        40,
        20,
        10,
        200,
    )
