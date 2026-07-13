"""Scoped normalized evidence reads for Compression Lab analyses."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def query_compression_evidence(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scope: Mapping[str, Any],
    include_turns: bool = True,
) -> dict[str, Any]:
    """Load one deduplicated evidence snapshot for a normalized scope."""
    payload = query_compression_evidence_rows(
        db_path,
        scope=scope,
        include_turns=include_turns,
    )
    return {
        **payload,
        "calls": _rows(payload["calls"]),
        "turns": _rows(payload["turns"]),
        "tool_calls": _rows(payload["tool_calls"]),
        "command_runs": _rows(payload["command_runs"]),
        "file_events": _rows(payload["file_events"]),
        "content_fragments": _rows(payload["content_fragments"]),
        "compactions": _rows(payload["compactions"]),
    }


def query_compression_evidence_rows(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scope: Mapping[str, Any],
    include_turns: bool = True,
) -> dict[str, Any]:
    """Load SQLite rows for direct domain-object materialization."""
    with connect(db_path) as conn:
        init_db(conn)
        scoped = not _is_unfiltered_all_history(scope)
        if scoped:
            _populate_scope_records(conn, scope)
        calls = _raw_rows(conn, _scoped_sql(_CALLS_SQL, "u", scoped=scoped))
        turns = (
            _raw_rows(conn, _scoped_sql(_TURNS_SQL, "t", scoped=scoped)) if include_turns else []
        )
        tool_calls = _raw_rows(conn, _scoped_sql(_TOOL_CALLS_SQL, "t", scoped=scoped))
        command_runs = _raw_rows(conn, _scoped_sql(_COMMAND_RUNS_SQL, "c", scoped=scoped))
        file_events = _raw_rows(conn, _scoped_sql(_FILE_EVENTS_SQL, "f", scoped=scoped))
        fragments = _raw_rows(conn, _scoped_sql(_FRAGMENTS_SQL, "f", scoped=scoped))
        source_coverage = _source_coverage(conn, scoped=scoped)
        content_index_enabled = _content_index_enabled(conn)
        turn_coverage = None if include_turns else _turn_coverage(conn, scoped=scoped)
        source_generation = read_compression_source_generation(conn)
    compactions = [
        row for row in fragments if row["fragment_kind"] in {"compaction", "compaction_history"}
    ]
    return {
        "calls": calls,
        "turns": turns,
        "tool_calls": tool_calls,
        "command_runs": command_runs,
        "file_events": file_events,
        "content_fragments": fragments,
        "compactions": compactions,
        "source_generation": source_generation,
        "coverage": _coverage_payload(
            calls=calls,
            turns=turns,
            tool_calls=tool_calls,
            command_runs=command_runs,
            file_events=file_events,
            fragments=fragments,
            compactions=compactions,
            source_coverage=source_coverage,
            content_index_enabled=content_index_enabled,
            turn_coverage=turn_coverage,
        ),
    }


def fold_compression_evidence_rows(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scope: Mapping[str, Any],
    consumer: Callable[[str, list[sqlite3.Row]], None],
    include_turns: bool = True,
    batch_size: int = 1_000,
) -> dict[str, Any]:
    """Stream scoped evidence rows to ``consumer`` and return snapshot metadata."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    with connect(db_path) as conn:
        init_db(conn)
        scoped = not _is_unfiltered_all_history(scope)
        if scoped:
            _populate_scope_records(conn, scope)
        call_count, _ = _fold_rows(
            conn,
            _scoped_sql(_CALLS_SQL, "u", scoped=scoped),
            "calls",
            consumer,
            batch_size=batch_size,
        )
        turn_count = 0
        if include_turns:
            turn_count, _ = _fold_rows(
                conn,
                _scoped_sql(_TURNS_SQL, "t", scoped=scoped),
                "turns",
                consumer,
                batch_size=batch_size,
            )
        tool_call_count, _ = _fold_rows(
            conn,
            _scoped_sql(_TOOL_CALLS_SQL, "t", scoped=scoped),
            "tool_calls",
            consumer,
            batch_size=batch_size,
        )
        command_run_count, _ = _fold_rows(
            conn,
            _scoped_sql(_COMMAND_RUNS_SQL, "c", scoped=scoped),
            "command_runs",
            consumer,
            batch_size=batch_size,
        )
        file_event_count, _ = _fold_rows(
            conn,
            _scoped_sql(_FILE_EVENTS_SQL, "f", scoped=scoped),
            "file_events",
            consumer,
            batch_size=batch_size,
        )
        fragment_count, compaction_count = _fold_rows(
            conn,
            _scoped_sql(_FRAGMENTS_SQL, "f", scoped=scoped),
            "content_fragments",
            consumer,
            batch_size=batch_size,
            count_compactions=True,
        )
        source_coverage = _source_coverage(conn, scoped=scoped)
        content_index_enabled = _content_index_enabled(conn)
        turn_coverage = _turn_coverage(conn, scoped=scoped)
        source_generation = read_compression_source_generation(conn)
    return {
        "source_generation": source_generation,
        "coverage": _coverage_counts_payload(
            call_count=call_count,
            turn_count=turn_count,
            tool_call_count=tool_call_count,
            command_run_count=command_run_count,
            file_event_count=file_event_count,
            fragment_count=fragment_count,
            compaction_count=compaction_count,
            indexed_call_count=0,
            source_coverage=source_coverage,
            content_index_enabled=content_index_enabled,
            turn_coverage=turn_coverage,
        ),
    }


