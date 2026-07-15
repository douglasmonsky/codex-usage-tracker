from __future__ import annotations

import sqlite3

import pytest

from codex_usage_tracker.store.allowance_intelligence import (
    AllowanceCursorError,
    query_allowance_evidence,
    query_allowance_series,
    query_latest_allowance_state,
)
from codex_usage_tracker.store.schema import init_db


def test_latest_and_series_are_archive_aware_and_scoped() -> None:
    conn = seeded_connection()

    latest = query_latest_allowance_state(conn, window_kind="weekly", cohort_id="team-a")
    assert latest is not None
    assert latest["cycle_id"] == "active-new"
    assert query_latest_allowance_state(
        conn, window_kind="weekly", cohort_id="team-a", include_archived=True
    )["cycle_id"] == "archived-new"

    rows = query_allowance_series(
        conn,
        start_at="2026-01-01T00:00:00Z",
        end_at="2026-01-31T23:59:59Z",
        window_kind="weekly",
        cohort_id="team-a",
    )
    assert [row["cycle_id"] for row in rows] == ["active-old", "active-new"]
    assert all(row["cohort_key"] == "team-a" and row["is_archived"] == 0 for row in rows)

    with pytest.raises(ValueError, match="start_at and end_at"):
        query_allowance_series(
            conn, start_at=None, end_at="2026-01-31T23:59:59Z", window_kind="weekly"
        )


def test_evidence_filters_orders_clamps_and_continues_without_overlap() -> None:
    conn = seeded_connection()

    newest = query_allowance_evidence(
        conn,
        limit=0,
        window_kind="weekly",
        cohort_id="team-a",
        start_at="2026-01-01T00:00:00Z",
        end_at="2026-01-31T23:59:59Z",
    )
    assert len(newest.rows) == 1
    assert newest.rows[0]["interval_id"] == "active-evidence-3"

    first = query_allowance_evidence(conn, limit=2, window_kind="weekly", cohort_id="team-a")
    second = query_allowance_evidence(
        conn, limit=2, window_kind="weekly", cohort_id="team-a", cursor=first.next_cursor
    )
    assert [row["interval_id"] for row in first.rows + second.rows] == [
        "active-evidence-3", "active-evidence-2", "active-evidence-1"
    ]
    assert second.next_cursor is None

    oldest = query_allowance_evidence(
        conn, limit=5000, window_kind="weekly", cohort_id="team-a", order="asc"
    )
    assert [row["interval_id"] for row in oldest.rows] == [
        "active-evidence-1", "active-evidence-2", "active-evidence-3"
    ]
    assert "untimed-evidence" not in {
        row["interval_id"]
        for row in query_allowance_evidence(
            conn, limit=500, window_kind="weekly", cohort_id="team-a", include_archived=True
        ).rows
    }


def test_all_history_evidence_merges_archive_partitions_without_cursor_gap() -> None:
    conn = seeded_connection()

    first = query_allowance_evidence(
        conn, limit=2, window_kind="weekly", cohort_id="team-a", include_archived=True
    )
    second = query_allowance_evidence(
        conn,
        limit=2,
        window_kind="weekly",
        cohort_id="team-a",
        include_archived=True,
        cursor=first.next_cursor,
    )
    assert [row["interval_id"] for row in first.rows + second.rows] == [
        "archived-evidence",
        "active-evidence-3",
        "active-evidence-2",
        "active-evidence-1",
    ]
    assert second.next_cursor is None


def test_evidence_cursor_rejects_malformed_and_stale_revisions() -> None:
    conn = seeded_connection()
    with pytest.raises(AllowanceCursorError, match="malformed_cursor"):
        query_allowance_evidence(conn, cursor="not a cursor")

    page = query_allowance_evidence(conn, limit=1, window_kind="weekly", cohort_id="team-a")
    conn.execute(
        "UPDATE allowance_source_state SET source_revision = 'revision-2' WHERE state_id = 1"
    )
    with pytest.raises(AllowanceCursorError, match="source_revision_mismatch"):
        query_allowance_evidence(conn, cursor=page.next_cursor)

    malformed_stale = "eyJzb3VyY2VfcmV2aXNpb24iOjEsIm9ic2VydmVkX2F0IjoxLCJyb3dfaWQiOjEsIm9yZGVyIjoiYmFkIiwic2NvcGUiOltdfQ"
    with pytest.raises(AllowanceCursorError, match="malformed_cursor"):
        query_allowance_evidence(conn, cursor=malformed_stale)


