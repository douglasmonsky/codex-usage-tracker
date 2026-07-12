"""Scoped normalized evidence reads for Compression Lab analyses."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def query_compression_evidence(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Load one deduplicated evidence snapshot for a normalized scope."""
    with connect(db_path) as conn:
        init_db(conn)
        _populate_scope_records(conn, scope)
        calls = _rows(conn, _CALLS_SQL)
        turns = _rows(conn, _TURNS_SQL)
        tool_calls = _rows(conn, _TOOL_CALLS_SQL)
        command_runs = _rows(conn, _COMMAND_RUNS_SQL)
        file_events = _rows(conn, _FILE_EVENTS_SQL)
        fragments = _rows(conn, _FRAGMENTS_SQL)
        source_coverage = _source_coverage(conn)
        content_index_enabled = _content_index_enabled(conn)
    compactions = [
        row for row in fragments if row.get("fragment_kind") in {"compaction", "compaction_history"}
    ]
    return {
        "calls": _deduplicate(calls, "record_id"),
        "turns": _deduplicate(turns, "turn_key"),
        "tool_calls": _deduplicate(tool_calls, "tool_call_key"),
        "command_runs": _deduplicate(command_runs, "command_run_key"),
        "file_events": _deduplicate(file_events, "file_event_key"),
        "content_fragments": _deduplicate(fragments, "fragment_id"),
        "compactions": _deduplicate(compactions, "fragment_id"),
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


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql).fetchall()]


def _source_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS source_record_count,
            SUM(
                CASE WHEN sr.parse_warnings_json NOT IN ('', '[]') THEN 1 ELSE 0 END
            ) AS parser_warning_record_count,
            GROUP_CONCAT(DISTINCT sr.parser_adapter) AS parser_adapters,
            GROUP_CONCAT(DISTINCT sr.parser_version) AS parser_versions
        FROM source_records AS sr
        JOIN compression_scope_records AS scoped ON scoped.record_id = sr.record_id
        """
    ).fetchone()
    return dict(row) if row is not None else {}


def _content_index_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT enabled
        FROM content_index_features
        WHERE feature_key = 'fts5'
        """
    ).fetchone()
    return bool(row and int(row["enabled"]))


def _coverage_payload(
    *,
    calls: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    command_runs: list[dict[str, Any]],
    file_events: list[dict[str, Any]],
    fragments: list[dict[str, Any]],
    compactions: list[dict[str, Any]],
    source_coverage: dict[str, Any],
    content_index_enabled: bool,
) -> dict[str, Any]:
    indexed_calls = {
        str(row["record_id"]) for row in turns if bool(row.get("indexed_content_included"))
    }
    return {
        "call_count": len(_deduplicate(calls, "record_id")),
        "turn_count": len(_deduplicate(turns, "turn_key")),
        "tool_call_count": len(_deduplicate(tool_calls, "tool_call_key")),
        "command_run_count": len(_deduplicate(command_runs, "command_run_key")),
        "file_event_count": len(_deduplicate(file_events, "file_event_key")),
        "content_fragment_count": len(_deduplicate(fragments, "fragment_id")),
        "compaction_count": len(_deduplicate(compactions, "fragment_id")),
        "indexed_call_count": len(indexed_calls),
        "source_record_count": int(source_coverage.get("source_record_count") or 0),
        "parser_warning_record_count": int(source_coverage.get("parser_warning_record_count") or 0),
        "parser_adapters": _csv_values(source_coverage.get("parser_adapters")),
        "parser_versions": _csv_values(source_coverage.get("parser_versions")),
        "content_index_enabled": content_index_enabled,
    }


def _deduplicate(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value and value not in unique:
            unique[value] = row
    return list(unique.values())


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
JOIN compression_scope_records AS scoped ON scoped.record_id = u.record_id
ORDER BY u.event_timestamp, u.record_id
"""

_TURNS_SQL = """
SELECT t.*
FROM conversation_turns AS t
JOIN compression_scope_records AS scoped ON scoped.record_id = t.record_id
ORDER BY t.event_timestamp, t.turn_key
"""

_TOOL_CALLS_SQL = """
SELECT t.*
FROM tool_calls AS t
JOIN compression_scope_records AS scoped ON scoped.record_id = t.record_id
ORDER BY COALESCE(t.started_at, ''), t.tool_call_key
"""

_COMMAND_RUNS_SQL = """
SELECT c.*
FROM command_runs AS c
JOIN compression_scope_records AS scoped ON scoped.record_id = c.record_id
ORDER BY c.command_run_key
"""

_FILE_EVENTS_SQL = """
SELECT f.*
FROM file_events AS f
JOIN compression_scope_records AS scoped ON scoped.record_id = f.record_id
ORDER BY f.file_event_key
"""

_FRAGMENTS_SQL = """
SELECT f.*
FROM content_fragments AS f
JOIN compression_scope_records AS scoped ON scoped.record_id = f.record_id
ORDER BY f.created_at, f.fragment_id
"""
