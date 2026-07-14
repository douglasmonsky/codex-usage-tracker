from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.recommendation_engine import (
    summary_materialization as recommendation_summaries,
)
from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
    sync_thread_recommendation_summaries,
)
from codex_usage_tracker.store.api import init_db, upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.recommendation_queries import (
    query_recommendation_fact_page,
    query_recommendation_thread_summaries,
)
from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries
from tests.store_dashboard_helpers import _usage_event


def test_recommendation_fact_page_orders_and_counts_before_limiting(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _usage_event(
                record_id="lower-score",
                session_id="session-lower",
                thread_key="thread:shared",
                event_timestamp="2026-07-13T12:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            total_tokens=900,
        ),
        replace(
            _usage_event(
                record_id="higher-score",
                session_id="session-higher",
                thread_key="thread:shared",
                event_timestamp="2026-07-13T13:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            total_tokens=100,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id for event in events])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET recommendation_score = 10,
                primary_recommendation_key = 'lower',
                secondary_recommendation_keys_json = '["shared"]',
                recommendations_json = '[{"key":"lower","title":"Lower"}]'
            WHERE record_id = 'lower-score'
            """
        )
        conn.execute(
            """
            UPDATE recommendation_facts
            SET recommendation_score = 20,
                primary_recommendation_key = 'higher',
                secondary_recommendation_keys_json = '["shared"]',
                recommendations_json = '[{"key":"higher","title":"Higher"}]'
            WHERE record_id = 'higher-score'
            """
        )
        sync_thread_recommendation_summaries(conn)

    page = query_recommendation_fact_page(db_path=db_path, limit=1)

    assert page.total_count == 2
    assert [row["record_id"] for row in page.rows] == ["higher-score"]
    assert page.rows[0]["fact_recommendation_score"] == 20

    summaries = query_recommendation_thread_summaries(db_path=db_path, limit=1)

    assert summaries is not None
    assert summaries[0]["thread"] == "shared"
    assert summaries[0]["call_count"] == 2
    assert summaries[0]["session_count"] == 2
    assert summaries[0]["total_tokens"] == 1_000
    assert summaries[0]["recommendation_score"] == 30
    assert summaries[0]["primary_recommendation"] == {
        "key": "higher",
        "title": "Higher",
    }
    assert summaries[0]["secondary_signals"] == ["lower", "shared"]
    with connect(db_path) as conn:
        rebuild_thread_summaries(conn)

    assert query_recommendation_thread_summaries(db_path=db_path, limit=1) == summaries


def test_recommendation_thread_summaries_refresh_only_affected_threads(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = _thread_events("first", "second")
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id for event in events])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET recommendation_score = 10,
                recommendations_json = '[{"key":"initial"}]',
                primary_recommendation_key = 'initial'
            """
        )
        sync_thread_recommendation_summaries(conn)
        untouched_before = conn.execute(
            """
            SELECT recommendation_summary_json
            FROM thread_summaries
            WHERE thread_key = 'thread:second' AND is_archived_scope = 'active'
            """
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE recommendation_facts
            SET recommendation_score = 40,
                recommendations_json = '[{"key":"updated"}]',
                primary_recommendation_key = 'updated'
            WHERE record_id = 'record-first'
            """
        )
        sync_thread_recommendation_summaries(conn, thread_keys=("thread:first",))
        untouched_after = conn.execute(
            """
            SELECT recommendation_summary_json
            FROM thread_summaries
            WHERE thread_key = 'thread:second' AND is_archived_scope = 'active'
            """
        ).fetchone()[0]

    summaries = query_recommendation_thread_summaries(db_path=db_path, limit=2)

    assert summaries is not None
    assert [summary["thread"] for summary in summaries] == ["first", "second"]
    assert summaries[0]["recommendation_score"] == 40
    assert untouched_after == untouched_before


def test_v21_migration_backfills_all_summaries_before_incremental_refresh(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = _thread_events("first", "second")
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id for event in events])
        conn.execute("DROP INDEX idx_thread_summaries_scope_recommendations")
        conn.execute("ALTER TABLE thread_summaries DROP COLUMN recommendation_score")
        conn.execute("ALTER TABLE thread_summaries DROP COLUMN recommendation_total_tokens")
        conn.execute("ALTER TABLE thread_summaries DROP COLUMN recommendation_summary_json")
        conn.execute("ALTER TABLE recommendation_fact_state DROP COLUMN thread_summaries_complete")
        conn.execute("DELETE FROM schema_migrations WHERE version = 21")
        conn.execute("PRAGMA user_version = 20")
        init_db(conn)
        sync_recommendation_facts(conn, record_ids=[events[0].record_id])

    summaries = query_recommendation_thread_summaries(db_path=db_path, limit=10)

    assert summaries is not None
    assert {summary["thread"] for summary in summaries} == {"first", "second"}


def test_recommendation_thread_summaries_defer_noncanonical_threads(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = replace(
        _usage_event(
            record_id="child",
            session_id="child-session",
            thread_key="session:child-session",
            event_timestamp="2026-07-13T12:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        thread_name=None,
        parent_session_id="parent-session",
        parent_thread_name="parent",
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])

    assert query_recommendation_thread_summaries(db_path=db_path) is None


def test_incomplete_noncanonical_coverage_keeps_incremental_summary_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    canonical = _thread_events("first", "second")
    noncanonical = replace(
        _usage_event(
            record_id="child",
            session_id="child-session",
            thread_key="session:child-session",
            event_timestamp="2026-07-13T14:00:00Z",
            cumulative_total_tokens=900_000,
        ),
        thread_name=None,
        parent_session_id="parent-session",
        parent_thread_name="parent",
    )
    upsert_usage_events([*canonical, noncanonical], db_path=db_path)
    observed_scopes: list[tuple[str, ...] | None] = []
    original_reset = recommendation_summaries._reset_summaries

    with connect(db_path) as conn:
        sync_recommendation_facts(
            conn,
            record_ids=[event.record_id for event in canonical],
        )
        sync_recommendation_facts(conn, record_ids=[noncanonical.record_id])

        def capture_reset(
            target_conn: sqlite3.Connection,
            thread_keys: tuple[str, ...] | None,
        ) -> None:
            observed_scopes.append(thread_keys)
            original_reset(target_conn, thread_keys)

        monkeypatch.setattr(recommendation_summaries, "_reset_summaries", capture_reset)
        sync_recommendation_facts(conn, record_ids=[canonical[0].record_id])

    assert observed_scopes == [("thread:first",)]


def _thread_events(*threads: str):
    return [
        _usage_event(
            record_id=f"record-{thread}",
            session_id=f"session-{thread}",
            thread_key=f"thread:{thread}",
            event_timestamp=f"2026-07-13T1{index}:00:00Z",
            cumulative_total_tokens=900_000,
        )
        for index, thread in enumerate(threads)
    ]
