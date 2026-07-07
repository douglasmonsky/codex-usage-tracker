"""Normalized local content indexing for Codex JSONL source logs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION, optional_str

MAX_FRAGMENT_CHARS = 4000
PARSER_ADAPTER_NAME = "codex-jsonl"
CONTENT_INDEX_TABLES = (
    "content_fragments",
    "file_events",
    "command_runs",
    "tool_calls",
    "conversation_turns",
)


@dataclass(frozen=True)
class ContentIndexResult:
    """Content indexing counts for one refresh operation."""

    source_files: int
    conversation_turns: int
    content_fragments: int
    parse_warnings: int = 0


@dataclass(frozen=True)
class _PendingFragment:
    role: str
    fragment_kind: str
    safe_label: str
    text: str
    line_start: int
    line_end: int
    turn_id: str | None
    turn_index: int
    event_timestamp: str | None


def index_content_for_source_files(
    conn: sqlite3.Connection,
    *,
    source_files: Iterable[Path],
) -> ContentIndexResult:
    """Populate normalized bounded local content rows for source files."""

    source_paths = list(dict.fromkeys(source_files))
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    for source_path in source_paths:
        result = _index_content_for_source_file(conn, source_path=source_path)
        totals = ContentIndexResult(
            source_files=totals.source_files + result.source_files,
            conversation_turns=totals.conversation_turns + result.conversation_turns,
            content_fragments=totals.content_fragments + result.content_fragments,
            parse_warnings=totals.parse_warnings + result.parse_warnings,
        )
    return totals


def clear_content_index_rows(conn: sqlite3.Connection) -> None:
    """Clear normalized content index rows while tolerating unavailable FTS5."""

    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(f"DELETE FROM {table_name}")


def delete_content_index_rows_for_source_files(
    conn: sqlite3.Connection,
    *,
    placeholders: str,
    source_files_to_replace: list[str],
) -> None:
    """Delete normalized content rows linked to source files."""

    record_subquery = (
        "SELECT record_id FROM usage_events " f"WHERE source_file IN ({placeholders})"
    )
    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(
            f"DELETE FROM {table_name} WHERE record_id IN ({record_subquery})",
            source_files_to_replace,
        )
    _rebuild_content_fts(conn)


def _index_content_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
) -> ContentIndexResult:
    usage_rows = _usage_rows_by_token_line(conn, source_file=str(source_path))
    if not usage_rows:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    delete_content_index_rows_for_source_files(
        conn,
        placeholders="?",
        source_files_to_replace=[str(source_path)],
    )
    pending: list[_PendingFragment] = []
    turn_id: str | None = None
    turn_index = 0
    parse_warnings = 0
    try:
        with source_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                try:
                    envelope = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parse_warnings += 1
                    continue
                if not isinstance(envelope, dict):
                    parse_warnings += 1
                    continue
                payload = envelope.get("payload")
                if not isinstance(payload, dict):
                    parse_warnings += 1
                    continue
                entry_type = envelope.get("type")
                timestamp = optional_str(envelope.get("timestamp"))
                if entry_type == "turn_context":
                    turn_id = optional_str(payload.get("turn_id"))
                    turn_index += 1
                    continue
                if _is_token_count(entry_type, payload):
                    usage_row = usage_rows.get(line_number)
                    if usage_row is not None:
                        _flush_pending_fragments(
                            conn,
                            pending=pending,
                            usage_row=usage_row,
                        )
                    pending = []
                    continue
                pending.extend(
                    _extract_pending_fragments(
                        envelope=envelope,
                        payload=payload,
                        line_number=line_number,
                        timestamp=timestamp,
                        turn_id=turn_id,
                        turn_index=turn_index,
                    )
                )
    except OSError:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    _rebuild_content_fts(conn)
    counts = _content_counts_for_source_file(conn, source_file=str(source_path))
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=parse_warnings,
    )


def _usage_rows_by_token_line(
    conn: sqlite3.Connection,
    *,
    source_file: str,
) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        """
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
        ORDER BY u.line_number
        """,
        (source_file,),
    ).fetchall()
    return {int(row["line_number"]): row for row in rows}


def _extract_pending_fragments(
    *,
    envelope: dict[str, Any],
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    entry_type = envelope.get("type")
    payload_type = optional_str(payload.get("type")) or ""
    if entry_type == "response_item":
        return _response_item_fragments(
            payload=payload,
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "event_msg" and payload_type == "context_compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="context_compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    return []


def _response_item_fragments(
    *,
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    payload_type = optional_str(payload.get("type")) or "response_item"
    role = optional_str(payload.get("role")) or _role_from_payload_type(payload_type)
    fragments: list[_PendingFragment] = []
    for index, text in enumerate(_content_texts(payload.get("content"))):
        fragments.append(
            _pending_fragment(
                role=role,
                fragment_kind="message",
                safe_label=f"response_item.{payload_type}.{role}.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, text in enumerate(_reasoning_summary_texts(payload.get("summary"))):
        fragments.append(
            _pending_fragment(
                role="reasoning",
                fragment_kind="reasoning_summary",
                safe_label=f"response_item.{payload_type}.reasoning_summary.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    return fragments


def _compaction_fragments(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    fragments: list[_PendingFragment] = []
    message = optional_str(payload.get("message"))
    if message:
        fragments.append(
            _pending_fragment(
                role="system",
                fragment_kind="compaction",
                safe_label=f"{payload_type}.message",
                text=message,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, item in enumerate(_message_history(payload.get("replacement_history"))):
        role = optional_str(item.get("role")) or "unknown"
        for content_index, text in enumerate(_content_texts(item.get("content"))):
            fragments.append(
                _pending_fragment(
                    role=role,
                    fragment_kind="compaction_history",
                    safe_label=f"{payload_type}.replacement_history.{role}.{index}.{content_index}",
                    text=text,
                    line_number=line_number,
                    timestamp=timestamp,
                    turn_id=turn_id,
                    turn_index=turn_index,
                )
            )
    return fragments


def _pending_fragment(
    *,
    role: str,
    fragment_kind: str,
    safe_label: str,
    text: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> _PendingFragment:
    return _PendingFragment(
        role=role,
        fragment_kind=fragment_kind,
        safe_label=safe_label,
        text=text[:MAX_FRAGMENT_CHARS],
        line_start=line_number,
        line_end=line_number,
        turn_id=turn_id,
        turn_index=turn_index,
        event_timestamp=timestamp,
    )


def _flush_pending_fragments(
    conn: sqlite3.Connection,
    *,
    pending: list[_PendingFragment],
    usage_row: sqlite3.Row,
) -> None:
    if not pending:
        return
    turn_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    for index, fragment in enumerate(pending):
        turn_key = _stable_hash(
            f"turn:{usage_row['record_id']}:{fragment.line_start}:{fragment.role}:{index}"
        )
        turn_rows.append(_turn_row(turn_key=turn_key, fragment=fragment, usage_row=usage_row))
        fragment_rows.append(
            _fragment_row(
                fragment_id=_stable_hash(
                    f"fragment:{turn_key}:{index}:{_stable_hash(fragment.text)}"
                ),
                turn_key=turn_key,
                fragment=fragment,
                usage_row=usage_row,
            )
        )
    _upsert_turn_rows(conn, turn_rows)
    _upsert_fragment_rows(conn, fragment_rows)


def _turn_row(
    *,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: sqlite3.Row,
) -> dict[str, object]:
    return {
        "turn_key": turn_key,
        "record_id": str(usage_row["record_id"]),
        "session_id": str(usage_row["session_id"]),
        "turn_id": fragment.turn_id or usage_row["turn_id"],
        "turn_index": fragment.turn_index,
        "role": fragment.role,
        "event_timestamp": fragment.event_timestamp or usage_row["event_timestamp"],
        "source_record_hash": usage_row["source_record_hash"],
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "indexed_content_included": 1,
        "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
        "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
    }


def _fragment_row(
    *,
    fragment_id: str,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: sqlite3.Row,
) -> dict[str, object]:
    return {
        "fragment_id": fragment_id,
        "record_id": str(usage_row["record_id"]),
        "turn_key": turn_key,
        "fragment_kind": fragment.fragment_kind,
        "role": fragment.role,
        "safe_label": fragment.safe_label,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "fragment_text": fragment.text,
        "includes_raw_fragment": 1,
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "token_link_record_id": str(usage_row["record_id"]),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


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
        f"INSERT INTO {table_name} ({', '.join(columns)}) "
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


def _content_texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            text = optional_str(item.get("text"))
            if text:
                texts.append(text)
    return texts


def _reasoning_summary_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = optional_str(item.get("text")) or optional_str(item.get("summary_text"))
            if text:
                texts.append(text)
    return texts


def _message_history(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _role_from_payload_type(payload_type: str) -> str:
    if payload_type == "reasoning":
        return "reasoning"
    if payload_type in {"function_call", "function_call_output"}:
        return "tool"
    return "unknown"


def _is_token_count(entry_type: object, payload: dict[str, Any]) -> bool:
    return entry_type == "event_msg" and payload.get("type") == "token_count"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
