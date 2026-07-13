"""Normalized row construction for local content indexing."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION
from codex_usage_tracker.store.content_index_event_store import (
    PendingEventRows,
    pending_event_rows,
)
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
)
from codex_usage_tracker.store.content_index_models import (
    UsageContentRow,
    _PendingContentRows,
    _PendingFragment,
)

PARSER_ADAPTER_NAME = "codex-jsonl"


def _empty_pending_content_rows() -> _PendingContentRows:
    return _PendingContentRows(
        turn_rows=[],
        fragment_rows=[],
        event_rows=PendingEventRows(
            tool_call_rows=[],
            command_run_rows=[],
            file_event_rows=[],
        ),
    )


def _append_pending_content_rows(
    batch: _PendingContentRows,
    *,
    pending: list[_PendingFragment],
    tool_calls: list[PendingToolCall],
    command_runs: list[PendingCommandRun],
    file_events: list[PendingFileEvent],
    usage_row: UsageContentRow,
    created_at: str,
) -> None:
    turn_rows, fragment_rows = _pending_fragment_rows(
        pending=pending,
        usage_row=usage_row,
        created_at=created_at,
    )
    event_rows = pending_event_rows(
        tool_calls=tool_calls,
        command_runs=command_runs,
        file_events=file_events,
        usage_row=usage_row,
    )
    batch.turn_rows.extend(turn_rows)
    batch.fragment_rows.extend(fragment_rows)
    batch.event_rows.tool_call_rows.extend(event_rows.tool_call_rows)
    batch.event_rows.command_run_rows.extend(event_rows.command_run_rows)
    batch.event_rows.file_event_rows.extend(event_rows.file_event_rows)
    batch.linked_records += 1


def _pending_fragment_rows(
    *,
    pending: list[_PendingFragment],
    usage_row: UsageContentRow,
    created_at: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not pending:
        return [], []
    turn_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    for index, fragment in enumerate(pending):
        content_hash = _stable_hash(fragment.text)
        content_size_bytes = len(fragment.text.encode("utf-8"))
        turn_key = _stable_hash(
            f"turn:{usage_row['record_id']}:{fragment.line_start}:{fragment.role}:{index}"
        )
        turn_rows.append(
            _turn_row(
                turn_key=turn_key,
                fragment=fragment,
                usage_row=usage_row,
                content_hash=content_hash,
                content_size_bytes=content_size_bytes,
            )
        )
        fragment_rows.append(
            _fragment_row(
                fragment_id=_stable_hash(f"fragment:{turn_key}:{index}:{content_hash}"),
                turn_key=turn_key,
                fragment=fragment,
                usage_row=usage_row,
                content_hash=content_hash,
                content_size_bytes=content_size_bytes,
                created_at=created_at,
            )
        )
    return turn_rows, fragment_rows


def _turn_row(
    *,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: UsageContentRow,
    content_hash: str,
    content_size_bytes: int,
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
        "content_hash": content_hash,
        "content_size_bytes": content_size_bytes,
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
    usage_row: UsageContentRow,
    content_hash: str,
    content_size_bytes: int,
    created_at: str,
) -> dict[str, object]:
    return {
        "fragment_id": fragment_id,
        "record_id": str(usage_row["record_id"]),
        "turn_key": turn_key,
        "fragment_kind": fragment.fragment_kind,
        "role": fragment.role,
        "safe_label": fragment.safe_label,
        "content_hash": content_hash,
        "content_size_bytes": content_size_bytes,
        "fragment_text": fragment.text,
        "includes_raw_fragment": 1,
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "token_link_record_id": str(usage_row["record_id"]),
        "created_at": created_at,
    }


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_row_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
