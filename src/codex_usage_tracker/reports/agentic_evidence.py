"""Compact and summarize aggregate evidence for agentic reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

_COMPACT_EVIDENCE_FIELDS = (
    "record_id",
    "session_id",
    "thread_key",
    "thread_name",
    "event_timestamp",
    "model",
    "effort",
    "total_tokens",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "cache_ratio",
    "context_window_percent",
    "candidate_explanation",
    "explanation_reasons",
    "command_root",
    "command_label",
    "command_family",
    "churn_kind",
    "occurrences",
    "call_count",
    "thread_count",
    "session_count",
    "failure_count",
    "path_hash",
    "path_identity",
    "path_basename",
    "path_extension",
    "candidate_kind",
    "operation_mix",
    "recommendation",
    "primary_signal",
    "secondary_signals",
    "recommended_action",
    "usage_credits",
    "estimated_cost_usd",
    "next_tool",
)
_PRIMARY_RECOMMENDATION_FIELDS = ("key", "severity", "title", "action")
_NEARBY_ACTIVITY_FIELDS = (
    "tool_call_count",
    "command_run_count",
    "failed_command_count",
    "file_event_count",
)
_TRACE_HANDLE_FIELDS = (
    "thread_key",
    "thread",
    "session_id",
    "call_count",
    "total_tokens",
    "next_tool",
)
_SUMMARY_TOTAL_FIELDS = (
    ("occurrences", "total_occurrences"),
    ("call_count", "total_call_count"),
    ("failure_count", "total_failure_count"),
)


def _compact_agentic_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    compact = _non_null_fields(row, _COMPACT_EVIDENCE_FIELDS)
    _set_optional(
        compact,
        "primary_recommendation",
        _compact_mapping(row.get("primary_recommendation"), _PRIMARY_RECOMMENDATION_FIELDS),
    )
    _set_optional(
        compact,
        "nearby_activity",
        _compact_mapping(row.get("nearby_activity"), _NEARBY_ACTIVITY_FIELDS),
    )
    _set_optional(compact, "trace_handles", _compact_trace_handles(row.get("trace_handles")))
    return compact


def _agentic_evidence_summary(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    token_values = _numeric_values(evidence, "total_tokens")
    summary: dict[str, Any] = {
        "row_count": len(evidence),
        "total_tokens": sum(token_values),
        "max_total_tokens": max(token_values) if token_values else None,
        "threads": _ordered_text_values(evidence, "thread_name", "thread", "thread_key")[:5],
        "models": _ordered_text_values(evidence, "model")[:5],
        "efforts": _ordered_text_values(evidence, "effort")[:5],
        "candidate_explanations": _ordered_text_values(evidence, "candidate_explanation")[:5],
        "recommendations": _ordered_text_values(evidence, "recommendation", "recommended_action")[
            :5
        ],
    }
    summary.update(_timestamp_bounds(evidence))
    summary.update(_optional_numeric_totals(evidence))
    return {key: value for key, value in summary.items() if value not in (None, [], {})}


def _non_null_fields(source: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {key: source[key] for key in fields if key in source and source[key] is not None}


def _compact_mapping(value: object, fields: Iterable[str]) -> dict[str, Any] | None:
    return _non_null_fields(value, fields) if isinstance(value, dict) else None


def _compact_trace_handles(value: object) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    return [
        _non_null_fields(handle, _TRACE_HANDLE_FIELDS)
        for handle in value[:3]
        if isinstance(handle, dict)
    ]


def _set_optional(target: dict[str, Any], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value


def _numeric_values(rows: list[dict[str, Any]], field: str) -> list[int]:
    return [int(row[field]) for row in rows if isinstance(row.get(field), int | float)]


def _first_text(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    value = next((row.get(field) for field in fields if row.get(field)), "")
    return str(value)


def _ordered_text_values(rows: list[dict[str, Any]], *fields: str) -> list[str]:
    return _ordered_unique(_first_text(row, fields) for row in rows)


def _timestamp_bounds(rows: list[dict[str, Any]]) -> dict[str, str]:
    timestamps = _ordered_text_values(rows, "event_timestamp")
    if not timestamps:
        return {}
    return {
        "first_event_timestamp": min(timestamps),
        "last_event_timestamp": max(timestamps),
    }


def _optional_numeric_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for source_field, result_field in _SUMMARY_TOTAL_FIELDS:
        values = _numeric_values(rows, source_field)
        if values:
            totals[result_field] = sum(values)
    return totals


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value == "None" or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _count_confidence(count: int) -> str:
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    if count == 1:
        return "low"
    return "insufficient_local_evidence"
