from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
)
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.recommendation_queries import (
    query_recommendation_fact_page,
)
from tests.store_dashboard_helpers import _usage_event


def test_recommendation_fact_page_orders_and_counts_before_limiting(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    events = [
        replace(
            _usage_event(
                record_id="lower-score",
                session_id="session-lower",
                thread_key="thread:lower",
                event_timestamp="2026-07-13T12:00:00Z",
                cumulative_total_tokens=900_000,
            ),
            total_tokens=900,
        ),
        replace(
            _usage_event(
                record_id="higher-score",
                session_id="session-higher",
                thread_key="thread:higher",
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
            "UPDATE recommendation_facts SET recommendation_score = 10 WHERE record_id = ?",
            ("lower-score",),
        )
        conn.execute(
            "UPDATE recommendation_facts SET recommendation_score = 20 WHERE record_id = ?",
            ("higher-score",),
        )

    page = query_recommendation_fact_page(db_path=db_path, limit=1)

    assert page.total_count == 2
    assert [row["record_id"] for row in page.rows] == ["higher-score"]
    assert page.rows[0]["fact_recommendation_score"] == 20
