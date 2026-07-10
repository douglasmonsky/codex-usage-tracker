"""Persistence and FTS synchronization for the local content index."""

from __future__ import annotations

import sqlite3

CONTENT_INDEX_TABLES = (
    "content_fragments",
    "file_events",
    "command_runs",
    "tool_calls",
    "conversation_turns",
)


def clear_content_index_rows(conn: sqlite3.Connection) -> None:
    """Clear normalized content index rows while tolerating unavailable FTS5."""

    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(f"DELETE FROM {table_name}")  # nosec B608


def delete_content_index_rows_for_source_files(
    conn: sqlite3.Connection,
    *,
    placeholders: str,
    source_files_to_replace: list[str],
    sync_fts: bool = True,
) -> None:
    """Delete normalized content rows linked to source files."""

    record_subquery = f"SELECT record_id FROM usage_events WHERE source_file IN ({placeholders})"  # nosec B608
    if sync_fts:
        _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(
            f"DELETE FROM {table_name} WHERE record_id IN ({record_subquery})",  # nosec B608
            source_files_to_replace,
        )
    if sync_fts:
        _rebuild_content_fts(conn)


def _upsert_turn_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "turn_key",
        "record_id",
        "session_id",
        "turn_id",
        "turn_index",
        "role",
        "event_timestamp",
        "source_record_hash",
        "source_file_id",
        "line_start",
        "line_end",
        "content_hash",
        "content_size_bytes",
        "indexed_content_included",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("conversation_turns", columns, "turn_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_fragment_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "fragment_id",
        "record_id",
        "turn_key",
        "fragment_kind",
        "role",
        "safe_label",
        "content_hash",
        "content_size_bytes",
        "fragment_text",
        "includes_raw_fragment",
        "source_file_id",
        "line_start",
        "line_end",
        "token_link_record_id",
        "created_at",
    )
    conn.executemany(
        _upsert_sql("content_fragments", columns, "fragment_id"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_sql(table_name: str, columns: tuple[str, ...], primary_key: str) -> str:
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column != primary_key
    )
    return (
        f"INSERT INTO {table_name} ({', '.join(columns)}) "  # nosec B608
        f"VALUES ({placeholders}) "
        f"ON CONFLICT({primary_key}) DO UPDATE SET {update_clause}"
    )


def _rebuild_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
        conn.execute(
            """
            INSERT INTO content_fts(rowid, fragment_text, safe_label, fragment_kind)
            SELECT fragment_rowid, fragment_text, safe_label, fragment_kind
            FROM content_fragments
            WHERE fragment_text != ''
            """
        )
    except sqlite3.DatabaseError:
        return


def _sync_content_fts_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    min_line_start: int,
) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO content_fts(rowid, fragment_text, safe_label, fragment_kind)
            SELECT cf.fragment_rowid, cf.fragment_text, cf.safe_label, cf.fragment_kind
            FROM content_fragments cf
            JOIN usage_events u ON u.record_id = cf.record_id
            WHERE u.source_file = ?
              AND cf.line_start >= ?
              AND cf.fragment_text != ''
            """,
            (source_file, min_line_start),
        )
    except sqlite3.DatabaseError:
        return


def _clear_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
    except sqlite3.DatabaseError:
        return


def _content_counts_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_file: str,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM conversation_turns
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS conversation_turns,
            (SELECT COUNT(*)
             FROM content_fragments
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS content_fragments
        """,
        (source_file, source_file),
    ).fetchone()
    if rows is None:
        return {"conversation_turns": 0, "content_fragments": 0}
    return {
        "conversation_turns": int(rows["conversation_turns"] or 0),
        "content_fragments": int(rows["content_fragments"] or 0),
    }
