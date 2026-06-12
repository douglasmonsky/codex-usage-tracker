"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

import json
from functools import lru_cache
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.redaction import redact_secrets
from codex_usage_tracker.store import query_usage_record

DEFAULT_CONTEXT_CHARS = 20_000
DEFAULT_CONTEXT_ENTRIES = 80

_OUTPUT_OMITTED = (
    "Tool output hidden for this request. Reload with include_tool_output=true to inspect "
    "redacted, size-limited output."
)


def load_call_context(
    record_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
    include_compaction_history: bool = False,
    diagnostics: bool = False,
) -> dict[str, Any]:
    """Load logged turn context for one model call from the source JSONL file.

    This intentionally reads raw transcript-like data only on demand. The returned
    context is not written back to SQLite or embedded in dashboard HTML.
    """

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

    line_number = _positive_int(row.get("line_number"))
    if line_number is None:
        raise ValueError(f"Usage record has no valid source line: {record_id}")

    target_turn_id = _optional_str(row.get("turn_id"))
    source_scan_started = perf_counter()
    entries, omitted, estimate_entries, serialized_estimate, serialized_estimate_ms = (
        _read_context_entries(
            path=source_file,
            token_line=line_number,
            target_turn_id=target_turn_id,
            max_chars=max_chars if max_chars <= 0 else max(1_000, max_chars),
            max_entries=max_entries if max_entries <= 0 else max(1, max_entries),
            include_tool_output=include_tool_output,
            include_compaction_history=include_compaction_history,
            model=_optional_str(row.get("model")),
        )
    )
    source_scan_ms = _elapsed_ms(source_scan_started)
    if diagnostic_payload is not None:
        diagnostic_payload["source_scan_ms"] = source_scan_ms
    visible_estimate = _estimate_visible_tokens(estimate_entries, _optional_str(row.get("model")))
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
        "include_tool_output": include_tool_output,
        "include_compaction_history": include_compaction_history,
        "visible_char_count": visible_estimate["visible_char_count"],
        "visible_token_estimate": visible_estimate["visible_token_estimate"],
        "visible_token_estimator": visible_estimate["visible_token_estimator"],
        "serialized_evidence": serialized_estimate,
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
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any], float]:
    candidates: list[dict[str, Any]] = []
    raw_entries: list[dict[str, Any]] = []
    field_buckets: dict[str, dict[str, Any]] = {}
    omitted_parse_errors = 0
    current_turn_id: str | None = None
    collecting = target_turn_id is None
    pending_compactions: list[dict[str, Any]] = []
    encoding, estimator = _context_encoding(model or "")

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
            entry_type = _optional_str(envelope.get("type")) or "unknown"
            payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
            timestamp = _optional_str(envelope.get("timestamp"))

            if entry_type == "turn_context":
                was_collecting = collecting
                current_turn_id = _optional_str(payload.get("turn_id"))
                collecting = target_turn_id is None or current_turn_id == target_turn_id
                if collecting:
                    raw_entries = []
                    field_buckets = {}
                    _collect_serialized_envelope(
                        raw_entries=raw_entries,
                        field_buckets=field_buckets,
                        envelope=envelope,
                        entry_type=entry_type,
                        payload=payload,
                        encoding=encoding,
                    )
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
                    candidates.extend(carried_compactions)
                pending_compactions = []
                continue

            if collecting:
                _collect_serialized_envelope(
                    raw_entries=raw_entries,
                    field_buckets=field_buckets,
                    envelope=envelope,
                    entry_type=entry_type,
                    payload=payload,
                    encoding=encoding,
                )

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
    serialized_estimate = _serialized_context_estimate(
        raw_entries=raw_entries,
        field_buckets=field_buckets,
        parse_errors=omitted_parse_errors,
        encoding=encoding,
        estimator=estimator,
    )
    serialized_estimate_ms = _elapsed_ms(serialized_started)
    candidates = _dedupe_chat_message_echoes(candidates)
    limited, omitted = _limit_entries(candidates, max_chars=max_chars, max_entries=max_entries)
    omitted["parse_errors"] = omitted_parse_errors
    omitted["target_turn_id"] = target_turn_id
    omitted["total_entries"] = len(candidates)
    return limited, omitted, candidates, serialized_estimate, serialized_estimate_ms


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
    raw_json = "\n".join(_compact_json(_redact_json_value(entry)) for entry in raw_entries)
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
        "raw_json_token_estimate": _token_estimate(raw_json, encoding),
        "token_estimator": estimator,
        "parse_errors": parse_errors,
        "upper_bound": True,
        "raw_text_returned": False,
        "buckets": top_buckets,
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
    label = _optional_str(entry.get("label")) or ""
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
    return (_optional_str(entry.get("label")) or "") in {"message / user", "message / assistant"}


