from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
)
from codex_usage_tracker.store.api import query_status_context_facts, upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.home_queries import (
    query_home_finding_rows,
    query_home_recent_evidence_rows,
    query_home_usage_metrics,
)
from tests.store_dashboard_helpers import _usage_event


def test_home_queries_are_active_bounded_and_narrow(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active_events = [
        _usage_event(
            record_id=f"record-{index}",
            session_id=f"session-{index}",
            thread_key=f"thread:Thread {index}",
            event_timestamp=f"2026-07-21T0{index}:00:00Z",
            cumulative_total_tokens=1_000 + index,
        )
        for index in range(7)
    ]
    archived = replace(
        _usage_event(
            record_id="archived-record",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=9_999,
        ),
        is_archived=1,
    )
    events = [*active_events, archived]
    upsert_usage_events(events, db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id for event in events])
        for index, event in enumerate(events):
            conn.execute(
                """
                UPDATE recommendation_facts
                SET recommendation_score = ?,
                    primary_recommendation_key = 'context-bloat',
                    recommendations_json = ?
                WHERE record_id = ?
                """,
                (
                    90 + index,
                    '[{"key":"context-bloat","severity":"high","title":"High context"}]',
                    event.record_id,
                ),
            )

    findings = query_home_finding_rows(db_path=db_path, limit=999, min_score=80)
    recent = query_home_recent_evidence_rows(db_path=db_path, limit=999)

    assert [row["record_id"] for row in findings] == ["record-6", "record-5", "record-4"]
    assert all(set(row) == {
        "record_id",
        "fact_primary_recommendation_key",
        "fact_recommendations_json",
    } for row in findings)
    assert [row["record_id"] for row in recent] == [
        "record-6",
        "record-5",
        "record-4",
        "record-3",
        "record-2",
    ]
    assert all(set(row) == {
        "record_id",
        "event_timestamp",
        "thread_name",
        "session_id",
        "model",
        "total_tokens",
    } for row in recent)


def test_home_usage_metrics_use_current_canonical_materialization(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="active-session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=2_500,
        ),
        is_archived=1,
    )
    upsert_usage_events([active, archived], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[active.record_id, archived.record_id])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.25,
                usage_credits = 3.5
            WHERE record_id = 'active'
            """
        )
        conn.execute("DELETE FROM refresh_meta WHERE key = 'home_usage_metrics_v1'")

    metrics = query_home_usage_metrics(db_path=db_path)

    assert metrics is not None
    assert metrics["calls"] == 1
    assert metrics["total_tokens"] == active.total_tokens
    assert metrics["estimated_cost_usd"] == 1.25
    assert metrics["usage_credits"] == 3.5
    assert metrics["pricing_coverage"] == 1.0
    assert metrics["credit_coverage"] == 1.0


def test_status_context_uses_current_active_home_materialization(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    active = _usage_event(
        record_id="active",
        session_id="active-session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    archived = replace(
        _usage_event(
            record_id="archived",
            session_id="archived-session",
            thread_key="thread:Archived",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=2_500,
        ),
        is_archived=1,
    )
    upsert_usage_events([active, archived], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[active.record_id, archived.record_id])
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.25, usage_credits = 3.5
            WHERE record_id = 'active'
            """
        )
        conn.execute("DELETE FROM refresh_meta WHERE key = 'home_usage_metrics_v1'")

    facts = query_status_context_facts(
        db_path,
        scope={"history": "active", "filters": {}},
        priced_models={"gpt-5.5"},
        credit_models={"gpt-5.5"},
    )

    assert facts["physical_rows"] == 1
    assert facts["canonical_rows"] == 1
    assert facts["copied_rows_excluded"] == 0
    assert facts["latest_indexed_event_at"] == active.event_timestamp
    assert facts["pricing_coverage"] == 1.0
    assert facts["credit_coverage"] == 1.0
    assert facts["service_tier_coverage"] == 0.0
    assert facts["source_revision"] == "generation:1"


def test_status_context_preserves_token_weighted_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    priced = replace(
        _usage_event(
            record_id="priced",
            session_id="priced-session",
            thread_key="thread:Priced",
            event_timestamp="2026-07-21T08:00:00Z",
            cumulative_total_tokens=110,
        ),
        service_tier="priority",
    )
    unpriced = replace(
        _usage_event(
            record_id="unpriced",
            session_id="unpriced-session",
            thread_key="thread:Unpriced",
            event_timestamp="2026-07-21T09:00:00Z",
            cumulative_total_tokens=1_110,
        ),
        model="unpriced-model",
        input_tokens=1_000,
        cached_input_tokens=0,
        output_tokens=100,
        reasoning_output_tokens=10,
        total_tokens=1_100,
    )
    upsert_usage_events([priced, unpriced], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(
            conn,
            record_ids=[priced.record_id, unpriced.record_id],
        )
        conn.execute(
            """
            UPDATE recommendation_facts
            SET estimated_cost_usd = 1.0, usage_credits = 1.0
            WHERE record_id = 'priced'
            """
        )
        conn.execute("DELETE FROM refresh_meta WHERE key = 'home_usage_metrics_v1'")

    facts = query_status_context_facts(
        db_path,
        scope={"history": "active", "filters": {}},
        priced_models={"gpt-5.5"},
        credit_models={"gpt-5.5"},
    )

    expected = priced.total_tokens / (priced.total_tokens + unpriced.total_tokens)
    assert facts["pricing_coverage"] == expected
    assert facts["credit_coverage"] == expected
    assert facts["service_tier_coverage"] == expected


def test_home_usage_metrics_omit_stale_materialization(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="active",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])
        conn.execute(
            "UPDATE recommendation_fact_state SET source_generation = source_generation - 1"
        )

    assert query_home_usage_metrics(db_path=db_path) is None
