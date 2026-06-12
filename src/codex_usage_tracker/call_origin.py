"""Derived per-call initiator metadata for aggregate dashboard rows."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class _EventFlags:
    user_message: bool = False
    compaction: bool = False
    tool_result: bool = False
    codex_activity: bool = False


def annotate_rows_with_call_origin(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate dashboard rows with derived call-level initiator metadata.

    The persisted ``thread_source`` field is session-level. A normal user-created
    thread can still contain many Codex-initiated model calls after tool results,
    agent continuations, or compactions. This helper reads only source JSONL event
    metadata around token-count lines. It does not copy prompt, assistant, or tool
    text into the returned rows.
    """

    annotated = [dict(row) for row in rows]
    rows_by_file: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in annotated:
        source_file = row.get("source_file")
        line_number = _positive_int(row.get("line_number"))
        if isinstance(source_file, str) and source_file and line_number is not None:
            rows_by_file[source_file][line_number].append(row)
        else:
            row.update(_fallback_origin(row, reason="missing_source"))

    for source_file, rows_by_line in rows_by_file.items():
        annotations = _classify_source_file(Path(source_file), set(rows_by_line))
        for line_number, line_rows in rows_by_line.items():
            annotation = annotations.get(line_number)
            for row in line_rows:
                row.update(annotation or _fallback_origin(row, reason="source_unavailable"))
    return annotated


def _classify_source_file(path: Path, target_lines: set[int]) -> dict[int, dict[str, str]]:
    if not target_lines or not path.exists():
        return {}
    max_line = max(target_lines)
    annotations: dict[int, dict[str, str]] = {}
    segment: list[_EventFlags] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number > max_line:
                    break
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if _is_token_count(envelope):
                    if line_number in target_lines:
                        annotations[line_number] = _classify_segment(segment)
                    segment = []
                    continue
                segment.append(_event_flags(envelope))
    except OSError:
        return {}
    return annotations


def _classify_segment(segment: list[_EventFlags]) -> dict[str, str]:
    if any(event.user_message for event in segment):
        return _origin("user", "user_message", "high")
    if any(event.compaction for event in segment):
        return _origin("codex", "post_compaction", "high")
    if any(event.tool_result for event in segment):
        return _origin("codex", "tool_result", "high")
    if any(event.codex_activity for event in segment):
        return _origin("codex", "agent_continuation", "medium")
    return _origin("unknown", "no_signal", "low")


def _event_flags(envelope: object) -> _EventFlags:
    if not isinstance(envelope, dict):
        return _EventFlags()
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    entry_type = envelope.get("type")
    payload_type = payload.get("type")
    role = payload.get("role")

    user_message = (
        entry_type == "event_msg"
        and payload_type == "user_message"
        or entry_type == "response_item"
        and payload_type == "message"
        and role == "user"
    )
    compaction = entry_type == "compacted" or (
        entry_type == "event_msg" and payload_type == "context_compacted"
    )
    tool_result = payload_type in {"function_call_output", "tool_search_output"} or (
        entry_type == "event_msg" and payload_type in {"mcp_tool_call_end"}
    )
    codex_activity = (
        entry_type == "event_msg"
        and payload_type in {"agent_message", "mcp_tool_call_begin"}
        or entry_type == "response_item"
        and payload_type in {"message", "reasoning", "function_call", "tool_search_call"}
        and role != "user"
    )
    return _EventFlags(
        user_message=user_message,
        compaction=compaction,
        tool_result=tool_result,
        codex_activity=codex_activity,
    )


def _is_token_count(envelope: object) -> bool:
    if not isinstance(envelope, dict):
        return False
    payload = envelope.get("payload")
    return (
        envelope.get("type") == "event_msg"
        and isinstance(payload, dict)
        and payload.get("type") == "token_count"
    )


def _fallback_origin(row: dict[str, Any], *, reason: str) -> dict[str, str]:
    if (
        row.get("model") == "codex-auto-review"
        or row.get("thread_source") == "subagent"
        or row.get("subagent_type")
        or row.get("parent_session_id")
    ):
        return _origin("codex", "thread_source", "medium")
    return _origin("unknown", reason, "low")


def _origin(initiator: str, reason: str, confidence: str) -> dict[str, str]:
    return {
        "call_initiator": initiator,
        "call_initiator_reason": reason,
        "call_initiator_confidence": confidence,
    }


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