def _summarize_payload(
    entry_type: str,
    payload: dict[str, Any],
    include_tool_output: bool,
    include_compaction_history: bool,
) -> dict[str, Any] | None:
    if entry_type == "response_item":
        return _summarize_response_item(payload, include_tool_output=include_tool_output)
    if _optional_str(payload.get("type")) == "context_compacted":
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
    message = _optional_str(payload.get("message")) or ""
    compaction: dict[str, Any] = {
        "replacement_history_available": bool(replacement_entries),
        "replacement_entry_count": len(replacement_entries),
        "replacement_history_included": include_compaction_history and bool(replacement_entries),
        "classification": "confirmed_compaction",
    }
    if message:
        text = _redact(message)
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
            "text": _redact(_jsonish(item)),
        }
    item_type = _optional_str(item.get("type")) or "replacement item"
    role = _optional_str(item.get("role"))
    name = _optional_str(item.get("name"))
    label_bits = [item_type]
    if role:
        label_bits.append(role)
    if name:
        label_bits.append(name)
    text = _content_text(item.get("content")) or _jsonish(
        {key: value for key, value in item.items() if key not in {"content"}}
    )
    return {
        "label": " / ".join(label_bits),
        "role": role,
        "type": item_type,
        "text": _redact(text),
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
    summary = _optional_str(payload.get("summary"))
    if summary:
        lines.append(f"summary: {summary}")
    return "\n".join(lines) if lines else "Turn context"


def _summarize_response_item(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    item_type = _optional_str(payload.get("type")) or "response_item"
    role = _optional_str(payload.get("role"))
    name = _optional_str(payload.get("name"))
    label_bits = [item_type]
    if role:
        label_bits.append(role)
    if name:
        label_bits.append(name)
    label = " / ".join(label_bits)

    content_text = _content_text(payload.get("content"))
    if content_text:
        return {"label": label, "text": content_text}

    if "arguments" in payload:
        return {
            "label": label,
            "text": f"Tool call arguments:\n{_jsonish(payload.get('arguments'))}",
        }

    if "input" in payload:
        return {
            "label": label,
            "text": f"Tool input:\n{_jsonish(payload.get('input'))}",
        }

    if "output" in payload:
        output = _optional_str(payload.get("output")) or _jsonish(payload.get("output"))
        if include_tool_output:
            return {"label": label, "text": output}
        return {"label": label, "text": _OUTPUT_OMITTED, "tool_output_omitted": True}

    summary = _content_text(payload.get("summary"))
    if summary:
        return {"label": label, "text": summary}

    action = payload.get("action")
    if isinstance(action, dict):
        return {"label": label, "text": f"Action:\n{_jsonish(action)}"}

    return None


def _summarize_event_msg(
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, Any] | None:
    event_type = _optional_str(payload.get("type")) or "event_msg"
    if event_type == "token_count":
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        token_usage = _token_count_summary(info)
        return {
            "label": "Token count",
            "text": _jsonish(token_usage),
            "token_usage": token_usage,
        }

    if "message" in payload:
        return {"label": event_type, "text": _optional_str(payload.get("message")) or ""}

    output_fields = [field for field in ("stdout", "stderr", "result") if field in payload]
    if output_fields:
        if not include_tool_output:
            return {"label": event_type, "text": _OUTPUT_OMITTED, "tool_output_omitted": True}
        text = "\n".join(f"{field}:\n{_jsonish(payload.get(field))}" for field in output_fields)
        return {"label": event_type, "text": text}

    compact = {
        key: payload.get(key)
        for key in ("call_id", "turn_id", "phase", "status", "duration_ms")
        if key in payload
    }
    return {"label": event_type, "text": _jsonish(compact)} if compact else None


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
    input_tokens = _nonnegative_int(usage.get("input_tokens"))
    cached_input_tokens = _nonnegative_int(usage.get("cached_input_tokens"))
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
) -> dict[str, Any]:
    entry = {
        "line_number": line_number,
        "timestamp": timestamp,
        "type": entry_type,
        "label": label,
        "text": _redact(text),
        "truncated": False,
    }
    if tool_output_omitted:
        entry["tool_output_omitted"] = True
    if token_usage:
        entry["token_usage"] = token_usage
    if compaction:
        entry["compaction"] = compaction
    return entry


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


def _estimate_visible_tokens(entries: list[dict[str, Any]], model: str | None) -> dict[str, Any]:
    text = "\n\n".join(str(entry.get("text") or "") for entry in entries if entry.get("text"))
    visible_chars = len(text)
    encoding, estimator = _context_encoding(model or "")
    visible_tokens = _token_estimate(text, encoding)
    if encoding is None:
        visible_tokens = ceil(visible_chars / 4) if visible_chars else 0
    return {
        "visible_char_count": visible_chars,
        "visible_token_estimate": visible_tokens,
        "visible_token_estimator": estimator,
    }


def _collect_serialized_field_buckets(
    *,
    buckets: dict[str, dict[str, Any]],
    entry_type: str,
    payload: dict[str, Any],
    encoding: Any | None,
) -> None:
    payload_type = _optional_str(payload.get("type")) or ""
    for key, value in payload.items():
        if key == "type":
            continue
        bucket_key, label, note = _serialized_bucket_label(entry_type, payload_type, key)
        rendered = _compact_json({key: _redact_json_value(value)})
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
        stats["token_estimate"] = int(stats["token_estimate"]) + _token_estimate(rendered, encoding)


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


def _token_estimate(text: str, encoding: Any | None) -> int:
    if not text:
        return 0
    if encoding is None:
        return ceil(len(text) / 4)
    return len(encoding.encode(text))


def _redact_json_value(value: object) -> object:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json_value(item) for key, item in value.items()}
    return value


def _compact_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(value)


@lru_cache(maxsize=32)
def _context_encoding(model: str) -> tuple[Any | None, str]:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except Exception:
        return None, "chars_per_4_fallback"

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        try:
            encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                return None, "chars_per_4_fallback"
    except Exception:
        return None, "chars_per_4_fallback"
    return encoding, f"tiktoken:{getattr(encoding, 'name', 'unknown')}"


def _content_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        pieces: list[str] = []
        for item in value:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    pieces.append(text)
        return "\n".join(piece for piece in pieces if piece)
    return _jsonish(value)


def _jsonish(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
    except TypeError:
        return str(value)


def _redact(text: str) -> str:
    return redact_secrets(text)


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _nonnegative_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
