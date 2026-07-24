"""Build and limit reader-facing context entries."""

from __future__ import annotations

import json
from typing import Any

from codex_usage_tracker.context.action_timing import normalize_millisecond_value
from codex_usage_tracker.context.values import nonnegative_float, optional_str, redact_text


def context_envelope_from_line(line: str) -> tuple[dict[str, Any] | None, bool]:
    try:
        envelope = json.loads(line)
    except json.JSONDecodeError:
        return None, True
    if not isinstance(envelope, dict):
        return None, False
    return envelope, False


def context_envelope_parts(
    envelope: dict[str, Any],
) -> tuple[str, dict[str, Any], str | None]:
    raw_payload = envelope.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    return (
        optional_str(envelope.get("type")) or "unknown",
        payload,
        optional_str(envelope.get("timestamp")),
    )


def is_token_count_boundary(
    line_number: int,
    token_line: int,
    entry_type: str,
    payload: dict[str, Any],
) -> bool:
    return (
        line_number >= token_line
        and entry_type == "event_msg"
        and payload.get("type") == "token_count"
    )


def summarized_context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    summarized: dict[str, Any],
) -> dict[str, Any]:
    return context_entry(
        line_number,
        timestamp,
        entry_type,
        summarized["label"],
        summarized["text"],
        tool_output_omitted=bool(summarized.get("tool_output_omitted")),
        token_usage=summarized.get("token_usage")
        if isinstance(summarized.get("token_usage"), dict)
        else None,
        compaction=summarized.get("compaction")
        if isinstance(summarized.get("compaction"), dict)
        else None,
        action_duration_ms=nonnegative_float(summarized.get("action_duration_ms")),
    )


def context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    label: str,
    text: str,
    *,
    tool_output_omitted: bool = False,
    token_usage: dict[str, Any] | None = None,
    compaction: dict[str, Any] | None = None,
    action_duration_ms: float | None = None,
) -> dict[str, Any]:
    entry = {
        "line_number": line_number,
        "timestamp": timestamp,
        "type": entry_type,
        "label": label,
        "text": redact_text(text),
        "truncated": False,
    }
    if tool_output_omitted:
        entry["tool_output_omitted"] = True
    if token_usage:
        entry["token_usage"] = token_usage
    if compaction:
        entry["compaction"] = compaction
    if action_duration_ms is not None:
        entry["action_timing"] = {
            "reported_duration_ms": normalize_millisecond_value(action_duration_ms),
            "duration_source": "event.duration_ms",
        }
    return entry


def limit_entries(
    entries: list[dict[str, Any]],
    max_chars: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limited_reversed: list[dict[str, Any]] = []
    remaining = None if max_chars <= 0 else max_chars
    omitted_entries = 0
    omitted_chars = 0
    selected = entries if max_entries <= 0 else entries[-max_entries:]

    for entry in reversed(selected):
        text = str(entry.get("text") or "")
        if remaining is None:
            limited_reversed.append(entry)
            continue
        if remaining <= 0:
            omitted_entries += 1
            omitted_chars += len(text)
            continue
        if len(text) > remaining:
            entry = dict(entry)
            entry["text"] = text[:remaining] + "\n[TRUNCATED]"
            entry["truncated"] = True
            omitted_chars += len(text) - remaining
            remaining = 0
        else:
            remaining -= len(text)
        limited_reversed.append(entry)

    limited = list(reversed(limited_reversed))
    return limited, {
        "older_entries": 0 if max_entries <= 0 else max(0, len(entries) - max_entries),
        "over_budget_entries": omitted_entries,
        "over_budget_chars": omitted_chars,
        "max_chars": max_chars,
        "max_entries": max_entries,
        "returned_entries": len(limited),
    }
