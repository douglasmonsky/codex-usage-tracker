"""Derived per-call initiator metadata for aggregate dashboard rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CallOriginFlags:
    """Metadata-only signals observed before one token_count callback."""

    user_message: bool = False
    compaction: bool = False
    tool_result: bool = False
    codex_activity: bool = False

    @property
    def has_signal(self) -> bool:
        return (
            self.user_message
            or self.compaction
            or self.tool_result
            or self.codex_activity
        )


def event_flags_from_envelope(envelope: object) -> CallOriginFlags:
    """Return categorical call-origin flags without reading raw text fields."""

    if not isinstance(envelope, dict):
        return CallOriginFlags()
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
    return CallOriginFlags(
        user_message=user_message,
        compaction=compaction,
        tool_result=tool_result,
        codex_activity=codex_activity,
    )


def classify_call_origin(segment: Iterable[CallOriginFlags]) -> dict[str, str]:
    """Classify who most likely initiated a model call from metadata-only signals."""

    flags = list(segment)
    if any(event.user_message for event in flags):
        return _origin("user", "user_message", "high")
    if any(event.compaction for event in flags):
        return _origin("codex", "post_compaction", "high")
    if any(event.tool_result for event in flags):
        return _origin("codex", "tool_result", "high")
    if any(event.codex_activity for event in flags):
        return _origin("codex", "agent_continuation", "medium")
    return _origin("unknown", "no_signal", "low")


def fallback_call_origin(row: Mapping[str, Any]) -> dict[str, str]:
    """Return cheap categorical origin for migrated rows missing persisted metadata."""

    if (
        row.get("model") == "codex-auto-review"
        or row.get("thread_source") == "subagent"
        or row.get("subagent_type")
        or row.get("parent_session_id")
    ):
        return _origin("codex", "thread_source", "medium")
    return _origin("unknown", "missing_origin", "low")


def ensure_call_origin(row: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a row and fill missing persisted origin fields without source-log reads."""

    copied = dict(row)
    if (
        isinstance(copied.get("call_initiator"), str)
        and copied["call_initiator"]
        and isinstance(copied.get("call_initiator_reason"), str)
        and copied["call_initiator_reason"]
        and isinstance(copied.get("call_initiator_confidence"), str)
        and copied["call_initiator_confidence"]
    ):
        return copied
    copied.update(fallback_call_origin(copied))
    return copied


def _origin(initiator: str, reason: str, confidence: str) -> dict[str, str]:
    return {
        "call_initiator": initiator,
        "call_initiator_reason": reason,
        "call_initiator_confidence": confidence,
    }
