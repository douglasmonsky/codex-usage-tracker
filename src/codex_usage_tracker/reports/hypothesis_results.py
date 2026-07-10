"""Shared hypothesis result and metric helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.reports.discovery import build_large_low_output_report


def _hypothesis_large_low_output(
    context: dict[str, Any],
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    report = context.get("large_low_output")
    if report is None:
        report = build_large_low_output_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            limit=evidence_limit,
            privacy_mode=privacy_mode,
        ).payload
        context["large_low_output"] = report
    return report


def _hypothesis_result(
    *,
    status: str,
    confidence: str,
    i_would_like_to_be_able_to: str,
    i_will_accomplish_this_using: str,
    i_am_missing_access_to: str,
    evidence_summary: dict[str, Any],
    evidence: list[dict[str, Any]],
    counter_evidence: list[str],
    next_action: str,
    recommended_next_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "confidence": confidence,
        "i_would_like_to_be_able_to": i_would_like_to_be_able_to,
        "i_will_accomplish_this_using": i_will_accomplish_this_using,
        "i_am_missing_access_to": i_am_missing_access_to,
        "evidence_summary": evidence_summary,
        "evidence": evidence,
        "counter_evidence": counter_evidence,
        "next_action": next_action,
        "recommended_next_tools": recommended_next_tools,
    }


def _row_has_cache_failure_signal(row: dict[str, Any]) -> bool:
    cache_ratio = _optional_number(row.get("cache_ratio"))
    context_window = _optional_number(row.get("context_window_percent"))
    explanation = " ".join(
        str(value)
        for value in (
            row.get("candidate_explanation"),
            row.get("explanation_reasons"),
            row.get("primary_signal"),
            row.get("secondary_signals"),
        )
        if value is not None
    ).lower()
    return (
        (cache_ratio is not None and cache_ratio < 0.25)
        or (context_window is not None and context_window >= 80)
        or any(term in explanation for term in ("cache", "cold", "resume", "context"))
    )


def _merge_evidence_summaries(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    return {**base, **extra}


def _next_tool(
    tool: str, reason: str, default_arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "tool": tool,
        "reason": reason,
        "default_arguments": default_arguments or {},
    }


def _number(value: Any) -> float:
    return _optional_number(value) or 0.0


def _optional_number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _token_totals_by(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        totals[key] = totals.get(key, 0.0) + _number(row.get("total_tokens"))
    return totals


def _top_token_totals(totals: dict[str, float], *, limit: int = 5) -> list[dict[str, Any]]:
    return [
        {"label": label, "total_tokens": int(value)}
        for label, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]
