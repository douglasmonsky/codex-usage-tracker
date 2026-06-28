"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.context_token_estimates import (
    context_encoding,
    estimate_visible_tokens,
    token_estimate,
)
from codex_usage_tracker.context_values import (
    compact_json,
    content_text,
    jsonish,
    nonnegative_float,
    nonnegative_int,
    optional_str,
    positive_int,
    redact_json_value,
    redact_text,
)
from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store_usage_record_queries import query_usage_record

DEFAULT_CONTEXT_CHARS = 20_000
DEFAULT_CONTEXT_ENTRIES = 80
CONTEXT_MODE_QUICK = "quick"
CONTEXT_MODE_FULL = "full"
CONTEXT_MODES = {CONTEXT_MODE_QUICK, CONTEXT_MODE_FULL}

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


def load_call_context(
    record_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
    include_compaction_history: bool = False,
    diagnostics: bool = False,
    mode: str = CONTEXT_MODE_QUICK,
) -> dict[str, Any]:
    """Load logged turn context for one model call from the source JSONL file.

    This intentionally reads raw transcript-like data only on demand. The returned
    context is not written back to SQLite or embedded in dashboard HTML.
    """

    context_mode = _normalize_context_mode(mode)
    diagnostic_payload: dict[str, Any] | None = {} if diagnostics else None
    db_lookup_started = perf_counter()
    row = query_usage_record(db_path=db_path, record_id=record_id)
    if diagnostic_payload is not None:
        diagnostic_payload["db_lookup_ms"] = _elapsed_ms(db_lookup_started)
    if row is None:
        raise ValueError(f"No usage record found for record_id: {record_id}")

    source_file = Path(str(row.get("source_file") or ""))
    if not source_file.exists():
        raise FileNotFoundError(f"Source log not found: {source_file}")
    source_file_bytes = source_file.stat().st_size

    line_number = positive_int(row.get("line_number"))
    if line_number is None:
        raise ValueError(f"Usage record has no valid source line: {record_id}")

    target_turn_id = optional_str(row.get("turn_id"))
    source_scan_started = perf_counter()
    (
        entries,
        omitted,
        estimate_entries,
        serialized_estimate,
        serialized_estimate_ms,
        action_timing,
    ) = (
        _read_context_entries(
            path=source_file,
            token_line=line_number,
            target_turn_id=target_turn_id,
            max_chars=max_chars if max_chars <= 0 else max(1_000, max_chars),
            max_entries=max_entries if max_entries <= 0 else max(1, max_entries),
            include_tool_output=include_tool_output,
            include_compaction_history=include_compaction_history,
            model=optional_str(row.get("model")),
            context_mode=context_mode,
        )
    )
    source_scan_ms = _elapsed_ms(source_scan_started)
    if diagnostic_payload is not None:
        diagnostic_payload["source_scan_ms"] = source_scan_ms
    visible_estimate = estimate_visible_tokens(estimate_entries, optional_str(row.get("model")))
    if diagnostic_payload is not None:
        diagnostic_payload["serialized_estimate_ms"] = serialized_estimate_ms
        diagnostic_payload["source_file_bytes"] = source_file_bytes
        diagnostic_payload["source_line_number"] = line_number
        diagnostic_payload["entries_before_limit"] = int(omitted.get("total_entries") or 0)
        diagnostic_payload["entries_returned"] = len(entries)
    payload = {
        "schema": "codex-usage-tracker-context-v1",
        "loaded_on_demand": True,
        "raw_context_persisted": False,
        "context_mode": context_mode,
        "include_tool_output": include_tool_output,
        "include_compaction_history": include_compaction_history,
        "visible_char_count": visible_estimate["visible_char_count"],
        "visible_token_estimate": visible_estimate["visible_token_estimate"],
        "visible_token_estimator": visible_estimate["visible_token_estimator"],
        "serialized_evidence": serialized_estimate,
        "action_timing": action_timing,
        "record": {
            "record_id": row.get("record_id"),
            "session_id": row.get("session_id"),
            "thread_name": row.get("thread_name"),
            "turn_id": row.get("turn_id"),
            "event_timestamp": row.get("event_timestamp"),
            "model": row.get("model"),
            "effort": row.get("effort"),
            "parent_session_id": row.get("parent_session_id"),
            "parent_thread_name": row.get("parent_thread_name"),
            "total_tokens": row.get("total_tokens"),
            "cumulative_total_tokens": row.get("cumulative_total_tokens"),
        },
        "source": {
            "file": str(source_file),
            "line_number": line_number,
        },
        "entries": entries,
        "omitted": omitted,
    }
    if diagnostic_payload is not None:
        payload["diagnostics"] = diagnostic_payload
        diagnostic_payload["json_bytes"] = _json_byte_count(payload)
    return payload