@pytest.mark.parametrize("cohort_id", ["team-a", None])
@pytest.mark.parametrize("is_archived", [0, 1])
def test_common_query_plans_use_allowance_indexes_without_temp_ordering(
    cohort_id: str | None, is_archived: int
) -> None:
    conn = seeded_connection()
    cohort_sql = " AND cohort_key = ?" if cohort_id is not None else ""
    cohort_params = [cohort_id] if cohort_id is not None else []
    latest = [
        row["detail"]
        for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM allowance_cycles "
            "WHERE is_archived = ? AND source_revision = ? AND window_kind = ?"
            f"{cohort_sql} "
            "ORDER BY last_observed_at DESC, cycle_id DESC LIMIT 1",
            [is_archived, "revision-1", "weekly", *cohort_params],
        )
    ]
    series = [
        row["detail"]
        for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM allowance_cycles "
            "WHERE is_archived = ? AND source_revision = ? AND window_kind = ?"
            f"{cohort_sql} AND first_observed_at >= ? "
            "ORDER BY first_observed_at ASC, cycle_id ASC",
            [is_archived, "revision-1", "weekly", *cohort_params, "2026-01-01T00:00:00Z"],
        )
    ]
    evidence = [
        row["detail"]
        for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM allowance_intervals "
            "WHERE is_archived = ? AND source_revision = ? AND window_kind = ?"
            f"{cohort_sql} AND end_observed_at IS NOT NULL "
            "ORDER BY end_observed_at DESC, interval_id DESC LIMIT 2",
            [is_archived, "revision-1", "weekly", *cohort_params],
        )
    ]
    latest_index = "idx_allowance_cycles_latest_cohort_window" if cohort_id else "idx_allowance_cycles_latest_window"
    series_index = "idx_allowance_cycles_series_cohort_window" if cohort_id else "idx_allowance_cycles_series_window"
    evidence_index = "idx_allowance_intervals_evidence_cohort_window" if cohort_id else "idx_allowance_intervals_evidence_window"
    assert any(latest_index in detail for detail in latest)
    assert any(series_index in detail for detail in series)
    assert any(evidence_index in detail for detail in evidence)
    assert not any("USE TEMP B-TREE" in detail for detail in latest + series + evidence)


def seeded_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO allowance_source_state VALUES "
        "(1, 1, 'revision-1', 1, '2026-01-30T00:00:00Z', 'v26', '2026-01-30T00:00:00Z')"
    )
    for cycle_id, cohort, archived, first, last in (
        ("active-old", "team-a", 0, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        ("active-new", "team-a", 0, "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"),
        ("archived-new", "team-a", 1, "2026-01-05T00:00:00Z", "2026-01-06T00:00:00Z"),
        ("other-cohort", "team-b", 0, "2026-01-07T00:00:00Z", "2026-01-08T00:00:00Z"),
    ):
        conn.execute(
            "INSERT INTO allowance_cycles "
            "(cycle_id, window_kind, window_key, cohort_key, is_archived, first_observed_at, "
            "last_observed_at, source_revision) "
            "VALUES (?, 'weekly', 'primary', ?, ?, ?, ?, 'revision-1')",
            (cycle_id, cohort, archived, first, last),
        )
    for interval_id, end_at in (
        ("active-evidence-1", "2026-01-10T00:00:00Z"),
        ("active-evidence-2", "2026-01-11T00:00:00Z"),
        ("active-evidence-3", "2026-01-12T00:00:00Z"),
    ):
        conn.execute(
            "INSERT INTO allowance_intervals "
            "(interval_id, cycle_id, window_kind, window_key, cohort_key, is_archived, "
            "end_observed_at, point_kind, source_revision) "
            "VALUES (?, 'active-new', 'weekly', 'primary', 'team-a', 0, ?, 'observed', "
            "'revision-1')",
            (interval_id, end_at),
        )
    conn.execute(
        "INSERT INTO allowance_intervals "
        "(interval_id, cycle_id, window_kind, window_key, cohort_key, is_archived, "
        "end_observed_at, point_kind, source_revision) "
        "VALUES ('archived-evidence', 'archived-new', 'weekly', 'primary', 'team-a', 1, "
        "'2026-01-13T00:00:00Z', 'observed', 'revision-1')"
    )
    conn.execute(
        "INSERT INTO allowance_intervals "
        "(interval_id, cycle_id, window_kind, window_key, cohort_key, is_archived, "
        "point_kind, source_revision) "
        "VALUES ('untimed-evidence', 'active-new', 'weekly', 'primary', 'team-a', 0, "
        "'observed', 'revision-1')"
    )
    return conn
