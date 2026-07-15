from pathlib import Path

from codex_usage_tracker.store.allowance_observations import query_allowance_observations
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_limited_history_returns_newest_observations_in_chronological_order(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id=f"rec-{day}",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp=f"2026-07-{day:02d}T00:00:00Z",
                cumulative_total_tokens=day * 100,
                rate_limit_primary_used_percent=float(day),
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            )
            for day in range(11, 15)
        ],
        db_path=db_path,
    )

    rows = query_allowance_observations(db_path, limit=2)

    assert [row["event_timestamp"] for row in rows] == [
        "2026-07-13T00:00:00Z",
        "2026-07-14T00:00:00Z",
    ]


def test_limited_history_returns_newest_observations_descending_when_requested(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id=f"rec-{day}",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp=f"2026-07-{day:02d}T00:00:00Z",
                cumulative_total_tokens=day * 100,
                rate_limit_primary_used_percent=float(day),
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            )
            for day in range(11, 15)
        ],
        db_path=db_path,
    )

    rows = query_allowance_observations(db_path, limit=2, newest_first=True)

    assert [row["event_timestamp"] for row in rows] == [
        "2026-07-14T00:00:00Z",
        "2026-07-13T00:00:00Z",
    ]