def _normalize_context_mode(mode: str) -> str:
    normalized = str(mode or CONTEXT_MODE_QUICK).strip().lower()
    if normalized not in CONTEXT_MODES:
        raise ValueError(
            f"Unsupported context mode: {mode}. Expected one of: "
            f"{', '.join(sorted(CONTEXT_MODES))}"
        )
    return normalized


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _json_byte_count(payload: dict[str, Any]) -> int:
    previous_size: int | None = None
    diagnostics = payload.get("diagnostics")
    while True:
        size = len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        if size == previous_size or not isinstance(diagnostics, dict):
            return size
        diagnostics["json_bytes"] = size
        previous_size = size


def _read_context_entries(
    path: Path,
    token_line: int,
    target_turn_id: str | None,
    max_chars: int,
    max_entries: int,
    include_tool_output: bool,
    include_compaction_history: bool,
    model: str | None,
    context_mode: str,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    float,
    dict[str, Any],
]:
    candidates: list[dict[str, Any]] = []
    raw_entries: list[dict[str, Any]] = []
    field_buckets: dict[str, dict[str, Any]] = {}
    serialized_line_count = 0
    serialized_raw_char_count = 0
    omitted_parse_errors = 0
    current_turn_id: str | None = None
    collecting = target_turn_id is None
    pending_compactions: list[dict[str, Any]] = []
    pending_diagnostic_events: list[dict[str, Any]] = []
    full_serialized_analysis = context_mode == CONTEXT_MODE_FULL
    encoding, estimator = (
        context_encoding(model or "")
        if full_serialized_analysis
        else (None, "chars_per_4_fallback")
    )

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line_number > token_line:
                break
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                omitted_parse_errors += 1
                continue
            if not isinstance(envelope, dict):
                continue
            entry_type = optional_str(envelope.get("type")) or "unknown"
            payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
            timestamp = optional_str(envelope.get("timestamp"))

            if entry_type == "turn_context":
                was_collecting = collecting
                current_turn_id = optional_str(payload.get("turn_id"))
                collecting = target_turn_id is None or current_turn_id == target_turn_id
                if collecting:
                    raw_entries = []
                    field_buckets = {}
                    serialized_line_count = 0
                    serialized_raw_char_count = 0
                    if full_serialized_analysis:
                        _collect_serialized_envelope(
                            raw_entries=raw_entries,
                            field_buckets=field_buckets,
                            envelope=envelope,
                            entry_type=entry_type,
                            payload=payload,
                            encoding=encoding,
                        )
                    else:
                        serialized_line_count += 1
                        serialized_raw_char_count += len(line)
                    carried_compactions = (
                        [entry for entry in candidates if entry.get("type") == "compacted"]
                        if was_collecting and target_turn_id is not None
                        else []
                    )
                    candidates = []
                    candidates.append(
                        _context_entry(
                            line_number,
                            timestamp,
                            entry_type,
                            "Turn context",
                            _summarize_turn_context(payload),
                        )
                    )
                    candidates.extend(pending_compactions)
                    candidates.extend(pending_diagnostic_events)
                    candidates.extend(carried_compactions)
                pending_compactions = []
                pending_diagnostic_events = []
                continue

            if collecting:
                if full_serialized_analysis:
                    _collect_serialized_envelope(
                        raw_entries=raw_entries,
                        field_buckets=field_buckets,
                        envelope=envelope,
                        entry_type=entry_type,
                        payload=payload,
                        encoding=encoding,
                    )
                else:
                    serialized_line_count += 1
                    serialized_raw_char_count += len(line)

            summarized = _summarize_payload(
                entry_type=entry_type,
                payload=payload,
                include_tool_output=include_tool_output,
                include_compaction_history=include_compaction_history,
            )

            if not collecting and entry_type == "compacted" and summarized is not None:
                pending_compactions = [
                    _summarized_context_entry(
                        line_number,
                        timestamp,
                        entry_type,
                        summarized,
                    )
                ]
                continue

            if (
                not collecting
                and summarized is not None
                and summarized.get("carry_into_next_turn") is True
            ):
                pending_diagnostic_events = [
                    *pending_diagnostic_events,
                    _summarized_context_entry(
                        line_number,
                        timestamp,
                        entry_type,
                        summarized,
                    ),
                ][-8:]
                continue

            if not collecting:
                continue

            if summarized is not None:
                candidates.append(_summarized_context_entry(line_number, timestamp, entry_type, summarized))

            if (
                line_number >= token_line
                and entry_type == "event_msg"
                and payload.get("type") == "token_count"
            ):
                break

    serialized_started = perf_counter()
    if full_serialized_analysis:
        serialized_estimate = _serialized_context_estimate(
            raw_entries=raw_entries,
            field_buckets=field_buckets,
            parse_errors=omitted_parse_errors,
            encoding=encoding,
            estimator=estimator,
        )
    else:
        serialized_estimate = _quick_serialized_context_estimate(
            raw_line_count=serialized_line_count,
            raw_json_char_count=serialized_raw_char_count,
            parse_errors=omitted_parse_errors,
        )
    serialized_estimate_ms = _elapsed_ms(serialized_started)
    candidates = _dedupe_chat_message_echoes(candidates)
    action_timing = _annotate_action_timing(candidates)
    limited, omitted = _limit_entries(candidates, max_chars=max_chars, max_entries=max_entries)
    omitted["parse_errors"] = omitted_parse_errors
    omitted["target_turn_id"] = target_turn_id
    omitted["total_entries"] = len(candidates)
    return limited, omitted, candidates, serialized_estimate, serialized_estimate_ms, action_timing


