"""Serialized raw JSONL evidence estimates for selected context turns."""

from __future__ import annotations

from math import ceil
from typing import Any

from codex_usage_tracker.context_token_estimates import token_estimate
from codex_usage_tracker.context_values import compact_json, optional_str, redact_json_value

_VISIBLE_PAYLOAD_FIELDS = {"content", "message", "output", "arguments", "input"}
_PROTOCOL_METADATA_FIELDS = {
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
}
_OTHER_BUCKET = (
    "other_serialized_metadata",
    "Other serialized metadata",
    "Additional local JSONL fields not separately categorized.",
)


def collect_serialized_envelope(
    *,
    raw_entries: list[dict[str, Any]],
    field_buckets: dict[str, dict[str, Any]],
    envelope: dict[str, Any],
    entry_type: str,
    payload: dict[str, Any],
    encoding: Any | None,
) -> None:
    """Record one raw envelope and account for its serializable field buckets."""
    raw_entries.append(envelope)
    _collect_serialized_field_buckets(
        buckets=field_buckets,
        entry_type=entry_type,
        payload=payload,
        encoding=encoding,
    )


def serialized_context_estimate(
    *,
    raw_entries: list[dict[str, Any]],
    field_buckets: dict[str, dict[str, Any]],
    parse_errors: int,
    encoding: Any | None,
    estimator: str,
) -> dict[str, Any]:
    """Build the full serialized raw JSONL upper-bound estimate."""
    raw_json = "\n".join(compact_json(redact_json_value(entry)) for entry in raw_entries)
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
        "buckets": _top_serialized_buckets(field_buckets),
        "deferred": False,
        "deferred_buckets": False,
    }


def quick_serialized_context_estimate(
    *,
    raw_line_count: int,
    raw_json_char_count: int,
    parse_errors: int,
) -> dict[str, Any]:
    """Build the quick serialized estimate without per-field bucket analysis."""
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


def _top_serialized_buckets(field_buckets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        field_buckets.values(),
        key=lambda bucket: int(bucket.get("token_estimate") or 0),
        reverse=True,
    )[:8]


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
        _add_serialized_field_bucket(
            buckets=buckets,
            entry_type=entry_type,
            payload_type=payload_type,
            key=key,
            value=value,
            encoding=encoding,
        )


def _add_serialized_field_bucket(
    *,
    buckets: dict[str, dict[str, Any]],
    entry_type: str,
    payload_type: str,
    key: str,
    value: object,
    encoding: Any | None,
) -> None:
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
    special = _special_serialized_bucket(entry_type, payload_type, key)
    if special is not None:
        return special
    if key in _VISIBLE_PAYLOAD_FIELDS:
        return (
            "visible_payload_fields",
            "Visible message/tool payload fields",
            "Raw JSON representation of content already summarized in evidence.",
        )
    if key in _PROTOCOL_METADATA_FIELDS:
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
    return _OTHER_BUCKET


def _special_serialized_bucket(
    entry_type: str,
    payload_type: str,
    key: str,
) -> tuple[str, str, str] | None:
    if entry_type == "response_item" and key == "encrypted_content":
        return (
            "encrypted_reasoning_state",
            "Encrypted reasoning/state payload",
            "Opaque local payload; counted as serialized evidence, not readable text.",
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
    return None
