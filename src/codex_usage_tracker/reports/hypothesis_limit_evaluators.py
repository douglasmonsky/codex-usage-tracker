"""Evaluate model-effort and allowance-change hypotheses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance_intelligence import build_allowance_diagnostics_report
from codex_usage_tracker.reports.hypothesis_results import (
    _hypothesis_result,
    _next_tool,
    _number,
    _token_totals_by,
    _top_token_totals,
)
from codex_usage_tracker.store.api import query_dashboard_events


def _evaluate_effort_model_hypothesis(
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
) -> dict[str, Any]:
    rows = query_dashboard_events(
        db_path,
        limit=0,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    total_tokens, high_effort_ratio, effort_totals = _effort_token_share(rows)
    model_totals = _token_totals_by(rows, "model")
    status, confidence = _effort_hypothesis_outcome(
        row_count=len(rows),
        total_tokens=total_tokens,
        high_effort_ratio=high_effort_ratio,
    )
    return _hypothesis_result(
        status=status,
        confidence=confidence,
        i_would_like_to_be_able_to="Tell whether model or effort selection materially drives usage.",
        i_will_accomplish_this_using="Aggregate selected calls by effort and model, then compare high-effort token share.",
        i_am_missing_access_to="Whether high effort was required for the task quality target.",
        evidence_summary={
            "row_count": len(rows),
            "total_tokens": int(total_tokens),
            "high_effort_token_ratio": round(high_effort_ratio, 6),
            "top_efforts": _top_token_totals(effort_totals),
            "top_models": _top_token_totals(model_totals),
        },
        evidence=[],
        counter_evidence=_effort_counter_evidence(high_effort_ratio),
        next_action="Compare high-effort calls against task type, then use lower effort for routine edits and reserve higher effort for uncertain design work.",
        recommended_next_tools=[
            _next_tool("usage_summary", "Summarize usage by model or effort."),
            _next_tool("usage_calls", "Filter calls by effort and inspect outliers."),
            _next_tool(
                "usage_recommendations", "Compare effort choices with aggregate recommendations."
            ),
        ],
    )


def _effort_token_share(
    rows: list[dict[str, Any]],
) -> tuple[float, float, dict[str, float]]:
    total_tokens = sum(_number(row.get("total_tokens")) for row in rows)
    effort_totals = _token_totals_by(rows, "effort")
    high_effort_tokens = sum(
        value
        for effort, value in effort_totals.items()
        if effort.lower() in {"high", "xhigh", "maximum"}
    )
    ratio = high_effort_tokens / total_tokens if total_tokens else 0.0
    return total_tokens, ratio, effort_totals


def _effort_hypothesis_outcome(
    *,
    row_count: int,
    total_tokens: float,
    high_effort_ratio: float,
) -> tuple[str, str]:
    if not row_count or not total_tokens:
        return "insufficient_evidence", "insufficient_local_evidence"
    if high_effort_ratio >= 0.5:
        return "true", "medium"
    if high_effort_ratio >= 0.2:
        return "partially_true", "low"
    return "false", "low"


def _effort_counter_evidence(high_effort_ratio: float) -> list[str]:
    if high_effort_ratio:
        return []
    return ["No high-effort token share found in the selected scope."]


def _evaluate_allowance_hypothesis(
    *,
    db_path: Path,
    allowance_path: Path,
    include_archived: bool,
) -> dict[str, Any]:

    diagnostics = build_allowance_diagnostics_report(
        db_path=db_path,
        allowance_path=allowance_path,
        include_archived=include_archived,
        window_kind="weekly",
        limit=1000,
        privacy_mode="strict",
    ).payload
    summary = diagnostics.get("summary", {})
    grade = str(summary.get("primary_evidence_grade") or "insufficient_data")
    if grade in {"strong_local_evidence"}:
        status = "true"
        confidence = "high"
    elif grade in {"possible_regime_change"}:
        status = "partially_true"
        confidence = "medium"
    elif grade in {"counter_noise_likely"}:
        status = "false"
        confidence = "medium"
    else:
        status = "insufficient_evidence"
        confidence = "insufficient_local_evidence"
    return _hypothesis_result(
        status=status,
        confidence=confidence,
        i_would_like_to_be_able_to="Distinguish real weekly allowance movement from rolling-window noise.",
        i_will_accomplish_this_using="Read weekly allowance diagnostics and evidence grades from observed usage snapshots.",
        i_am_missing_access_to="OpenAI's official internal ledger and usage from other surfaces sharing the same allowance.",
        evidence_summary={
            "primary_evidence_grade": grade,
            "observation_count": summary.get("observation_count"),
            "weekly_observation_count": summary.get("weekly_observation_count"),
            "candidate_change_count": summary.get("candidate_change_count"),
            "research_readiness": summary.get("research_readiness"),
        },
        evidence=[],
        counter_evidence=[
            "Outside usage and missing observations can explain observed movement unless weekly evidence is strong."
        ],
        next_action="Run full weekly allowance diagnostics and export strict evidence before making any public claim.",
        recommended_next_tools=[
            _next_tool(
                "usage_allowance_diagnostics", "Run evidence-graded weekly allowance diagnostics."
            ),
            _next_tool(
                "usage_allowance_export", "Create a strict local evidence bundle for sharing."
            ),
        ],
    )