def _collect_serialized_envelope(
    *,
    raw_entries: list[dict[str, Any]],
    field_buckets: dict[str, dict[str, Any]],
    envelope: dict[str, Any],
    entry_type: str,
    payload: dict[str, Any],
    encoding: Any | None,
) -> None:
    raw_entries.append(envelope)
    _collect_serialized_field_buckets(
        buckets=field_buckets,
        entry_type=entry_type,
        payload=payload,
        encoding=encoding,
    )


def _serialized_context_estimate(
    *,
    raw_entries: list[dict[str, Any]],
    field_buckets: dict[str, dict[str, Any]],
    parse_errors: int,
    encoding: Any | None,
    estimator: str,
) -> dict[str, Any]:
    raw_json = "\n".join(compact_json(redact_json_value(entry)) for entry in raw_entries)
    top_buckets = sorted(
        field_buckets.values(),
        key=lambda bucket: int(bucket.get("token_estimate") or 0),
        reverse=True,
    )[:8]
    return {
        "available": bool(raw_entries),
        "scope": "selected_turn_raw_jsonl",
        "raw_line_count": len(raw_entries),
        "raw_json_char_count": len(raw_json),
        "raw_json_token_estimate": token_estimate(raw_json, encoding),
        "token_estimator": estimator,
        "parse_errors": parse_errors,
        "upper_bound": True,
        "raw_text_returned": False,
        "buckets": top_buckets,
        "deferred": False,
        "deferred_buckets": False,
    }


def _quick_serialized_context_estimate(
    *,
    raw_line_count: int,
    raw_json_char_count: int,
    parse_errors: int,
) -> dict[str, Any]:
    return {
        "available": raw_line_count > 0,
        "scope": "selected_turn_raw_jsonl_fast_estimate",
        "raw_line_count": raw_line_count,
        "raw_json_char_count": raw_json_char_count,
        "raw_json_token_estimate": ceil(raw_json_char_count / 4) if raw_json_char_count else 0,
        "token_estimator": "chars_per_4_fallback",
        "parse_errors": parse_errors,
        "upper_bound": True,
        "raw_text_returned": False,
        "buckets": [],
        "deferred": True,
        "deferred_buckets": True,
        "reason": "full_serialized_analysis_not_requested",
    }


