"""Context evidence summarization helpers."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.context.values import (
    content_text,
    jsonish,
    nonnegative_float,
    nonnegative_int,
    optional_str,
    redact_text,
)

_OUTPUT_OMITTED = (
    "Tool output hidden for this request. Reload with include_tool_output=true to inspect "
    "redacted, size-limited output."
)
_SAFE_STRUCTURED_EVENT_TYPES = frozenset(
    {
        "image_generation_end",
        "mcp_tool_call_end",
        "patch_apply_end",
        "skill_completed",
        "skill_invoked",
        "skill_selected",
        "skill_started",
        "skill_used",
        "task_complete",
        "thread_rolled_back",
        "turn_aborted",
        "web_search_end",
    }
)
_SAFE_STRUCTURED_EVENT_FIELDS = (
    "type",
    "call_id",
    "turn_id",
    "phase",
    "status",
    "duration_ms",
    "num_turns",
    "started_at",
    "completed_at",
    "time_to_first_token_ms",
    "tool_name",
    "server_name",
    "skill_name",
)
_COMPACT_EVENT_FIELDS = ("call_id", "turn_id", "phase", "status", "duration_ms")
_TURN_CONTEXT_FIELDS = (
    "turn_id",
    "cwd",
    "model",
    "effort",
    "current_date",
    "timezone",
)
_CHAT_MESSAGE_ROLES = {
    "message / user": "user",
    "user_message": "user",
    "message / assistant": "assistant",
    "agent_message": "assistant",
}
_STRUCTURED_CHAT_LABELS = {"message / user", "message / assistant"}


def dedupe_chat_message_echoes(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide adjacent progress-message echoes when a structured chat message exists."""
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        if _should_replace_previous_echo(deduped, entry):
            deduped[-1] = entry
        elif _is_adjacent_echo(deduped, entry):
            continue
        else:
            deduped.append(entry)
    return deduped


def summarize_payload(
    entry_type: str,
    payload: dict[str, Any],
    include_tool_output: bool,
    include_compaction_history: bool,
) -> dict[str, Any] | None:
    """Return safe reader-facing context evidence for a raw log payload."""
    if entry_type == "response_item":
        return _summarize_response_item(payload, include_tool_output=include_tool_output)
    if _is_compaction_payload(entry_type, payload):
        return _summarize_compaction(
            payload,
            include_compaction_history=include_compaction_history,
        )
    if entry_type == "event_msg":
        return _summarize_event_msg(payload, include_tool_output=include_tool_output)
    return None


def summarize_turn_context(payload: dict[str, Any]) -> str:
    """Format turn context fields as compact evidence text."""
    lines = [
        f"{field}: {payload[field]}"
        for field in _TURN_CONTEXT_FIELDS
        if payload.get(field) not in (None, "")
    ]
    summary = optional_str(payload.get("summary"))
    if summary:
        lines.append(f"summary: {summary}")
    return "\n".join(lines) if lines else "Turn context"


def _should_replace_previous_echo(
    deduped: list[dict[str, Any]],
    entry: dict[str, Any],
) -> bool:
    if not _is_adjacent_echo(deduped, entry):
        return False
    return _is_structured_chat_message(entry) and not _is_structured_chat_message(deduped[-1])


def _is_adjacent_echo(
    deduped: list[dict[str, Any]],
    entry: dict[str, Any],
) -> bool:
    if not deduped:
        return False
    key = _chat_message_echo_key(entry)
    return key is not None and _chat_message_echo_key(deduped[-1]) == key


def _chat_message_echo_key(entry: dict[str, Any]) -> tuple[str, str] | None:
    label = optional_str(entry.get("label")) or ""
    role = _CHAT_MESSAGE_ROLES.get(label)
    if role is None:
        return None
    text = " ".join(str(entry.get("text") or "").split())
    return (role, text) if text else None


def _is_structured_chat_message(entry: dict[str, Any]) -> bool:
    return (optional_str(entry.get("label")) or "") in _STRUCTURED_CHAT_LABELS


def _is_compaction_payload(entry_type: str, payload: dict[str, Any]) -> bool:
    return entry_type == "compacted" or optional_str(payload.get("type")) == "context_compacted"


def _summarize_compaction(
    payload: dict[str, Any],
    *,
    include_compaction_history: bool,
) -> dict[str, Any]:
    replacement_entries = _replacement_history_entries(payload)
    compaction = _compaction_metadata(replacement_entries, include_compaction_history)
    if include_compaction_history and replacement_entries:
        compaction["replacement_history"] = [
            _summarize_replacement_history_item(item) for item in replacement_entries
        ]
    return {
        "label": "Compaction detected",
        "text": _compaction_text(payload, replacement_entries),
        "compaction": compaction,
    }


def _replacement_history_entries(payload: dict[str, Any]) -> list[object]:
    replacement_history = payload.get("replacement_history")
    return replacement_history if isinstance(replacement_history, list) else []


def _compaction_metadata(
    replacement_entries: list[object],
    include_compaction_history: bool,
) -> dict[str, Any]:
    return {
        "replacement_history_available": bool(replacement_entries),
        "replacement_entry_count": len(replacement_entries),
        "replacement_history_included": include_compaction_history and bool(replacement_entries),
        "classification": "confirmed_compaction",
    }


def _compaction_text(payload: dict[str, Any], replacement_entries: list[object]) -> str:
    message = optional_str(payload.get("message")) or ""
    if message:
        return redact_text(message)
    if replacement_entries:
        return (
            "Compaction detected. Replacement history contains "
            f"{len(replacement_entries)} compacted history entries."
        )
    return (
        "Compaction marker found. This event did not include replacement history, "
        "so there is no compacted summary to display."
    )


