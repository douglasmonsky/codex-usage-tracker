import sqlite3
from contextlib import suppress
from typing import Any

from codex_usage_tracker.store_dashboard_queries import observed_usage_reconciliation
from codex_usage_tracker.store_schema import init_db


class _AutoClosingConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


def _usage_db() -> _AutoClosingConnection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return _AutoClosingConnection(conn)


def _insert_observed_usage_row(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    event_timestamp: str,
    limit_id: str,
    plan_type: str = "pro",
    cumulative_total_tokens: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO usage_events (
            record_id,
            session_id,
            event_timestamp,
            source_file,
            line_number,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            reasoning_output_tokens,
            total_tokens,
            cumulative_input_tokens,
            cumulative_cached_input_tokens,
            cumulative_output_tokens,
            cumulative_reasoning_output_tokens,
            cumulative_total_tokens,
            uncached_input_tokens,
            cache_ratio,
            reasoning_output_ratio,
            context_window_percent,
            rate_limit_plan_type,
            rate_limit_limit_id
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, 0, 0.0, 0.0, 0.0, ?, ?)
        """,
        (
            record_id,
            f"session-{record_id}",
            event_timestamp,
            "/tmp/session.jsonl",
            1,
            cumulative_total_tokens,
            plan_type,
            limit_id,
        ),
    )


def _selected_row(conn: sqlite3.Connection, record_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM usage_events WHERE record_id = ?",
        (record_id,),
    ).fetchone()
    assert row is not None
    return row


def test_observed_usage_reconciliation_recommends_live_check_for_alternate_streak() -> None:
    conn = _usage_db()
    _insert_observed_usage_row(
        conn,
        record_id="selected-codex",
        event_timestamp="2026-06-01T10:00:00Z",
        limit_id="codex",
    )
    for index in range(3):
        _insert_observed_usage_row(
            conn,
            record_id=f"alternate-{index}",
            event_timestamp=f"2026-06-01T10:0{index + 1}:00Z",
            limit_id="codex_spark",
            cumulative_total_tokens=index,
        )

    result = observed_usage_reconciliation(
        conn,
        scoped_where="",
        params=[],
        selected_row=_selected_row(conn, "selected-codex"),
    )

    assert result["recommended"] is True
    assert result["reason"] == "latest_alternate_codex_limit_rows"
    assert result["suggested_action"] == "live_usage_check"
    assert result["consecutive_alternate_rows"] == 3
    assert result["latest_limit_id"] == "codex_spark"
    assert result["latest_observed_at"] == "2026-06-01T10:03:00Z"
    assert result["selected_limit_id"] == "codex"


def test_observed_usage_reconciliation_ignores_short_or_interrupted_alternate_streak() -> None:
    conn = _usage_db()
    _insert_observed_usage_row(
        conn,
        record_id="selected-codex",
        event_timestamp="2026-06-01T10:00:00Z",
        limit_id="codex",
    )
    _insert_observed_usage_row(
        conn,
        record_id="latest-alternate",
        event_timestamp="2026-06-01T10:02:00Z",
        limit_id="codex_spark",
    )
    _insert_observed_usage_row(
        conn,
        record_id="latest-codex",
        event_timestamp="2026-06-01T10:03:00Z",
        limit_id="codex",
    )

    result = observed_usage_reconciliation(
        conn,
        scoped_where="",
        params=[],
        selected_row=_selected_row(conn, "selected-codex"),
    )

    assert result["recommended"] is False
    assert result["reason"] is None
    assert result["suggested_action"] is None
    assert result["consecutive_alternate_rows"] == 0
    assert result["latest_limit_id"] is None


def test_observed_usage_reconciliation_ignores_selected_latest_alternate() -> None:
    conn = _usage_db()
    for index in range(3):
        _insert_observed_usage_row(
            conn,
            record_id=f"alternate-{index}",
            event_timestamp=f"2026-06-01T10:0{index + 1}:00Z",
            limit_id="codex_spark",
            cumulative_total_tokens=index,
        )

    result = observed_usage_reconciliation(
        conn,
        scoped_where="",
        params=[],
        selected_row=_selected_row(conn, "alternate-2"),
    )

    assert result["recommended"] is False
    assert result["consecutive_alternate_rows"] == 3
    assert result["latest_limit_id"] == "codex_spark"
    assert result["selected_limit_id"] == "codex_spark"
