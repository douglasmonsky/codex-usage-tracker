"""Evaluate normalized hypotheses against local usage evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
    _count_confidence,
)
from codex_usage_tracker.reports.discovery import (
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.reports.hypothesis_limit_evaluators import (
    _evaluate_allowance_hypothesis,
    _evaluate_effort_model_hypothesis,
)
from codex_usage_tracker.reports.hypothesis_results import (
    _hypothesis_large_low_output,
    _hypothesis_result,
    _merge_evidence_summaries,
    _next_tool,
    _row_has_cache_failure_signal,
)
from codex_usage_tracker.reports.query import build_recommendations_report


def evaluate_hypothesis_spec(
    spec: dict[str, str],
    *,
    context: dict[str, Any],
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    family = spec["family"]
    if family == "cache_failure":
        result = _evaluate_cache_failure_hypothesis(
            context,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=evidence_limit,
            privacy_mode=privacy_mode,
        )
    elif family == "repeated_file_rediscovery":
        result = _evaluate_repeated_file_hypothesis(
            context,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=evidence_limit,
            privacy_mode=privacy_mode,
        )
    elif family == "shell_churn":
        result = _evaluate_shell_churn_hypothesis(
            context,
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=evidence_limit,
            privacy_mode=privacy_mode,
        )
    elif family == "effort_model_choice":
        result = _evaluate_effort_model_hypothesis(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
        )
    elif family == "allowance_change":
        result = _evaluate_allowance_hypothesis(
            db_path=db_path,
            allowance_path=allowance_path,
            include_archived=include_archived,
        )
    else:
        result = _evaluate_token_waste_hypothesis(
            context,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=evidence_limit,
            privacy_mode=privacy_mode,
        )

    return {
        "id": spec["id"],
        "hypothesis": spec["hypothesis"],
        "family": family,
        **result,
    }


def _evaluate_token_waste_hypothesis(
    context: dict[str, Any],
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    large = _hypothesis_large_low_output(
        context,
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    )
    recommendations = build_recommendations_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload
    large_count = int(large["total_candidates"])
    recommendation_count = len(recommendations.get("rows", []))
    if large_count:
        status = "true"
        confidence = _count_confidence(large_count)
    elif recommendation_count:
        status = "partially_true"
        confidence = "low"
    else:
        status = "false"
        confidence = "low"
    return _hypothesis_result(
        status=status,
        confidence=confidence,
        i_would_like_to_be_able_to="Find obvious token-waste candidates without reading raw conversations.",
        i_will_accomplish_this_using="Rank large low-output calls and aggregate recommendation rows.",
        i_am_missing_access_to="Whether each expensive call produced valuable work or was intentionally exploratory.",
        evidence_summary=_merge_evidence_summaries(
            _agentic_evidence_summary(large.get("rows", [])),
            {
                "recommendation_count": recommendation_count,
                "large_low_output_candidate_count": large_count,
            },
        ),
        evidence=[
            _compact_agentic_evidence_row(row) for row in large.get("rows", [])[:evidence_limit]
        ],
        counter_evidence=(
            []
            if large_count
            else ["No large low-output calls crossed the default threshold in the selected scope."]
        ),
        next_action="Inspect the largest low-output rows, then verify whether a shorter handoff or smaller context would have avoided them.",
        recommended_next_tools=[
            _next_tool(
                "usage_large_low_output_calls", "Inspect the highest-token low-output calls."
            ),
            _next_tool("usage_recommendations", "Compare aggregate recommendation scoring."),
            _next_tool("usage_calls", "Open the underlying aggregate call rows."),
        ],
    )


def _evaluate_cache_failure_hypothesis(
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
    large = _hypothesis_large_low_output(
        context,
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    )
    rows = large.get("rows", [])
    signal_rows = [row for row in rows if _row_has_cache_failure_signal(row)]
    if signal_rows:
        status = "true"
        confidence = _count_confidence(len(signal_rows))
    elif rows:
        status = "partially_true"
        confidence = "low"
    else:
        status = "false"
        confidence = "low"
    return _hypothesis_result(
        status=status,
        confidence=confidence,
        i_would_like_to_be_able_to="Tell whether cache misses, cold resumes, or context pressure explain expensive calls.",
        i_will_accomplish_this_using="Look for large low-output calls with low cache ratios, high context-window use, or cache/context explanations.",
        i_am_missing_access_to="The exact task intent and raw turn context unless the user explicitly enables raw context inspection.",
        evidence_summary=_agentic_evidence_summary(signal_rows or rows),
        evidence=[
            _compact_agentic_evidence_row(row) for row in (signal_rows or rows)[:evidence_limit]
        ],
        counter_evidence=(
            []
            if signal_rows
            else ["No selected large low-output row had a direct cache/context signal."]
        ),
        next_action="Verify the candidate rows in Call Investigator and compare nearby thread traces before changing workflow.",
        recommended_next_tools=[
            _next_tool(
                "usage_large_low_output_calls", "Check cache ratio and context-window percent."
            ),
            _next_tool("usage_call_detail", "Inspect one aggregate call in Call Investigator."),
            _next_tool(
                "usage_thread_trace",
                "Trace local indexed thread activity if deeper context is needed.",
            ),
        ],
    )


def _evaluate_repeated_file_hypothesis(
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
    report = context.get("repeated_file_rediscovery")
    if report is None:
        report = build_repeated_file_rediscovery_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=2,
            limit=evidence_limit,
            privacy_mode=privacy_mode,
        ).payload
        context["repeated_file_rediscovery"] = report
    rows = report.get("rows", [])
    total = int(report["total_candidates"])
    status = "true" if total >= 3 else "partially_true" if total else "false"
    return _hypothesis_result(
        status=status,
        confidence=_count_confidence(total) if total else "low",
        i_would_like_to_be_able_to="Find repeated file rediscovery without exposing full local paths.",
        i_will_accomplish_this_using="Rank safe path hashes, basenames, extensions, operation mixes, and associated token totals.",
        i_am_missing_access_to="Whether each reread was necessary for task correctness without task-level intent.",
        evidence_summary=_agentic_evidence_summary(rows),
        evidence=[_compact_agentic_evidence_row(row) for row in rows[:evidence_limit]],
        counter_evidence=[]
        if total
        else ["No repeated file rediscovery candidates crossed the threshold."],
        next_action="Turn recurring lookups into a durable project note, helper command, or narrower read path.",
        recommended_next_tools=[
            _next_tool("usage_repeated_file_rediscovery", "Rank repeated safe file identities."),
            _next_tool(
                "usage_thread_trace", "Check whether the same thread repeats the rediscovery loop."
            ),
        ],
    )


def _evaluate_shell_churn_hypothesis(
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
    report = context.get("shell_churn")
    if report is None:
        report = build_shell_churn_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=2,
            limit=evidence_limit,
            sample_limit=3,
            privacy_mode=privacy_mode,
        ).payload
        context["shell_churn"] = report
    rows = report.get("rows", [])
    total = int(report["total_candidates"])
    unknown_count = sum(
        1 for row in rows if str(row.get("command_root") or "").startswith("unknown")
    )
    status = "true" if total >= 3 else "partially_true" if total else "false"
    counter_evidence = []
    if unknown_count:
        counter_evidence.append(
            "Some shell rows still have cloudy command labels; normalization needs more hardening."
        )
    if not total:
        counter_evidence.append("No repeated shell churn candidates crossed the threshold.")
    return _hypothesis_result(
        status=status,
        confidence=_count_confidence(total) if total else "low",
        i_would_like_to_be_able_to="Detect repeated command probing without storing raw command output.",
        i_will_accomplish_this_using="Rank command roots, bounded labels, occurrence counts, failures, and associated token totals.",
        i_am_missing_access_to="Full raw command arguments and the developer's intent for each probe.",
        evidence_summary=_merge_evidence_summaries(
            _agentic_evidence_summary(rows),
            {"unknown_command_row_count": unknown_count},
        ),
        evidence=[_compact_agentic_evidence_row(row) for row in rows[:evidence_limit]],
        counter_evidence=counter_evidence,
        next_action="If the same command family repeats, replace exploratory loops with a helper command, test selector, or saved project note.",
        recommended_next_tools=[
            _next_tool("usage_shell_churn", "Inspect repeated shell command families."),
            _next_tool("usage_thread_trace", "Trace whether command churn clusters in one thread."),
        ],
    )