def _summarize_replacement_history_item(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        return _replacement_history_fallback(item)
    item_type = optional_str(item.get("type")) or "replacement item"
    return {
        "label": _label_for_item(item_type, item),
        "role": optional_str(item.get("role")),
        "type": item_type,
        "text": redact_text(_replacement_history_text(item)),
    }


def _replacement_history_fallback(item: object) -> dict[str, Any]:
    return {
        "label": "replacement item",
        "role": None,
        "type": type(item).__name__,
        "text": redact_text(jsonish(item)),
    }


def _replacement_history_text(item: dict[str, Any]) -> str:
    content = content_text(item.get("content"))
    if content:
        return content
    return jsonish({key: value for key, value in item.items() if key not in {"content"}})


def _summarize_response_item(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    label = _response_item_label(payload)
    summary = _response_item_text(payload, include_tool_output=include_tool_output)
    if summary is None:
        return None
    text, metadata = summary
    return {"label": label, "text": text, **metadata}


def _response_item_label(payload: dict[str, Any]) -> str:
    item_type = optional_str(payload.get("type")) or "response_item"
    return _label_for_item(item_type, payload)


def _label_for_item(item_type: str, item: dict[str, Any]) -> str:
    return " / ".join(
        part
        for part in (
            item_type,
            optional_str(item.get("role")),
            optional_str(item.get("name")),
        )
        if part
    )


def _response_item_text(
    payload: dict[str, Any],
    *,
    include_tool_output: bool,
) -> tuple[str, dict[str, Any]] | None:
    content = content_text(payload.get("content"))
    if content:
        return content, {}
    for field, prefix in (("arguments", "Tool call arguments"), ("input", "Tool input")):
        if field in payload:
            return f"{prefix}:\n{jsonish(payload.get(field))}", {}
    if "output" in payload:
        return _output_text(payload.get("output"), include_tool_output=include_tool_output)
    summary = content_text(payload.get("summary"))
    if summary:
        return summary, {}
    action = payload.get("action")
    if isinstance(action, dict):
        return f"Action:\n{jsonish(action)}", {}
    return None


def _output_text(value: object, *, include_tool_output: bool) -> tuple[str, dict[str, Any]]:
    if include_tool_output:
        return optional_str(value) or jsonish(value), {}
    return _OUTPUT_OMITTED, {"tool_output_omitted": True}


def _summarize_event_msg(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    event_type = optional_str(payload.get("type")) or "event_msg"
    token_count = _summarize_token_count(event_type, payload)
    if token_count is not None:
        return token_count
    safe_structured = _summarize_safe_structured_event(event_type, payload)
    if safe_structured is not None:
        return safe_structured
    return _summarize_event_fallback(
        event_type,
        payload,
        include_tool_output=include_tool_output,
    )


def _summarize_token_count(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if event_type != "token_count":
        return None
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    token_usage = _token_count_summary(info)
    return {
        "label": "Token count",
        "text": jsonish(token_usage),
        "token_usage": token_usage,
    }


def _summarize_event_fallback(
    event_type: str,
    payload: dict[str, Any],
    *,
    include_tool_output: bool,
) -> dict[str, Any] | None:
    if "message" in payload:
        return {"label": event_type, "text": optional_str(payload.get("message")) or ""}
    output_fields = _event_output_fields(payload)
    if output_fields:
        return _summarize_event_output(event_type, payload, output_fields, include_tool_output)
    compact = _compact_event_payload(payload)
    return {"label": event_type, "text": jsonish(compact)} if compact else None


def _event_output_fields(payload: dict[str, Any]) -> list[str]:
    return [field for field in ("stdout", "stderr", "result") if field in payload]


def _summarize_event_output(
    event_type: str,
    payload: dict[str, Any],
    output_fields: list[str],
    include_tool_output: bool,
) -> dict[str, Any]:
    if not include_tool_output:
        return {"label": event_type, "text": _OUTPUT_OMITTED, "tool_output_omitted": True}
    text = "\n".join(f"{field}:\n{jsonish(payload.get(field))}" for field in output_fields)
    return {"label": event_type, "text": text}


def _compact_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in _COMPACT_EVENT_FIELDS if key in payload}


def _summarize_safe_structured_event(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if event_type not in _SAFE_STRUCTURED_EVENT_TYPES:
        return None
    summary: dict[str, Any] = {
        "label": event_type,
        "text": jsonish(_safe_structured_payload(event_type, payload)),
        "carry_into_next_turn": True,
    }
    duration_ms = nonnegative_float(payload.get("duration_ms"))
    if duration_ms is not None:
        summary["action_duration_ms"] = duration_ms
    return summary


def _safe_structured_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {"type": event_type}
    for key in _SAFE_STRUCTURED_EVENT_FIELDS:
        if key == "type" or key not in payload:
            continue
        value = payload.get(key)
        if _is_safe_structured_scalar(value):
            compact[key] = value
    return compact


def _is_safe_structured_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _token_count_summary(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_token_usage": _token_usage_summary(info.get("last_token_usage")),
        "total_token_usage": _token_usage_summary(info.get("total_token_usage")),
        "model_context_window": info.get("model_context_window"),
    }


def _token_usage_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    usage = dict(value)
    input_tokens = nonnegative_int(usage.get("input_tokens"))
    cached_input_tokens = nonnegative_int(usage.get("cached_input_tokens"))
    if input_tokens is not None and cached_input_tokens is not None:
        usage.setdefault("uncached_input_tokens", max(input_tokens - cached_input_tokens, 0))
    return usage
