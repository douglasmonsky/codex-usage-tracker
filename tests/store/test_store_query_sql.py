from __future__ import annotations

from codex_usage_tracker.store.query_sql import _usage_where_clause


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
        "AND (usage_events.thread_key = ? "
        "OR usage_events.thread_name = ? "
        "OR usage_events.parent_thread_name = ? "
        "OR usage_events.session_id = ? "
        "OR 'session:' || usage_events.session_id = ?) "
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
        "Thread A",
        "Thread A",
        100,
    ]


def test_usage_where_clause_excludes_archived_sources_when_requested() -> None:
    where, params = _usage_where_clause(include_archived=False)

    assert where == (
        "WHERE (is_archived = 0 "
        "AND NOT (source_file LIKE ? OR source_file LIKE ? "
        "OR source_file LIKE ? OR source_file LIKE ?))"
    )
    assert params == [
        "%/archived_sessions/%",
        "archived_sessions/%",
        "%\\archived_sessions\\%",
        "archived_sessions\\%",
    ]


def test_usage_where_clause_can_trust_the_materialized_archive_flag() -> None:
    where, params = _usage_where_clause(
        include_archived=False,
        legacy_archive_path_fallback=False,
    )

    assert where == "WHERE is_archived = 0"
    assert params == []


def test_usage_where_clause_filters_source_metadata() -> None:
    project_where, project_params = _usage_where_clause(
        source="project",
        table_alias="usage_events",
    )
    missing_where, missing_params = _usage_where_clause(source="missing")

    assert project_where == "WHERE nullif(usage_events.cwd, '') IS NOT NULL"
    assert project_params == []
    assert "NOT (nullif(cwd, '') IS NOT NULL" in missing_where
    assert "nullif(source_file, '') IS NOT NULL" in missing_where
    assert missing_params == []


def test_usage_where_clause_filters_bounded_cwd_groups() -> None:
    cwds = [f"/repo/{index}" for index in range(501)]
    where, params = _usage_where_clause(cwds=cwds, table_alias="usage_events")

    assert where.count("usage_events.cwd IN") == 2
    assert " OR " in where
    assert params == cwds

    empty_where, empty_params = _usage_where_clause(cwds=[])
    assert empty_where == "WHERE 0"
    assert empty_params == []


def test_usage_where_clause_returns_empty_filter_without_constraints() -> None:
    assert _usage_where_clause() == ("", [])
