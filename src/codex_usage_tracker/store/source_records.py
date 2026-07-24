"""Per-record source provenance for aggregate usage events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.source_record_sync import (
    SOURCE_RECORD_COLUMNS as SOURCE_RECORD_COLUMNS,
)
from codex_usage_tracker.store.source_record_sync import (
    content_usage_row_from_event as content_usage_row_from_event,
)
from codex_usage_tracker.store.source_record_sync import (
    sync_source_records as sync_source_records,
)
from codex_usage_tracker.store.source_record_sync import (
    upsert_source_records_from_events as upsert_source_records_from_events,
)


def query_source_records(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    record_id: str | None = None,
    limit: int | None = 1000,
) -> list[dict[str, Any]]:
    """Return source provenance rows with aggregate call context."""

    from codex_usage_tracker.store.schema import init_db

    with connect(db_path) as conn:
        init_db(conn)
        sync_source_records(conn)
        where_clauses: list[str] = []
        params: list[object] = []
        if not include_archived:
            where_clauses.append("u.is_archived = 0")
        if record_id:
            where_clauses.append("sr.record_id = ?")
            params.append(record_id)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit_sql = ""
        if limit is not None and limit > 0:
            limit_sql = "LIMIT ?"
            params.append(limit)
        rows = conn.execute(
            f"""
            SELECT
                sr.*,
                u.source_file,
                u.session_id,
                u.thread_name,
                u.model,
                u.effort,
                u.is_archived,
                u.total_tokens,
                u.cumulative_total_tokens
            FROM source_records AS sr
            JOIN usage_events AS u ON u.record_id = sr.record_id
            {where_sql}
            ORDER BY u.event_timestamp, u.cumulative_total_tokens, sr.line_number, sr.record_id
            {limit_sql}
            """,
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def query_source_record_coverage(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Summarize parser adapter and shape coverage for provenance rows."""

    from codex_usage_tracker.store.schema import init_db

    with connect(db_path) as conn:
        init_db(conn)
        sync_source_records(conn)
        where_sql = "" if include_archived else "WHERE u.is_archived = 0"
        rows = conn.execute(
            f"""
            SELECT
                sr.raw_shape_label,
                sr.parser_adapter,
                sr.parser_version,
                COUNT(*) AS record_count,
                COUNT(DISTINCT sr.source_file_id) AS source_file_count,
                SUM(
                    CASE
                    WHEN sr.parse_warnings_json NOT IN ('', '[]') THEN 1
                    ELSE 0
                    END
                ) AS warning_record_count
            FROM source_records AS sr
            JOIN usage_events AS u ON u.record_id = sr.record_id
            {where_sql}
            GROUP BY sr.raw_shape_label, sr.parser_adapter, sr.parser_version
            ORDER BY record_count DESC, sr.raw_shape_label, sr.parser_adapter
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def query_source_record_totals(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return aggregate parser/source provenance coverage totals."""

    from codex_usage_tracker.store.schema import init_db

    with connect(db_path) as conn:
        init_db(conn)
        sync_source_records(conn)
        where_sql = "" if include_archived else "WHERE u.is_archived = 0"
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS source_record_count,
                COUNT(DISTINCT sr.source_file_id) AS source_file_count,
                COUNT(DISTINCT sr.parser_version) AS parser_version_count,
                SUM(
                    CASE
                    WHEN sr.parse_warnings_json NOT IN ('', '[]') THEN 1
                    ELSE 0
                    END
                ) AS warning_record_count
            FROM source_records AS sr
            JOIN usage_events AS u ON u.record_id = sr.record_id
            {where_sql}
            """
        ).fetchone()
        return row_to_dict(row) if row is not None else {}
