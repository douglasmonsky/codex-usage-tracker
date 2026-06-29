"""Usage record detail read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import usage_where_clause
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
)


def query_session_usage(
    db_path: Path = DEFAULT_DB_PATH,
    session_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return aggregate usage rows for one session."""

    with connect(db_path) as conn:
        init_db(conn)
        if session_id is None:
            row = conn.execute(
                """
                SELECT session_id
                FROM usage_events
                GROUP BY session_id
                ORDER BY MAX(event_timestamp) DESC
                LIMIT 1
                """,
            ).fetchone()
            if row is None:
                return []
            session_id = str(row["session_id"])
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                {USAGE_TIMING_SELECT_SQL}
            FROM usage_events
            {USAGE_TIMING_JOIN_SQL}
            WHERE usage_events.session_id = ?
            ORDER BY usage_events.event_timestamp, usage_events.cumulative_total_tokens
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [usage_row_to_dict(row) for row in rows]


def query_usage_record(
    db_path: Path = DEFAULT_DB_PATH,
    record_id: str | None = None,
) -> dict[str, Any] | None:
    """Return one aggregate usage row by stable record id."""

    if not record_id:
        return None
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT
                usage_events.*,
                {USAGE_TIMING_SELECT_SQL}
            FROM usage_events
            {USAGE_TIMING_JOIN_SQL}
            WHERE usage_events.record_id = ?
            LIMIT 1
            """,
            (record_id,),
        ).fetchone()
    return usage_row_to_dict(row) if row is not None else None


def query_most_expensive_calls(
    db_path: Path = DEFAULT_DB_PATH,
    limit: int = 20,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Return calls with largest last-call token count."""

    where_clause, params = usage_where_clause(since=since, table_alias="usage_events")
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                {USAGE_TIMING_SELECT_SQL}
            FROM usage_events
            {USAGE_TIMING_JOIN_SQL}
            {where_clause}
            ORDER BY usage_events.total_tokens DESC, usage_events.event_timestamp DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [usage_row_to_dict(row) for row in rows]
