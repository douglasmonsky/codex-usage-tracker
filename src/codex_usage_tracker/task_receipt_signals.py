"""Aggregate-only task receipt signal classification."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from codex_usage_tracker.models import TaskReceiptSignal

RECEIPT_CATEGORY_PATCH_APPLIED = "patch_applied"
RECEIPT_CATEGORY_TOOL_ACTIVITY = "tool_activity"
RECEIPT_CATEGORY_TASK_COMPLETE = "task_complete"
RECEIPT_CATEGORY_UNKNOWN = "unknown"

EVIDENCE_SCOPE_BETWEEN_CALLS = "between_calls"

CONFIDENCE_ORDER = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


def task_receipt_signal_from_envelope(
    envelope: object,
    *,
    line_number: int,
) -> TaskReceiptSignal | None:
    """Return a receipt signal from one JSONL envelope without reading raw content fields."""

    if not isinstance(envelope, dict):
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    entry_type = envelope.get("type")
    payload_type = payload.get("type")
    timestamp = _optional_str(envelope.get("timestamp"))

    if entry_type == "event_msg" and payload_type == "patch_apply_end":
        return _signal(
            category=RECEIPT_CATEGORY_PATCH_APPLIED,
            confidence="high",
            timestamp=timestamp,
            line_number=line_number,
            reason="patch_apply_end",
        )
    if entry_type == "event_msg" and payload_type == "task_complete":
        return _signal(
            category=RECEIPT_CATEGORY_TASK_COMPLETE,
            confidence="high",
            timestamp=timestamp,
            line_number=line_number,
            reason="task_complete",
        )
    if entry_type == "event_msg" and payload_type in {
        "mcp_tool_call_end",
        "image_generation_end",
        "web_search_end",
    }:
        return _signal(
            category=RECEIPT_CATEGORY_TOOL_ACTIVITY,
            confidence="medium",
            timestamp=timestamp,
            line_number=line_number,
            reason=str(payload_type),
        )
    if entry_type == "response_item" and payload_type in {
        "function_call_output",
        "tool_search_output",
    }:
        return _signal(
            category=RECEIPT_CATEGORY_TOOL_ACTIVITY,
            confidence="medium",
            timestamp=timestamp,
            line_number=line_number,
            reason=str(payload_type),
        )
    if entry_type == "response_item" and payload_type in {
        "function_call",
        "tool_search_call",
    }:
        return _signal(
            category=RECEIPT_CATEGORY_TOOL_ACTIVITY,
            confidence="low",
            timestamp=timestamp,
            line_number=line_number,
            reason=str(payload_type),
        )
    return None


def task_receipt_signal_to_json(signal: TaskReceiptSignal) -> dict[str, Any]:
    """Encode a receipt signal for parser-state persistence."""

    return asdict(signal)


def task_receipt_signal_from_json(value: object) -> TaskReceiptSignal | None:
    """Decode a parser-state receipt signal, preserving metadata only."""

    if not isinstance(value, dict):
        return None
    category = _optional_str(value.get("category"))
    confidence = _optional_str(value.get("confidence"))
    event_count = _positive_int(value.get("event_count"))
    if not category or not confidence or event_count is None:
        return None
    return TaskReceiptSignal(
        category=category,
        confidence=confidence,
        event_count=event_count,
        first_event_timestamp=_optional_str(value.get("first_event_timestamp")),
        last_event_timestamp=_optional_str(value.get("last_event_timestamp")),
        first_source_line=_positive_int(value.get("first_source_line")),
        last_source_line=_positive_int(value.get("last_source_line")),
        evidence_scope=_optional_str(value.get("evidence_scope")) or EVIDENCE_SCOPE_BETWEEN_CALLS,
        reason=_optional_str(value.get("reason")),
    )


def strongest_confidence(values: list[str]) -> str:
    """Return the strongest confidence label in a stable order."""

    if not values:
        return "unknown"
    return max(values, key=lambda value: CONFIDENCE_ORDER.get(value, 0))


def _signal(
    *,
    category: str,
    confidence: str,
    timestamp: str | None,
    line_number: int,
    reason: str,
) -> TaskReceiptSignal:
    return TaskReceiptSignal(
        category=category,
        confidence=confidence,
        event_count=1,
        first_event_timestamp=timestamp,
        last_event_timestamp=timestamp,
        first_source_line=line_number,
        last_source_line=line_number,
        evidence_scope=EVIDENCE_SCOPE_BETWEEN_CALLS,
        reason=reason,
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
