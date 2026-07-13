"""Incrementally maintain detector facts inside aggregate write transactions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from codex_usage_tracker.store.compression_fact_contract import COMPRESSION_FACTS_VERSION
from codex_usage_tracker.store.compression_facts import (
    _insert_record_facts,
    _insert_sequence_facts,
    _insert_thread_facts,
    _update_record_manifests,
    _update_thread_manifests,
)
from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.compression_schema import (
    stamp_compression_fact_state,
)
from codex_usage_tracker.store.content_index_models import ContentIndexPlan
from codex_usage_tracker.store.sources import SourceParsePlan


def content_index_plans(
    plans: Iterable[SourceParsePlan],
) -> tuple[ContentIndexPlan, ...]:
    """Materialize content plans for indexing followed by fact synchronization."""
    return tuple(
        ContentIndexPlan(
            source_path=plan.path,
            replace_existing=plan.replace_existing,
            start_byte=plan.start_byte,
            start_line=plan.start_line,
        )
        for plan in plans
    )


def sync_compression_detector_facts(
    conn: sqlite3.Connection,
    *,
    record_ids: Iterable[str],
    affected_thread_keys: Iterable[str],
) -> None:
    """Refresh only changed records and their surviving thread summaries."""
    targets = {str(record_id) for record_id in record_ids if str(record_id)}
    threads = {str(thread_key) for thread_key in affected_thread_keys if str(thread_key)}
    _populate_record_targets(conn, targets)
    threads.update(_target_thread_keys(conn, table="compression_record_facts"))
    threads.update(_target_thread_keys(conn, table="usage_events"))

    if targets:
        conn.execute(
            """
            DELETE FROM compression_sequence_facts
            WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
            """
        )
        conn.execute(
            """
            DELETE FROM compression_record_facts
            WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
            """
        )
        _insert_record_facts(conn, targeted=True)
        _update_record_manifests(conn, targeted=True)
        _insert_sequence_facts(conn, targeted=True)

    _populate_thread_targets(conn, threads)
    if threads:
        conn.execute(
            """
            DELETE FROM compression_thread_facts
            WHERE thread_key IN (
                SELECT thread_key FROM compression_fact_thread_targets
            )
            """
        )
        _insert_thread_facts(conn, targeted=True)
        _update_thread_manifests(conn, targeted=True)
    stamp_compression_fact_state(conn, facts_version=COMPRESSION_FACTS_VERSION)


def sync_content_plan_compression_facts(
    conn: sqlite3.Connection,
    *,
    plans: Iterable[ContentIndexPlan],
) -> None:
    """Refresh fact rows whose normalized content changed in this refresh."""
    content_plans = tuple(plans)
    if not content_plans:
        return
    touch_compression_revisions(conn, {"commands", "files", "fragments", "tools"})
    record_ids: set[str] = set()
    for plan in content_plans:
        minimum_line = 0 if plan.replace_existing else plan.start_line + 1
        rows = conn.execute(
            """
            SELECT record_id FROM usage_events
            WHERE source_file = ? AND line_number >= ?
            """,
            (str(plan.source_path), minimum_line),
        )
        record_ids.update(str(row["record_id"]) for row in rows if row["record_id"])
    sync_compression_detector_facts(
        conn,
        record_ids=record_ids,
        affected_thread_keys=(),
    )


def delete_compression_facts_for_source_files(
    conn: sqlite3.Connection,
    *,
    source_files: Iterable[str],
) -> None:
    """Delete record and sequence facts before their usage rows are replaced."""
    paths = tuple(dict.fromkeys(str(path) for path in source_files if str(path)))
    if not paths:
        return
    _populate_source_file_targets(conn, paths)
    record_ids = {
        str(row["record_id"])
        for row in conn.execute(
            """
            SELECT record_id FROM usage_events
            WHERE source_file IN (
                SELECT source_file FROM compression_fact_source_targets
            )
            """
        )
    }
    _populate_record_targets(conn, record_ids)
    conn.execute(
        """
        DELETE FROM compression_sequence_facts
        WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
        """
    )
    conn.execute(
        """
        DELETE FROM compression_record_facts
        WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
        """
    )


def clear_compression_detector_facts(conn: sqlite3.Connection) -> None:
    """Clear all detector-ready facts and their integrity stamp."""
    conn.execute("DELETE FROM compression_sequence_facts")
    conn.execute("DELETE FROM compression_thread_facts")
    conn.execute("DELETE FROM compression_record_facts")
    conn.execute("DELETE FROM compression_fact_state")


def _populate_record_targets(conn: sqlite3.Connection, record_ids: set[str]) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_fact_targets (
            record_id TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM compression_fact_targets")
    conn.executemany(
        "INSERT INTO compression_fact_targets(record_id) VALUES (?)",
        ((record_id,) for record_id in sorted(record_ids)),
    )


def _target_thread_keys(conn: sqlite3.Connection, *, table: str) -> set[str]:
    if table == "compression_record_facts":
        rows = conn.execute(
            """
            SELECT DISTINCT thread_key
            FROM compression_record_facts
            WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
            """
        )
    elif table == "usage_events":
        rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(thread_key, thread_name, session_id) AS thread_key
            FROM usage_events
            WHERE record_id IN (SELECT record_id FROM compression_fact_targets)
            """
        )
    else:
        raise ValueError(f"unsupported fact thread table: {table}")
    return {str(row["thread_key"]) for row in rows if row["thread_key"]}


def _populate_source_file_targets(
    conn: sqlite3.Connection,
    source_files: tuple[str, ...],
) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_fact_source_targets (
            source_file TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM compression_fact_source_targets")
    conn.executemany(
        "INSERT INTO compression_fact_source_targets(source_file) VALUES (?)",
        ((source_file,) for source_file in source_files),
    )


def _populate_thread_targets(conn: sqlite3.Connection, thread_keys: set[str]) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_fact_thread_targets (
            thread_key TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM compression_fact_thread_targets")
    conn.executemany(
        "INSERT INTO compression_fact_thread_targets(thread_key) VALUES (?)",
        ((thread_key,) for thread_key in sorted(thread_keys)),
    )
