"""Bounded reads over persisted detector-ready compression facts."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.store.compression_evidence import (
    _content_index_enabled,
    _is_unfiltered_all_history,
    _populate_scope_records,
    _scoped_sql,
)
from codex_usage_tracker.store.compression_fact_contract import (
    COMPRESSION_FACTS_VERSION,
    RELEVANT_COMMAND_ROOTS,
)
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

FactConsumer = Callable[[str, list[sqlite3.Row]], None]

_TARGET_SCOPES = {
    "__TARGET_RECORD__": (
        "WHERE record_id IN (SELECT record_id FROM compression_fact_targets)",
        "",
    ),
    "__TARGET_U_RECORD__": (
        "WHERE u.record_id IN (SELECT record_id FROM compression_fact_targets)",
        "",
    ),
    "__TARGET_T_RECORD_AND__": (
        "WHERE t.record_id IN (SELECT record_id FROM compression_fact_targets) AND",
        "WHERE",
    ),
    "__TARGET_C_RECORD_AND__": (
        "WHERE c.record_id IN (SELECT record_id FROM compression_fact_targets) AND",
        "WHERE",
    ),
    "__TARGET_F_RECORD_AND__": (
        "WHERE f.record_id IN (SELECT record_id FROM compression_fact_targets) AND",
        "WHERE",
    ),
    "__TARGET_R_THREAD__": (
        "WHERE r.thread_key IN (SELECT thread_key FROM compression_fact_thread_targets)",
        "",
    ),
}


def target_mode_sql(query: str, *, targeted: bool) -> str:
    """Resolve fixed internal scope markers without accepting SQL identifiers."""
    replacement_index = 0 if targeted else 1
    for marker, replacements in _TARGET_SCOPES.items():
        query = query.replace(marker, replacements[replacement_index])
    return query


def fold_compression_detector_facts(
    db_path: Path,
    *,
    scope: Mapping[str, Any],
    batch_size: int,
    consumer: FactConsumer,
) -> dict[str, Any]:
    """Fold ready facts into a caller-owned accumulator without raw event scans."""
    with connect(db_path) as conn:
        init_db(conn)
        scoped = not _is_unfiltered_all_history(scope)
        if scoped:
            _populate_scope_records(conn, scope)
        metadata = _fact_metadata(conn, scoped=scoped)
        if not metadata["ready"]:
            return metadata
        _fold_query(
            conn,
            _scoped_sql(_RECORD_FACTS_SQL, "r", scoped=scoped),
            category="records",
            batch_size=batch_size,
            consumer=consumer,
        )
        _fold_query(
            conn,
            _scoped_sql(_SEQUENCE_FACTS_SQL, "s", scoped=scoped),
            category="sequences",
            batch_size=batch_size,
            consumer=consumer,
        )
        return metadata


def _fold_query(
    conn: sqlite3.Connection,
    sql: str,
    *,
    category: str,
    batch_size: int,
    consumer: FactConsumer,
) -> None:
    cursor = conn.execute(sql, (COMPRESSION_FACTS_VERSION,))
    while rows := cursor.fetchmany(batch_size):
        consumer(category, rows)


def _fact_metadata(conn: sqlite3.Connection, *, scoped: bool) -> dict[str, Any]:
    expected_count = conn.execute(
        "SELECT COUNT(*) FROM compression_scope_records"
        if scoped
        else "SELECT COUNT(*) FROM usage_events"
    ).fetchone()[0]
    row = conn.execute(
        _scoped_sql(_COVERAGE_SQL, "r", scoped=scoped),
        (COMPRESSION_FACTS_VERSION,),
    ).fetchone()
    state = conn.execute(
        """
        SELECT facts_version, source_generation,
               record_count, sequence_count, thread_count
        FROM compression_fact_state WHERE singleton = 1
        """
    ).fetchone()
    integrity = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM compression_record_facts WHERE facts_version = ?)
                AS record_count,
            (SELECT COUNT(*) FROM compression_sequence_facts WHERE facts_version = ?)
                AS sequence_count,
            (SELECT COUNT(*) FROM compression_thread_facts WHERE facts_version = ?)
                AS thread_count
        """,
        (COMPRESSION_FACTS_VERSION,) * 3,
    ).fetchone()
    generation = read_compression_source_generation(conn)
    fact_count = int(row["call_count"] or 0) if row is not None else 0
    integrity_counts = (
        tuple(int(integrity[key]) for key in ("record_count", "sequence_count", "thread_count"))
        if integrity is not None
        else (-1, -1, -1)
    )
    state_signature = (
        (
            int(state["facts_version"]),
            int(state["source_generation"]),
            int(state["record_count"]),
            int(state["sequence_count"]),
            int(state["thread_count"]),
        )
        if state is not None
        else None
    )
    ready = bool(
        fact_count == int(expected_count)
        and state_signature == (COMPRESSION_FACTS_VERSION, generation, *integrity_counts)
    )
    coverage = dict(row) if row is not None else {}
    coverage.update(
        {
            "parser_adapters": _csv_values(coverage.get("parser_adapters")),
            "parser_versions": _csv_values(coverage.get("parser_versions")),
            "content_index_enabled": _content_index_enabled(conn),
        }
    )
    return {
        "ready": ready,
        "source_generation": generation,
        "coverage": coverage,
    }


