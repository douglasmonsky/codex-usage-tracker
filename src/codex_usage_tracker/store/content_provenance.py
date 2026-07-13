"""Usage-record provenance lookups for local content indexing."""

from __future__ import annotations

import sqlite3


def _usage_rows_by_token_line(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    min_line_number: int | None = None,
) -> dict[int, sqlite3.Row]:
    line_filter = "" if min_line_number is None else "AND u.line_number >= ?"
    params: list[object] = [source_file]
    if min_line_number is not None:
        params.append(min_line_number)
    query = f"""
        SELECT
            u.record_id,
            u.session_id,
            u.turn_id,
            u.event_timestamp,
            u.source_file,
            u.line_number,
            sr.source_file_id,
            sr.source_record_hash,
            sr.parser_adapter,
            sr.parser_version
        FROM usage_events AS u
        JOIN source_records AS sr ON sr.record_id = u.record_id
        WHERE u.source_file = ?
          {line_filter}
        ORDER BY u.line_number
        """  # nosec B608 - optional clause is fixed and values stay bound
    rows = conn.execute(
        query,
        params,
    ).fetchall()
    return {int(row["line_number"]): row for row in rows}
