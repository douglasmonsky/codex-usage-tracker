"""Additive query-index schema migrations."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.connection import execute_script

MIGRATION_NAMES = {
    18: "index usage events by source file and line",
    22: "cover diagnostic fact lookups",
    23: "cover diagnostic fact aggregation",
    34: "index focused call explorer sorts, sources, and parent lookups",
}


def migrate_source_file_line_index(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    if not {"source_file", "line_number"} <= columns:
        return
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_source_file_line "
        "ON usage_events(source_file, line_number)"
    )


def add_diagnostic_lookup_index(conn: sqlite3.Connection) -> None:
    """Cover correlated diagnostic lookups by type, name, and record."""

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_diagnostic_facts_lookup
        ON call_diagnostic_facts(fact_type, fact_name, record_id)
        """
    )


def add_diagnostic_aggregate_index(conn: sqlite3.Connection) -> None:
    """Cover fact rows consumed by the dashboard diagnostic aggregation."""

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_diagnostic_facts_aggregate
        ON call_diagnostic_facts(
            record_id,
            fact_type,
            fact_name,
            fact_category,
            event_count,
            first_source_line,
            last_source_line,
            raw_content_included
        )
        """
    )


def add_call_explorer_parent_lookup_indexes(conn: sqlite3.Connection) -> None:
    """Cover parent labels resolved for focused call pages."""
    columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    required = {
        "session_id",
        "is_archived",
        "thread_name",
        "session_updated_at",
        "source_file",
    }
    if not required <= columns:
        return
    execute_script(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_usage_parent_thread_lookup
        ON usage_events(session_id, is_archived, thread_name DESC, source_file);

        CREATE INDEX IF NOT EXISTS idx_usage_parent_updated_lookup
        ON usage_events(session_id, is_archived, session_updated_at DESC, source_file);

        CREATE INDEX IF NOT EXISTS idx_usage_cwd_scope
        ON usage_events(cwd, is_duplicate, is_archived, event_timestamp DESC, record_id);
        """,
    )