def _populate_scope_records(conn: sqlite3.Connection, scope: Mapping[str, Any]) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS compression_scope_records (
            record_id TEXT PRIMARY KEY
        )
        """
    )
    conn.execute("DELETE FROM compression_scope_records")
    thread = _optional_text(scope.get("thread"))
    conn.execute(
        """
        INSERT INTO compression_scope_records(record_id)
        SELECT u.record_id
        FROM usage_events AS u
        WHERE (? = 1 OR u.is_archived = 0)
            AND (? IS NULL OR u.event_timestamp >= ?)
            AND (? IS NULL OR u.event_timestamp <= ?)
            AND (? IS NULL OR u.model = ?)
            AND (? IS NULL OR u.effort = ?)
            AND (
                ? IS NULL
                OR u.thread_key = ?
                OR u.thread_name = ?
                OR u.session_id = ?
            )
        """,
        (
            int(bool(scope.get("include_archived"))),
            _optional_text(scope.get("since")),
            _optional_text(scope.get("since")),
            _optional_text(scope.get("until")),
            _optional_text(scope.get("until")),
            _optional_text(scope.get("model")),
            _optional_text(scope.get("model")),
            _optional_text(scope.get("effort")),
            _optional_text(scope.get("effort")),
            thread,
            thread,
            thread,
            thread,
        ),
    )


def _raw_rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql))


def _fold_rows(
    conn: sqlite3.Connection,
    sql: str,
    category: str,
    consumer: Callable[[str, list[sqlite3.Row]], None],
    *,
    batch_size: int,
    count_compactions: bool = False,
) -> tuple[int, int]:
    cursor = conn.execute(sql)
    row_count = 0
    compaction_count = 0
    while batch := cursor.fetchmany(batch_size):
        row_count += len(batch)
        if count_compactions:
            compaction_count += sum(
                row["fragment_kind"] in {"compaction", "compaction_history"} for row in batch
            )
        consumer(category, batch)
    return row_count, compaction_count


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [cast(dict[str, Any], dict(row)) for row in rows]


def _is_unfiltered_all_history(scope: Mapping[str, Any]) -> bool:
    return bool(scope.get("include_archived")) and all(
        _optional_text(scope.get(key)) is None
        for key in ("since", "until", "model", "effort", "thread")
    )


def _scoped_sql(sql: str, alias: str, *, scoped: bool) -> str:
    scope_join = (
        f"JOIN compression_scope_records AS scoped ON scoped.record_id = {alias}.record_id"
        if scoped
        else ""
    )
    return sql.format(scope_join=scope_join)


def _source_coverage(conn: sqlite3.Connection, *, scoped: bool) -> dict[str, Any]:
    row = conn.execute(
        _scoped_sql(
            """
        SELECT
            COUNT(*) AS source_record_count,
            SUM(
                CASE WHEN sr.parse_warnings_json NOT IN ('', '[]') THEN 1 ELSE 0 END
            ) AS parser_warning_record_count,
            GROUP_CONCAT(DISTINCT sr.parser_adapter) AS parser_adapters,
            GROUP_CONCAT(DISTINCT sr.parser_version) AS parser_versions
        FROM source_records AS sr
        {scope_join}
        """,
            "sr",
            scoped=scoped,
        )
    ).fetchone()
    return cast(dict[str, Any], dict(row)) if row is not None else {}


def _content_index_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT enabled
        FROM content_index_features
        WHERE feature_key = 'fts5'
        """
    ).fetchone()
    return bool(row and int(row["enabled"]))


def _turn_coverage(conn: sqlite3.Connection, *, scoped: bool) -> dict[str, int]:
    row = conn.execute(
        _scoped_sql(
            """
        SELECT
            COUNT(*) AS turn_count,
            COUNT(DISTINCT CASE WHEN t.indexed_content_included = 1 THEN t.record_id END)
                AS indexed_call_count
        FROM conversation_turns AS t
        {scope_join}
        """,
            "t",
            scoped=scoped,
        )
    ).fetchone()
    return {
        "turn_count": int(row["turn_count"] or 0),
        "indexed_call_count": int(row["indexed_call_count"] or 0),
    }