def _summarized_context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    summarized: dict[str, Any],
) -> dict[str, Any]:
    return _context_entry(
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


def _dedupe_chat_message_echoes(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide adjacent progress-message echoes when a structured chat message exists."""

    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = _chat_message_echo_key(entry)
        if key and deduped and _chat_message_echo_key(deduped[-1]) == key:
            if _is_structured_chat_message(entry) and not _is_structured_chat_message(deduped[-1]):
                deduped[-1] = entry
            elif _is_structured_chat_message(deduped[-1]):
                continue
            else:
                continue
        else:
            deduped.append(entry)
    return deduped


def _chat_message_echo_key(entry: dict[str, Any]) -> tuple[str, str] | None:
    label = optional_str(entry.get("label")) or ""
    role = None
    if label == "message / user" or label == "user_message":
        role = "user"
    elif label == "message / assistant" or label == "agent_message":
        role = "assistant"
    if role is None:
        return None
    text = " ".join(str(entry.get("text") or "").split())
    return (role, text) if text else None


def _is_structured_chat_message(entry: dict[str, Any]) -> bool:
    return (optional_str(entry.get("label")) or "") in {"message / user", "message / assistant"}


def _summarize_payload(
    entry_type: str,
    payload: dict[str, Any],
    include_tool_output: bool,
    include_compaction_history: bool,
) -> dict[str, Any] | None:
    if entry_type == "response_item":
        return _summarize_response_item(payload, include_tool_output=include_tool_output)
    if optional_str(payload.get("type")) == "context_compacted":
        return _summarize_compaction(
            payload,
            include_compaction_history=include_compaction_history,
        )
    if entry_type == "event_msg":
        return _summarize_event_msg(payload, include_tool_output=include_tool_output)
    if entry_type == "compacted":
        return _summarize_compaction(
            payload,
            include_compaction_history=include_compaction_history,
        )
    return None


def _summarize_compaction(
    payload: dict[str, Any],
    *,
    include_compaction_history: bool,
) -> dict[str, Any]:
    replacement_history = payload.get("replacement_history")
    replacement_entries = replacement_history if isinstance(replacement_history, list) else []
    message = optional_str(payload.get("message")) or ""
    compaction: dict[str, Any] = {
        "replacement_history_available": bool(replacement_entries),
        "replacement_entry_count": len(replacement_entries),
        "replacement_history_included": include_compaction_history and bool(replacement_entries),
        "classification": "confirmed_compaction",
    }
    if message:
        text = redact_text(message)
    elif replacement_entries:
        text = (
            "Compaction detected. Replacement history contains "
            f"{len(replacement_entries)} compacted history entries."
        )
    else:
        text = (
            "Compaction marker found. This event did not include replacement history, "
            "so there is no compacted summary to display."
        )
    if include_compaction_history and replacement_entries:
        compaction["replacement_history"] = [
            _summarize_replacement_history_item(item) for item in replacement_entries
        ]
    return {
        "label": "Compaction detected",
        "text": text,
        "compaction": compaction,
    }


def _summarize_replacement_history_item(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "label": "replacement item",
            "role": None,
            "type": type(item).__name__,
            "text": redact_text(jsonish(item)),
        }
    item_type = optional_str(item.get("type")) or "replacement item"
    role = optional_str(item.get("role"))
    name = optional_str(item.get("name"))
    label_bits = [item_type]
    if role:
        label_bits.append(role)
    if name:
        label_bits.append(name)
    text = content_text(item.get("content")) or jsonish(
        {key: value for key, value in item.items() if key not in {"content"}}
    )
    return {
        "label": " / ".join(label_bits),
        "role": role,
        "type": item_type,
        "text": redact_text(text),
    }


def _summarize_turn_context(payload: dict[str, Any]) -> str:
    fields = [
        ("turn_id", payload.get("turn_id")),
        ("cwd", payload.get("cwd")),
        ("model", payload.get("model")),
        ("effort", payload.get("effort")),
        ("current_date", payload.get("current_date")),
        ("timezone", payload.get("timezone")),
    ]
    lines = [f"{key}: {value}" for key, value in fields if value not in (None, "")]
    summary = optional_str(payload.get("summary"))
    if summary:
        lines.append(f"summary: {summary}")
    return "\n".join(lines) if lines else "Turn context"


def _summarize_response_item(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    item_type = optional_str(payload.get("type")) or "response_item"
    role = optional_str(payload.get("role"))
    name = optional_str(payload.get("name"))
    label_bits = [item_type]
    if role:
        label_bits.append(role)
    if name:
        label_bits.append(name)
    label = " / ".join(label_bits)

    content = content_text(payload.get("content"))
    if content:
        return {"label": label, "text": content}

    if "arguments" in payload:
        return {
            "label": label,
            "text": f"Tool call arguments:\n{jsonish(payload.get('arguments'))}",
        }

    if "input" in payload:
        return {
            "label": label,
            "text": f"Tool input:\n{jsonish(payload.get('input'))}",
        }

    if "output" in payload:
        output = optional_str(payload.get("output")) or jsonish(payload.get("output"))
        if include_tool_output:
            return {"label": label, "text": output}
        return {"label": label, "text": _OUTPUT_OMITTED, "tool_output_omitted": True}

    summary = content_text(payload.get("summary"))
    if summary:
        return {"label": label, "text": summary}

    action = payload.get("action")
    if isinstance(action, dict):
        return {"label": label, "text": f"Action:\n{jsonish(action)}"}

    return None


def _summarize_event_msg(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    event_type = optional_str(payload.get("type")) or "event_msg"
    if event_type == "token_count":
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        token_usage = _token_count_summary(info)
        return {
            "label": "Token count",
            "text": jsonish(token_usage),
            "token_usage": token_usage,
        }

    safe_structured = _summarize_safe_structured_event(event_type, payload)
    if safe_structured is not None:
        return safe_structured

    if "message" in payload:
        return {"label": event_type, "text": optional_str(payload.get("message")) or ""}

    output_fields = [field for field in ("stdout", "stderr", "result") if field in payload]
    if output_fields:
        if not include_tool_output:
            return {"label": event_type, "text": _OUTPUT_OMITTED, "tool_output_omitted": True}
        text = "\n".join(f"{field}:\n{jsonish(payload.get(field))}" for field in output_fields)
        return {"label": event_type, "text": text}

    compact = {
        key: payload.get(key)
        for key in ("call_id", "turn_id", "phase", "status", "duration_ms")
        if key in payload
    }
    return {"label": event_type, "text": jsonish(compact)} if compact else None


def _summarize_safe_structured_event(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if event_type not in _SAFE_STRUCTURED_EVENT_TYPES:
        return None
    compact: dict[str, Any] = {"type": event_type}
    for key in _SAFE_STRUCTURED_EVENT_FIELDS:
        if key == "type" or key not in payload:
            continue
        value = payload.get(key)
        if _is_safe_structured_scalar(value):
            compact[key] = value
    summary: dict[str, Any] = {
        "label": event_type,
        "text": jsonish(compact),
        "carry_into_next_turn": True,
    }
    duration_ms = nonnegative_float(payload.get("duration_ms"))
    if duration_ms is not None:
        summary["action_duration_ms"] = duration_ms
    return summary


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


def _context_entry(
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
            "reported_duration_ms": _normalize_millisecond_value(action_duration_ms),
            "duration_source": "event.duration_ms",
        }
    return entry


def _annotate_action_timing(entries: list[dict[str, Any]]) -> dict[str, Any]:
    first_ms: float | None = None
    previous_ms: float | None = None
    last_ms: float | None = None
    timed_entries = 0
    slowest_gap_ms = 0.0

    for entry in entries:
        timestamp_ms = _timestamp_epoch_ms(entry.get("timestamp"))
        if timestamp_ms is None:
            continue
        if first_ms is None:
            first_ms = timestamp_ms
        existing_timing = entry.get("action_timing")
        action_timing = dict(existing_timing) if isinstance(existing_timing, dict) else {}
        action_timing["since_turn_start_ms"] = _duration_between_ms(first_ms, timestamp_ms)
        if previous_ms is not None:
            gap_ms = _duration_between_ms(previous_ms, timestamp_ms)
            action_timing["since_previous_entry_ms"] = gap_ms
            slowest_gap_ms = max(slowest_gap_ms, float(gap_ms))
        action_timing["timestamp_source"] = "entry.timestamp"
        entry["action_timing"] = action_timing
        previous_ms = timestamp_ms
        last_ms = timestamp_ms
        timed_entries += 1

    total_elapsed_ms = (
        _duration_between_ms(first_ms, last_ms)
        if first_ms is not None and last_ms is not None
        else 0
    )
    return {
        "available": timed_entries > 1,
        "scope": "selected_turn_evidence_entries",
        "source": "entry_timestamps",
        "timed_entry_count": timed_entries,
        "total_elapsed_ms": total_elapsed_ms,
        "slowest_gap_ms": _normalize_millisecond_value(slowest_gap_ms),
    }


def _timestamp_epoch_ms(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000


def _duration_between_ms(start_ms: float, end_ms: float) -> int | float:
    return _normalize_millisecond_value(max(0.0, end_ms - start_ms))


def _normalize_millisecond_value(value: float) -> int | float:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _limit_entries(
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



def _collect_serialized_field_buckets(
    *,
    buckets: dict[str, dict[str, Any]],
    entry_type: str,
    payload: dict[str, Any],
    encoding: Any | None,
) -> None:
    payload_type = optional_str(payload.get("type")) or ""
    for key, value in payload.items():
        if key == "type":
            continue
        bucket_key, label, note = _serialized_bucket_label(entry_type, payload_type, key)
        rendered = compact_json({key: redact_json_value(value)})
        stats = buckets.setdefault(
            bucket_key,
            {
                "key": bucket_key,
                "label": label,
                "note": note,
                "count": 0,
                "char_count": 0,
                "token_estimate": 0,
            },
        )
        stats["count"] = int(stats["count"]) + 1
        stats["char_count"] = int(stats["char_count"]) + len(rendered)
        stats["token_estimate"] = int(stats["token_estimate"]) + token_estimate(rendered, encoding)


def _serialized_bucket_label(
    entry_type: str,
    payload_type: str,
    key: str,
) -> tuple[str, str, str]:
    if entry_type == "response_item" and key == "encrypted_content":
        return (
            "encrypted_reasoning_state",
            "Encrypted reasoning/state payload",
            "Opaque local payload; counted as serialized evidence, not readable text.",
        )
    if key in {"content", "message", "output", "arguments", "input"}:
        return (
            "visible_payload_fields",
            "Visible message/tool payload fields",
            "Raw JSON representation of content already summarized in evidence.",
        )
    if key == "goal":
        return (
            "local_goal_metadata",
            "Local thread goal metadata",
            "Client-side workflow metadata in the log; may not be model prompt input.",
        )
    if entry_type == "event_msg" and key == "rate_limits":
        return (
            "rate_limit_metadata",
            "Rate-limit metadata",
            "Client-side rate-limit state in the log; useful as an upper-bound bucket only.",
        )
    if entry_type == "event_msg" and payload_type == "token_count" and key == "info":
        return (
            "token_callback_metadata",
            "Token callback metadata",
            "Structured callback accounting already partly summarized in evidence.",
        )
    if key in {
        "call_id",
        "threadId",
        "turnId",
        "turn_id",
        "phase",
        "status",
        "name",
        "role",
        "memory_citation",
        "summary",
        "duration_ms",
    }:
        return (
            "protocol_metadata",
            "Protocol and response metadata",
            "IDs, roles, names, phases, or summaries in the local event stream.",
        )
    if entry_type == "turn_context":
        return (
            "turn_context_metadata",
            "Turn context metadata",
            "Local turn configuration such as cwd, model, effort, date, and timezone.",
        )
    return (
        "other_serialized_metadata",
        "Other serialized metadata",
        "Additional local JSONL fields not separately categorized.",
    )
