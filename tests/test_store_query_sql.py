from __future__ import annotations

from codex_usage_tracker.store_query_sql import _usage_where_clause


def test_usage_where_clause_builds_filters_in_stable_order() -> None:
    where, params = _usage_where_clause(
        since="2026-06-01T00:00:00Z",
        until="2026-06-02T00:00:00Z",
        model="gpt-test",
        effort="high",
        thread="Thread A",
        min_tokens=100,
        table_alias="usage_events",
    )

    assert where == (
        "WHERE usage_events.event_timestamp >= ? "
        "AND usage_events.event_timestamp <= ? "
        "AND usage_events.model = ? "
        "AND usage_events.effort = ? "
        "AND (usage_events.thread_name = ? "
        "OR usage_events.parent_thread_name = ? "
        "OR usage_events.session_id = ?) "
        "AND usage_events.total_tokens >= ?"
    )
    assert params == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
        "gpt-test",
        "high",
        "Thread A",
        "Thread A",
        "Thread A",
        100,
    ]


def test_usage_where_clause_excludes_archived_sources_when_requested() -> None:
    where, params = _usage_where_clause(include_archived=False)

    assert where == (
        "WHERE (coalesce(is_archived, 0) = 0 "
        "AND NOT (source_file LIKE ? OR source_file LIKE ? "
        "OR source_file LIKE ? OR source_file LIKE ?))"
    )
    assert params == [
        "%/archived_sessions/%",
        "archived_sessions/%",
        "%\\archived_sessions\\%",
        "archived_sessions\\%",
    ]


def test_usage_where_clause_returns_empty_filter_without_constraints() -> None:
    assert _usage_where_clause() == ("", [])
