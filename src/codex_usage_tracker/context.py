"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store import query_usage_record

DEFAULT_CONTEXT_CHARS = 20_000
DEFAULT_CONTEXT_ENTRIES = 80

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"github" r"_pat_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bA(?:KI|SI)A[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (
        re.compile(r"(?i)\baws_secret_access_key\s*[:=]\s*(['\"]?)[A-Za-z0-9/+=]{30,}\1"),
        "aws_secret_access_key=[REDACTED_AWS_SECRET]",
    ),
    (
        re.compile(r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._~+/-]+=*"),
        "Authorization: Bearer [REDACTED_BEARER_TOKEN]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer [REDACTED_BEARER_TOKEN]"),
    (
        re.compile(r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"(?i)\b([A-Z0-9_ -]*(?:password|api[_-]?key|token|secret|credential|private[_-]?key)[A-Z0-9_ -]*)\s*[:=]\s*"
            r"(['\"]?)[^'\"\s,;}]+\2"
        ),
        r"\1=[REDACTED_SECRET]",
    ),
)

_OUTPUT_OMITTED = (
    "Tool output omitted by default. Reload with include_tool_output=true to inspect "
    "redacted, size-limited output."
)


def load_call_context(
    record_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
) -> dict[str, Any]:
    """Load logged turn context for one model call from the source JSONL file.

    This intentionally reads raw transcript-like data only on demand. The returned
    context is not written back to SQLite or embedded in dashboard HTML.
    """

    row = query_usage_record(db_path=db_path, record_id=record_id)
    if row is None:
        raise ValueError(f"No usage record found for record_id: {record_id}")

    source_file = Path(str(row.get("source_file") or ""))
    if not source_file.exists():
        raise FileNotFoundError(f"Source log not found: {source_file}")

    line_number = _positive_int(row.get("line_number"))
    if line_number is None:
        raise ValueError(f"Usage record has no valid source line: {record_id}")

    target_turn_id = _optional_str(row.get("turn_id"))
    entries, omitted = _read_context_entries(
        path=source_file,
        token_line=line_number,
        target_turn_id=target_turn_id,
        max_chars=max(1_000, max_chars),
        max_entries=max(1, max_entries),
        include_tool_output=include_tool_output,
    )
    return {
        "schema": "codex-usage-tracker-context-v1",
        "loaded_on_demand": True,
        "raw_context_persisted": False,
        "include_tool_output": include_tool_output,
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


def _read_context_entries(
    path: Path,
    token_line: int,
    target_turn_id: str | None,
    max_chars: int,
    max_entries: int,
    include_tool_output: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    omitted_parse_errors = 0
    current_turn_id: str | None = None
    collecting = target_turn_id is None

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
                current_turn_id = _optional_str(payload.get("turn_id"))
                collecting = target_turn_id is None or current_turn_id == target_turn_id
                if collecting:
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
                continue

            if not collecting:
                continue

            summarized = _summarize_payload(
                entry_type=entry_type,
                payload=payload,
                include_tool_output=include_tool_output,
            )
            if summarized is not None:
                candidates.append(
                    _context_entry(
                        line_number,
                        timestamp,
                        entry_type,
                        summarized["label"],
                        summarized["text"],
                    )
                )

            if (
                line_number >= token_line
                and entry_type == "event_msg"
                and payload.get("type") == "token_count"
            ):
                break

    limited, omitted = _limit_entries(candidates, max_chars=max_chars, max_entries=max_entries)
    omitted["parse_errors"] = omitted_parse_errors
    omitted["target_turn_id"] = target_turn_id
    return limited, omitted


def _summarize_payload(
    entry_type: str,
    payload: dict[str, Any],
    include_tool_output: bool,
) -> dict[str, str] | None:
    if entry_type == "response_item":
        return _summarize_response_item(payload, include_tool_output=include_tool_output)
    if entry_type == "event_msg":
        return _summarize_event_msg(payload, include_tool_output=include_tool_output)
    if entry_type == "compacted":
        message = _optional_str(payload.get("message")) or "Compaction event"
        return {"label": "Compaction", "text": message}
    return None


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
) -> dict[str, str] | None:
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
        return {
            "label": label,
            "text": output if include_tool_output else _OUTPUT_OMITTED,
        }

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
) -> dict[str, str] | None:
    event_type = _optional_str(payload.get("type")) or "event_msg"
    if event_type == "token_count":
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        return {"label": "Token count", "text": _jsonish(_token_count_summary(info))}

    if "message" in payload:
        return {"label": event_type, "text": _optional_str(payload.get("message")) or ""}

    output_fields = [field for field in ("stdout", "stderr", "result") if field in payload]
    if output_fields:
        if not include_tool_output:
            return {"label": event_type, "text": _OUTPUT_OMITTED}
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
        "last_token_usage": info.get("last_token_usage"),
        "total_token_usage": info.get("total_token_usage"),
        "model_context_window": info.get("model_context_window"),
    }


def _context_entry(
    line_number: int,
    timestamp: str | None,
    entry_type: str,
    label: str,
    text: str,
) -> dict[str, Any]:
    return {
        "line_number": line_number,
        "timestamp": timestamp,
        "type": entry_type,
        "label": label,
        "text": _redact(text),
        "truncated": False,
    }


def _limit_entries(
    entries: list[dict[str, Any]],
    max_chars: int,
    max_entries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limited_reversed: list[dict[str, Any]] = []
    remaining = max_chars
    omitted_entries = 0
    omitted_chars = 0
    selected = entries[-max_entries:]

    for entry in reversed(selected):
        text = str(entry.get("text") or "")
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
        "older_entries": max(0, len(entries) - max_entries),
        "over_budget_entries": omitted_entries,
        "over_budget_chars": omitted_chars,
        "max_chars": max_chars,
        "max_entries": max_entries,
        "returned_entries": len(limited),
    }


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
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
