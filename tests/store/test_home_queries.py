from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
)
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.home_queries import (
    query_home_finding_rows,
    query_home_recent_evidence_rows,
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
