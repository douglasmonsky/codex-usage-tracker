"""Lower-level source provenance write primitives."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION

SOURCE_RECORD_COLUMNS = (
    "record_id",
    "source_file_id",
    "source_file_hash",
    "line_number",
    "event_timestamp",
    "source_record_hash",
    "hash_basis",
    "raw_shape_label",
    "parser_adapter",
    "parser_version",
    "parse_warnings_json",
    "created_from",
)
SOURCE_RECORD_HASH_BASIS = "source_file_id:line_number:record_id"
SOURCE_RECORD_SHAPE_LABEL = "token_count"
SOURCE_RECORD_CREATED_FROM = "usage_events"
SQLITE_VARIABLE_BATCH_SIZE = 500


def content_usage_row_from_event(event: UsageEvent) -> dict[str, object]:
    """Build the provenance fields content extraction needs before SQLite insertion."""
    source_file_id = _stable_hash(event.source_file)
    return {
        "record_id": event.record_id,
        "session_id": event.session_id,
        "turn_id": event.turn_id,
        "event_timestamp": event.event_timestamp,
        "source_file": event.source_file,
        "line_number": event.line_number,
        "source_file_id": source_file_id,
        "source_record_hash": _stable_hash(
            f"{source_file_id}:{event.line_number}:{event.record_id}"
        ),
        "parser_adapter": _parser_adapter_name(PARSER_ADAPTER_VERSION),
        "parser_version": PARSER_ADAPTER_VERSION,
    }


def sync_source_records(
    conn: sqlite3.Connection,
    *,
    record_ids: Iterable[str] | None = None,
    source_files: Iterable[str] | None = None,
) -> int:
    """Create or refresh provenance rows for aggregate usage events."""

    total = 0
    if record_ids is not None:
        record_id_chunks = _chunks(record_ids)
        if not record_id_chunks:
            return 0
        for chunk in record_id_chunks:
            total += _sync_source_records_chunk(conn, "u.record_id", chunk)
        return total
    if source_files is not None:
        source_file_chunks = _chunks(source_files)
        if not source_file_chunks:
            return 0
        for chunk in source_file_chunks:
            total += _sync_source_records_chunk(conn, "u.source_file", chunk)
        return total
    return _sync_source_records_chunk(conn)


def upsert_source_records_from_events(
    conn: sqlite3.Connection,
    *,
    events: Iterable[UsageEvent],
) -> int:
    """Persist source provenance directly from parsed usage events."""

    payloads = [_source_record_payload_from_event(event) for event in events]
    if not payloads:
        return 0
    before = conn.total_changes
    conn.executemany(
        _source_record_upsert_sql(),
        ([payload[column] for column in SOURCE_RECORD_COLUMNS] for payload in payloads),
    )
    return conn.total_changes - before


def _chunks(values: Iterable[str] | None) -> list[list[str]]:
    if values is None:
        return []
    unique_values = list(dict.fromkeys(str(value) for value in values))
    return [
        unique_values[start : start + SQLITE_VARIABLE_BATCH_SIZE]
        for start in range(0, len(unique_values), SQLITE_VARIABLE_BATCH_SIZE)
    ]


def _sync_source_records_chunk(
    conn: sqlite3.Connection,
    column: str | None = None,
    values: list[str] | None = None,
) -> int:
    params: list[object] = []
    where_sql = ""
    if column and values:
        placeholders = ", ".join("?" for _value in values)
        where_sql = f"WHERE {column} IN ({placeholders})"
        params.extend(values)
    rows = conn.execute(
        f"""
        SELECT
            u.record_id,
            u.source_file,
            u.line_number,
            u.event_timestamp,
            sf.source_file_id AS stored_source_file_id,
            sf.source_file_hash AS stored_source_file_hash,
            sf.parser_adapter AS stored_parser_adapter
        FROM usage_events AS u
        LEFT JOIN source_files AS sf ON sf.source_file = u.source_file
        {where_sql}
        """,
        params,
    ).fetchall()
    payloads = [_source_record_payload(row) for row in rows]
    if not payloads:
        return 0
    before = conn.total_changes
    conn.executemany(
        _source_record_upsert_sql(),
        ([payload[column_name] for column_name in SOURCE_RECORD_COLUMNS] for payload in payloads),
    )
    return conn.total_changes - before


def _source_record_payload(row: sqlite3.Row) -> dict[str, object]:
    source_file = str(row["source_file"])
    source_file_id = str(row["stored_source_file_id"] or _stable_hash(source_file))
    source_file_hash = str(row["stored_source_file_hash"] or source_file_id)
    line_number = int(row["line_number"])
    record_id = str(row["record_id"])
    parser_version = str(row["stored_parser_adapter"] or PARSER_ADAPTER_VERSION)
    return {
        "record_id": record_id,
        "source_file_id": source_file_id,
        "source_file_hash": source_file_hash,
        "line_number": line_number,
        "event_timestamp": str(row["event_timestamp"]),
        "source_record_hash": _stable_hash(
            f"{source_file_id}:{line_number}:{record_id}",
        ),
        "hash_basis": SOURCE_RECORD_HASH_BASIS,
        "raw_shape_label": SOURCE_RECORD_SHAPE_LABEL,
        "parser_adapter": _parser_adapter_name(parser_version),
        "parser_version": parser_version,
        "parse_warnings_json": "[]",
        "created_from": SOURCE_RECORD_CREATED_FROM,
    }


def _source_record_payload_from_event(event: UsageEvent) -> dict[str, object]:
    source_file_id = _stable_hash(event.source_file)
    return {
        "record_id": event.record_id,
        "source_file_id": source_file_id,
        "source_file_hash": source_file_id,
        "line_number": event.line_number,
        "event_timestamp": event.event_timestamp,
        "source_record_hash": _stable_hash(
            f"{source_file_id}:{event.line_number}:{event.record_id}"
        ),
        "hash_basis": SOURCE_RECORD_HASH_BASIS,
        "raw_shape_label": SOURCE_RECORD_SHAPE_LABEL,
        "parser_adapter": _parser_adapter_name(PARSER_ADAPTER_VERSION),
        "parser_version": PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
        "created_from": SOURCE_RECORD_CREATED_FROM,
    }


def _source_record_upsert_sql() -> str:
    placeholders = ", ".join("?" for _column in SOURCE_RECORD_COLUMNS)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in SOURCE_RECORD_COLUMNS if column != "record_id"
    )
    return (
        f"INSERT INTO source_records ({', '.join(SOURCE_RECORD_COLUMNS)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(record_id) DO UPDATE SET {update_clause}"
    )


def _parser_adapter_name(parser_version: str) -> str:
    if parser_version.startswith("codex-jsonl-"):
        return "codex-jsonl"
    return parser_version or "unknown"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
