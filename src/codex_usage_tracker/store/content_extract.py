"""Codex JSONL fragment extraction for the local content index."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codex_usage_tracker.parser.state import optional_str
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
    extract_pending_local_events,
)
from codex_usage_tracker.store.content_index_models import (
    _ExtractedContentRows,
    _PendingFragment,
)
from codex_usage_tracker.store.content_rows import (
    _append_pending_content_rows,
    _empty_pending_content_rows,
)

MAX_FRAGMENT_CHARS = 4000


def _extract_content_rows_for_source_file(
    *,
    source_path: Path,
    usage_rows: Mapping[int, Mapping[str, object]],
    start_byte: int,
    start_line: int,
) -> _ExtractedContentRows:
    if not usage_rows:
        return _empty_extracted_content_rows(source_path=source_path, has_usage_rows=False)

    pending: list[_PendingFragment] = []
    pending_tool_calls: list[PendingToolCall] = []
    pending_command_runs: list[PendingCommandRun] = []
    pending_file_events: list[PendingFileEvent] = []
    pending_rows = _empty_pending_content_rows()
    turn_id: str | None = None
    turn_index = 0
    parse_warnings = 0
    try:
        with source_path.open("rb") as handle:
            if start_byte > 0:
                handle.seek(start_byte)
            for line_number, raw_line in enumerate(handle, start_line + 1):
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
                        _append_pending_content_rows(
                            pending_rows,
                            pending=pending,
                            tool_calls=pending_tool_calls,
                            command_runs=pending_command_runs,
                            file_events=pending_file_events,
                            usage_row=usage_row,
                        )
                        pending = []
                        pending_tool_calls = []
                        pending_command_runs = []
                        pending_file_events = []
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
                events = extract_pending_local_events(
                    envelope=envelope,
                    payload=payload,
                    line_number=line_number,
                    timestamp=timestamp,
                )
                pending_tool_calls.extend(events.tool_calls)
                pending_command_runs.extend(events.command_runs)
                pending_file_events.extend(events.file_events)
    except OSError:
        return _empty_extracted_content_rows(source_path=source_path, has_usage_rows=False)

    return _ExtractedContentRows(
        source_path=str(source_path),
        has_usage_rows=True,
        turn_rows=pending_rows.turn_rows,
        fragment_rows=pending_rows.fragment_rows,
        event_rows=pending_rows.event_rows,
        parse_warnings=parse_warnings,
    )


def _empty_extracted_content_rows(
    *,
    source_path: Path,
    has_usage_rows: bool,
) -> _ExtractedContentRows:
    empty_rows = _empty_pending_content_rows()
    return _ExtractedContentRows(
        source_path=str(source_path),
        has_usage_rows=has_usage_rows,
        turn_rows=[],
        fragment_rows=[],
        event_rows=empty_rows.event_rows,
    )


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
