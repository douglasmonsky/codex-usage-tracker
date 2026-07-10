"""Compact and summarize aggregate evidence for agentic reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _compact_agentic_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    keep_fields = (
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
    compact = {key: row[key] for key in keep_fields if key in row and row[key] is not None}
    if "primary_recommendation" in row and isinstance(row["primary_recommendation"], dict):
        primary = row["primary_recommendation"]
        compact["primary_recommendation"] = {
            key: primary[key]
            for key in ("key", "severity", "title", "action")
            if key in primary and primary[key] is not None
        }
    if "nearby_activity" in row and isinstance(row["nearby_activity"], dict):
        compact["nearby_activity"] = {
            key: row["nearby_activity"].get(key)
            for key in (
                "tool_call_count",
                "command_run_count",
                "failed_command_count",
                "file_event_count",
            )
            if row["nearby_activity"].get(key) is not None
        }
    if "trace_handles" in row and isinstance(row["trace_handles"], list):
        compact["trace_handles"] = [
            {
                key: handle.get(key)
                for key in (
                    "thread_key",
                    "thread",
                    "session_id",
                    "call_count",
                    "total_tokens",
                    "next_tool",
                )
                if isinstance(handle, dict) and handle.get(key) is not None
            }
            for handle in row["trace_handles"][:3]
            if isinstance(handle, dict)
        ]
    return compact


def _agentic_evidence_summary(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    token_values = [
        int(row["total_tokens"])
        for row in evidence
        if isinstance(row.get("total_tokens"), int | float)
    ]
    timestamps = [str(row["event_timestamp"]) for row in evidence if row.get("event_timestamp")]
    threads = _ordered_unique(
        str(row.get("thread_name") or row.get("thread") or row.get("thread_key"))
        for row in evidence
    )
    models = _ordered_unique(str(row.get("model")) for row in evidence if row.get("model"))
    efforts = _ordered_unique(str(row.get("effort")) for row in evidence if row.get("effort"))
    explanations = _ordered_unique(
        str(row.get("candidate_explanation"))
        for row in evidence
        if row.get("candidate_explanation")
    )
    recommendations = _ordered_unique(
        str(row.get("recommendation") or row.get("recommended_action"))
        for row in evidence
        if row.get("recommendation") or row.get("recommended_action")
    )
    summary: dict[str, Any] = {
        "row_count": len(evidence),
        "total_tokens": sum(token_values),
        "max_total_tokens": max(token_values) if token_values else None,
        "threads": threads[:5],
        "models": models[:5],
        "efforts": efforts[:5],
        "candidate_explanations": explanations[:5],
        "recommendations": recommendations[:5],
    }
    if timestamps:
        summary["first_event_timestamp"] = min(timestamps)
        summary["last_event_timestamp"] = max(timestamps)
    occurrence_values = [
        int(row["occurrences"])
        for row in evidence
        if isinstance(row.get("occurrences"), int | float)
    ]
    call_count_values = [
        int(row["call_count"]) for row in evidence if isinstance(row.get("call_count"), int | float)
    ]
    failure_values = [
        int(row["failure_count"])
        for row in evidence
        if isinstance(row.get("failure_count"), int | float)
    ]
    if occurrence_values:
        summary["total_occurrences"] = sum(occurrence_values)
    if call_count_values:
        summary["total_call_count"] = sum(call_count_values)
    if failure_values:
        summary["total_failure_count"] = sum(failure_values)
    return {key: value for key, value in summary.items() if value not in (None, [], {})}


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
