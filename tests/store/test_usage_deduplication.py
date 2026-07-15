from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.api import connect, upsert_usage_events
from codex_usage_tracker.store.dashboard_queries import (
    query_dashboard_event_count,
    query_dashboard_events,
    query_dashboard_token_summary,
)
from codex_usage_tracker.store.summary_queries import query_summary
from codex_usage_tracker.store.usage_api_queries import (
    query_usage_api_event_count,
    query_usage_api_events,
)
from codex_usage_tracker.store.usage_record_queries import query_most_expensive_calls


def test_clone_copy_is_physical_but_not_billable(tmp_path: Path) -> None:
    original = _event("original", "/original.jsonl")
    copied = replace(original, record_id="clone", session_id="clone", source_file="/clone.jsonl")
    new = replace(copied, record_id="new", event_timestamp="2026-07-14T12:01:00Z")
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


def test_source_replacement_promotes_surviving_copy(tmp_path: Path) -> None:
    original = _event("original", "/original.jsonl")
    copied = replace(original, record_id="copy", session_id="copy", source_file="/copy.jsonl")
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original, copied], db_path)
    upsert_usage_events([], db_path, replace_source_files=[Path("/original.jsonl")])
    with connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0] == 1
        row = conn.execute("SELECT is_duplicate, duplicate_reason FROM usage_events").fetchone()
    assert tuple(row) == (0, None)


def test_default_usage_surfaces_exclude_copied_clone_rows(tmp_path: Path) -> None:
    original = replace(
        _event("original", "/original.jsonl"),
        rate_limit_primary_used_percent=10.0,
        rate_limit_primary_window_minutes=300,
    )
    copied = replace(original, record_id="clone", session_id="clone", source_file="/clone.jsonl")
    new = replace(
        copied,
        record_id="new",
        event_timestamp="2026-07-14T12:01:00Z",
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
        active_threads = conn.execute(
            """
            SELECT SUM(call_count), SUM(total_tokens)
            FROM thread_summaries
            WHERE is_archived_scope = 'active'
            """
        ).fetchone()
        allowance_rows = conn.execute(
            "SELECT COUNT(*) FROM allowance_observations"
        ).fetchone()[0]
    assert tuple(active_threads) == (2, 225)
    assert allowance_rows == 2


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