def _coverage_payload(
    *,
    calls: list[sqlite3.Row],
    turns: list[sqlite3.Row],
    tool_calls: list[sqlite3.Row],
    command_runs: list[sqlite3.Row],
    file_events: list[sqlite3.Row],
    fragments: list[sqlite3.Row],
    compactions: list[sqlite3.Row],
    source_coverage: dict[str, Any],
    content_index_enabled: bool,
    turn_coverage: dict[str, int] | None,
) -> dict[str, Any]:
    indexed_calls = {
        str(row["record_id"]) for row in turns if bool(row["indexed_content_included"])
    }
    return _coverage_counts_payload(
        call_count=len(calls),
        turn_count=len(turns),
        tool_call_count=len(tool_calls),
        command_run_count=len(command_runs),
        file_event_count=len(file_events),
        fragment_count=len(fragments),
        compaction_count=len(compactions),
        indexed_call_count=len(indexed_calls),
        source_coverage=source_coverage,
        content_index_enabled=content_index_enabled,
        turn_coverage=turn_coverage,
    )


def _coverage_counts_payload(
    *,
    call_count: int,
    turn_count: int,
    tool_call_count: int,
    command_run_count: int,
    file_event_count: int,
    fragment_count: int,
    compaction_count: int,
    indexed_call_count: int,
    source_coverage: dict[str, Any],
    content_index_enabled: bool,
    turn_coverage: dict[str, int] | None,
) -> dict[str, Any]:
    return {
        "call_count": call_count,
        "turn_count": turn_coverage["turn_count"] if turn_coverage else turn_count,
        "tool_call_count": tool_call_count,
        "command_run_count": command_run_count,
        "file_event_count": file_event_count,
        "content_fragment_count": fragment_count,
        "compaction_count": compaction_count,
        "indexed_call_count": (
            turn_coverage["indexed_call_count"] if turn_coverage else indexed_call_count
        ),
        "source_record_count": int(source_coverage.get("source_record_count") or 0),
        "parser_warning_record_count": int(source_coverage.get("parser_warning_record_count") or 0),
        "parser_adapters": _csv_values(source_coverage.get("parser_adapters")),
        "parser_versions": _csv_values(source_coverage.get("parser_versions")),
        "content_index_enabled": content_index_enabled,
    }


def _csv_values(value: Any) -> list[str]:
    return sorted(item for item in str(value or "").split(",") if item)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


_CALLS_SQL = """
SELECT
    u.record_id,
    u.session_id,
    COALESCE(u.thread_key, u.thread_name, u.session_id) AS thread_key,
    u.event_timestamp,
    u.model,
    u.effort,
    u.is_archived,
    u.thread_call_index,
    u.previous_record_id,
    u.cached_input_tokens,
    u.uncached_input_tokens,
    u.output_tokens,
    u.reasoning_output_tokens,
    u.cache_ratio,
    u.context_window_percent
FROM usage_events AS u
{scope_join}
ORDER BY u.event_timestamp, u.record_id
"""

_TURNS_SQL = """
SELECT
    t.turn_key,
    t.record_id,
    t.session_id,
    t.role,
    t.event_timestamp,
    t.content_size_bytes,
    t.indexed_content_included
FROM conversation_turns AS t
{scope_join}
ORDER BY t.event_timestamp, t.turn_key
"""

_TOOL_CALLS_SQL = """
SELECT
    t.tool_call_key,
    t.record_id,
    t.turn_key,
    t.tool_name,
    t.status,
    t.duration_ms,
    t.output_size_bytes
FROM tool_calls AS t
{scope_join}
"""

_COMMAND_RUNS_SQL = """
SELECT
    c.command_run_key,
    c.record_id,
    c.turn_key,
    c.command_root,
    c.command_root AS command_label,
    c.exit_code,
    c.status,
    c.output_size_bytes,
    c.retry_group
FROM command_runs AS c
{scope_join}
"""

_FILE_EVENTS_SQL = """
SELECT
    f.file_event_key,
    f.record_id,
    f.turn_key,
    f.operation,
    f.path_hash,
    f.path_hash AS path_identity
FROM file_events AS f
{scope_join}
"""

_FRAGMENTS_SQL = """
SELECT
    f.fragment_id,
    f.record_id,
    f.turn_key,
    f.fragment_kind,
    f.role,
    f.fragment_kind AS safe_label,
    f.content_hash,
    f.content_size_bytes,
    f.includes_raw_fragment
FROM content_fragments AS f
{scope_join}
"""
