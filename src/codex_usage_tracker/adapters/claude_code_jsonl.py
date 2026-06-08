"""Parse Claude Code local JSONL history into aggregate usage records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.models import SessionInfo, UsageEvent

CLAUDE_CODE_ADAPTER_VERSION = "claude-code-jsonl-v1"
CLAUDE_CODE_DIAGNOSTIC_KEYS = (
    "invalid_json",
    "unknown_event_shape",
    "missing_usage",
    "invalid_integer",
    "duplicate_record",
    "skipped_events",
)


@dataclass(frozen=True)
class ClaudeCodeJsonlAdapter:
    source_provider: str = "anthropic"
    source_app: str = "claude-code"
    source_format: str = CLAUDE_CODE_ADAPTER_VERSION

    def discover_logs(self, root: Path, *, include_archived: bool = False) -> list[Path]:
        del include_archived
        return sorted(path for path in (root / "projects").glob("**/*.jsonl") if path.is_file())

    def load_session_index(self, root: Path) -> dict[str, SessionInfo]:
        del root
        return {}

    def parse_file(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        del session_index
        events: list[UsageEvent] = []
        seen: set[str] = set()
        cumulative = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError:
                    _increment_stat(stats, "invalid_json")
                    continue
                if not isinstance(envelope, dict):
                    _increment_stat(stats, "unknown_event_shape")
                    continue
                message = _message_payload(envelope)
                if message is None:
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    _increment_stat(stats, "missing_usage")
                    _increment_stat(stats, "skipped_events")
                    continue
                try:
                    event = _build_event(path, line_number, envelope, message, usage, cumulative)
                except ValueError:
                    _increment_stat(stats, "invalid_integer")
                    _increment_stat(stats, "skipped_events")
                    continue
                if event.record_id in seen:
                    _increment_stat(stats, "duplicate_record")
                    continue
                seen.add(event.record_id)
                events.append(event)
        return events


def compact_claude_diagnostics(stats: MutableMapping[str, int]) -> dict[str, int]:
    return {
        key: int(stats.get(key, 0))
        for key in CLAUDE_CODE_DIAGNOSTIC_KEYS
        if stats.get(key, 0)
    }


def _message_payload(envelope: dict[str, Any]) -> dict[str, Any] | None:
    message = envelope.get("message")
    if isinstance(message, dict) and message.get("role") == "assistant":
        return message
    if envelope.get("type") == "assistant" and isinstance(message, dict):
        return message
    if envelope.get("role") == "assistant":
        return envelope
    return None


def _build_event(
    path: Path,
    line_number: int,
    envelope: dict[str, Any],
    message: dict[str, Any],
    usage: dict[str, Any],
    cumulative: dict[str, int],
) -> UsageEvent:
    normal_input = _usage_int(usage, "input_tokens")
    cache_creation = _usage_int(usage, "cache_creation_input_tokens", default=0)
    cache_read = _usage_int(usage, "cache_read_input_tokens", default=0)
    output_tokens = _usage_int(usage, "output_tokens")
    reasoning_output = _usage_int(usage, "thinking_tokens", default=0)
    input_tokens = normal_input + cache_creation + cache_read
    total_tokens = input_tokens + output_tokens
    cumulative["input_tokens"] += input_tokens
    cumulative["cached_input_tokens"] += cache_read
    cumulative["cache_creation_input_tokens"] += cache_creation
    cumulative["output_tokens"] += output_tokens
    cumulative["reasoning_output_tokens"] += reasoning_output
    cumulative["total_tokens"] += total_tokens
    session_id = (
        _optional_str(envelope.get("sessionId"))
        or _optional_str(envelope.get("session_id"))
        or path.stem
    )
    request_id = _optional_str(message.get("id")) or _optional_str(envelope.get("uuid"))
    event_timestamp = _optional_str(envelope.get("timestamp")) or ""
    record_id = _record_id(session_id, request_id, event_timestamp, line_number)
    return UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=_optional_str(envelope.get("summary")),
        session_updated_at=None,
        event_timestamp=event_timestamp,
        source_file=str(path),
        line_number=line_number,
        source_provider="anthropic",
        source_app="claude-code",
        source_format=CLAUDE_CODE_ADAPTER_VERSION,
        provider_request_id=request_id,
        turn_id=_optional_str(envelope.get("uuid")) or request_id,
        turn_timestamp=event_timestamp or None,
        cwd=_optional_str(envelope.get("cwd")),
        model=_optional_str(message.get("model")),
        effort=None,
        current_date=None,
        timezone=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=None,
        cache_creation_input_tokens=cache_creation,
        input_tokens=input_tokens,
        cached_input_tokens=cache_read,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output,
        total_tokens=total_tokens,
        cumulative_input_tokens=cumulative["input_tokens"],
        cumulative_cached_input_tokens=cumulative["cached_input_tokens"],
        cumulative_output_tokens=cumulative["output_tokens"],
        cumulative_reasoning_output_tokens=cumulative["reasoning_output_tokens"],
        cumulative_total_tokens=cumulative["total_tokens"],
    )


def _record_id(session_id: str, request_id: str | None, timestamp: str, line_number: int) -> str:
    raw = "|".join(["claude-code", session_id, request_id or "", timestamp, str(line_number)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _usage_int(values: dict[str, Any], key: str, *, default: int | None = None) -> int:
    if key not in values or values.get(key) is None:
        if default is not None:
            return default
        raise ValueError(f"missing usage field: {key}")
    return _strict_int(values.get(key))


def _strict_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid integer value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    raise ValueError(f"invalid integer value: {value!r}")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _increment_stat(stats: MutableMapping[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1