def _csv_values(value: object) -> list[str]:
    if not value:
        return []
    return sorted(part for part in str(value).split(",") if part)


_RECORD_FACTS_SQL = """
SELECT
    r.record_id,
    r.session_id,
    r.thread_key,
    r.event_timestamp,
    r.model,
    r.effort,
    r.is_archived,
    r.thread_call_index,
    r.previous_record_id,
    r.cached_input_tokens,
    r.uncached_input_tokens,
    r.output_tokens,
    r.reasoning_output_tokens,
    r.cache_ratio,
    r.context_window_percent,
    r.content_exposure_tokens,
    r.tool_output_exposure_tokens,
    r.manifest_count,
    r.manifest_sum_hex,
    r.manifest_xor_hex
FROM compression_record_facts AS r
{scope_join}
WHERE r.facts_version = ?
ORDER BY r.event_timestamp, r.record_id
"""

_SEQUENCE_FACTS_SQL = """
SELECT
    s.fact_key,
    s.record_id,
    s.thread_key,
    s.turn_key,
    s.fact_kind,
    s.category,
    s.status,
    s.duration_ms,
    s.output_size_bytes,
    s.command_label,
    s.exit_code,
    s.retry_group,
    s.path_identity,
    s.exposure_tokens
FROM compression_sequence_facts AS s
{scope_join}
WHERE s.facts_version = ?
ORDER BY
    CASE s.fact_kind
        WHEN 'tool_output' THEN 0
        WHEN 'command' THEN 1
        WHEN 'file_read' THEN 2
        ELSE 3
    END,
    s.source_order
"""

_COVERAGE_SQL = """
SELECT
    COUNT(*) AS call_count,
    SUM(r.turn_count) AS turn_count,
    SUM(r.tool_call_count) AS tool_call_count,
    SUM(r.command_run_count) AS command_run_count,
    SUM(r.file_event_count) AS file_event_count,
    SUM(r.content_fragment_count) AS content_fragment_count,
    SUM(r.compaction_count) AS compaction_count,
    SUM(r.indexed_call) AS indexed_call_count,
    SUM(r.source_record_count) AS source_record_count,
    SUM(r.parser_warning_record_count) AS parser_warning_record_count,
    GROUP_CONCAT(DISTINCT r.parser_adapter) AS parser_adapters,
    GROUP_CONCAT(DISTINCT r.parser_version) AS parser_versions
FROM compression_record_facts AS r
{scope_join}
WHERE r.facts_version = ?
"""


def ensure_empty_target_tables(conn: sqlite3.Connection) -> None:
    """Create the temp tables referenced by static full-backfill queries."""
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_fact_targets (
            record_id TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_fact_thread_targets (
            thread_key TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM compression_fact_targets")
    conn.execute("DELETE FROM compression_fact_thread_targets")


def populate_relevant_command_roots(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_relevant_command_roots (
            command_root TEXT PRIMARY KEY
        ) WITHOUT ROWID
        """
    )
    conn.execute("DELETE FROM compression_relevant_command_roots")
    conn.executemany(
        "INSERT INTO compression_relevant_command_roots(command_root) VALUES (?)",
        ((root,) for root in sorted(RELEVANT_COMMAND_ROOTS)),
    )
