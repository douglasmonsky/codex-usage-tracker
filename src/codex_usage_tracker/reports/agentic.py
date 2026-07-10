"""Goal-led investigation suggestions and agentic findings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.reports.agentic_evidence import (
    _count_confidence,
)
from codex_usage_tracker.reports.agentic_strategy import (
    AGENTIC_INVESTIGATION_GOALS,
    _agentic_finding,
    _dedupe_next_tools,
    _goal_next_tools,
    _investigation_suggestions,
    _normalize_agentic_detail_mode,
    _normalize_agentic_goal,
    _overall_agentic_confidence,
)
from codex_usage_tracker.reports.discovery import (
    build_large_low_output_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.reports.query import build_recommendations_report


@dataclass(frozen=True)
class InvestigationSuggestionsReport:
    """Stable machine-readable agentic investigation suggestions."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class AgenticInvestigationReport:
    """Stable machine-readable agentic investigation report."""

    payload: dict[str, Any]


def build_investigation_suggestions_report(
    *,
    goal: str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 10,
    privacy_mode: str = "normal",
) -> InvestigationSuggestionsReport:
    """Build intent-led MCP investigation suggestions."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_goal = _normalize_agentic_goal(goal)
    suggestions = _investigation_suggestions(normalized_goal)
    normalized_limit = None if limit is None or limit <= 0 else limit
    limited = suggestions if normalized_limit is None else suggestions[:normalized_limit]
    return InvestigationSuggestionsReport(
        {
            "schema": "codex-usage-tracker-investigation-suggestions-v1",
            "content_mode": "aggregate_guidance",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "goal": normalized_goal,
            "available_goals": list(AGENTIC_INVESTIGATION_GOALS),
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "limit": limit,
            },
            "summary": {
                "suggestion_count": len(limited),
                "total_suggestions": len(suggestions),
                "top_goal": limited[0]["goal"] if limited else None,
            },
            "suggestions": limited,
        }
    )


def build_agentic_investigation_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    detail_mode: str = "compact",
    privacy_mode: str = "normal",
) -> AgenticInvestigationReport:
    """Build a compact goal-led investigation using existing reports."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_goal = _normalize_agentic_goal(goal) or "token_waste"
    normalized_limit = max(1, evidence_limit)
    normalized_detail_mode = _normalize_agentic_detail_mode(detail_mode)
    findings: list[dict[str, Any]] = []
    source_reports: list[str] = []
    recommended_next_tools: list[dict[str, Any]] = []
    caveats = [
        "Local Codex logs only; this is not an official OpenAI usage ledger.",
        "Archived sessions are excluded unless include_archived is true.",
    ]

    if normalized_goal in {"token_waste", "cache_failure", "workflow_churn"}:
        large_low_output = build_large_low_output_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            privacy_mode=privacy_mode,
        ).payload
        source_reports.append(str(large_low_output["schema"]))
        if large_low_output["rows"]:
            findings.append(
                _agentic_finding(
                    finding="Large calls produced little output",
                    evidence=large_low_output["rows"][:normalized_limit],
                    detail_mode=normalized_detail_mode,
                    confidence=_count_confidence(int(large_low_output["total_candidates"])),
                    why_it_matters=(
                        "Large input/context usage with low output is a strong candidate for "
                        "cold resumes, stale thread continuation, or low-value continuation."
                    ),
                    recommended_action=(
                        "Open the top calls, check whether a smaller fresh thread or preserved handoff "
                        "would avoid resending large context."
                    ),
                    verify_with=[
                        "usage_large_low_output_calls",
                        "usage_call_detail",
                        "usage_thread_trace",
                    ],
                    privacy_notes="Aggregate token/activity counts only; no raw fragments or command output.",
                    missing_access=(
                        "The aggregate report cannot prove why output was low without a thread trace "
                        "or explicit raw-context inspection."
                    ),
                )
            )

    if normalized_goal in {"token_waste", "workflow_churn"}:
        shell_churn = build_shell_churn_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            privacy_mode=privacy_mode,
        ).payload
        source_reports.append(str(shell_churn["schema"]))
        if shell_churn["rows"]:
            findings.append(
                _agentic_finding(
                    finding="Repeated shell command churn",
                    evidence=shell_churn["rows"][:normalized_limit],
                    detail_mode=normalized_detail_mode,
                    confidence=_count_confidence(int(shell_churn["total_candidates"])),
                    why_it_matters=(
                        "Repeated shell roots, failures, or adjacent retries can waste turns and "
                        "inflate tool-output/context pressure."
                    ),
                    recommended_action=(
                        "Turn repeated probes into a small script, narrower command, or targeted test command."
                    ),
                    verify_with=["usage_shell_churn", "usage_thread_trace"],
                    privacy_notes="Command roots and bounded labels only; raw command output is omitted.",
                    missing_access=(
                        "Strict aggregate evidence cannot always recover the exact shell intent "
                        "or full command arguments."
                    ),
                )
            )

        repeated_files = build_repeated_file_rediscovery_report(
            db_path=db_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            privacy_mode=privacy_mode,
        ).payload
        source_reports.append(str(repeated_files["schema"]))
        if repeated_files["rows"]:
            findings.append(
                _agentic_finding(
                    finding="Repeated file rediscovery",
                    evidence=repeated_files["rows"][:normalized_limit],
                    detail_mode=normalized_detail_mode,
                    confidence=_count_confidence(int(repeated_files["total_candidates"])),
                    why_it_matters=(
                        "Repeated safe file identities can indicate the agent keeps rediscovering "
                        "the same context instead of using a durable summary or targeted helper."
                    ),
                    recommended_action=(
                        "Summarize stable facts into project docs or build a small helper command for recurring lookups."
                    ),
                    verify_with=["usage_repeated_file_rediscovery", "usage_thread_trace"],
                    privacy_notes="Safe path hashes, basenames, and aggregates only; full paths are omitted.",
                    missing_access=(
                        "The report can rank repeated safe file identities, but cannot tell whether "
                        "each reread was necessary without task intent."
                    ),
                )
            )

    if normalized_goal in {"overview", "token_waste", "cache_failure"}:
        recommendations = build_recommendations_report(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            privacy_mode=privacy_mode,
        ).payload
        source_reports.append(str(recommendations["schema"]))
        if recommendations["rows"]:
            findings.append(
                _agentic_finding(
                    finding="Ranked aggregate usage recommendations",
                    evidence=recommendations["rows"][:normalized_limit],
                    detail_mode=normalized_detail_mode,
                    confidence="medium",
                    why_it_matters="Existing recommendation scoring combines aggregate cost, cache, context, and pricing signals.",
                    recommended_action="Start with the highest recommendation score, then verify with the specific diagnostic tool.",
                    verify_with=["usage_recommendations", "usage_calls", "usage_call_detail"],
                    privacy_notes="Aggregate recommendations only; no prompt or tool-output text.",
                    missing_access=(
                        "Recommendation scores do not know whether an expensive call produced high-value work."
                    ),
                )
            )

    if normalized_goal == "allowance_change":
        recommended_next_tools.extend(
            [
                {
                    "tool": "usage_allowance_diagnostics",
                    "reason": "Run weekly evidence-graded allowance diagnostics before interpreting 5-hour noise.",
                    "default_arguments": {"window_kind": "weekly", "privacy_mode": "strict"},
                },
                {
                    "tool": "usage_allowance_export",
                    "reason": "Create strict local evidence bundle when the user wants to share allowance-change evidence.",
                    "default_arguments": {"window_kind": "weekly"},
                },
            ]
        )
        caveats.append(
            "Weekly allowance evidence is the primary signal; 5-hour counters are rolling-window context."
        )

    if normalized_goal == "overview":
        recommended_next_tools.extend(
            [
                {
                    "tool": "usage_status",
                    "reason": "Confirm index freshness and row counts.",
                    "default_arguments": {},
                },
                {
                    "tool": "usage_summary",
                    "reason": "Rank projects, threads, models, or dates depending on the user's next question.",
                    "default_arguments": {
                        "group_by": "thread",
                        "limit": 10,
                        "response_format": "json",
                    },
                },
                {
                    "tool": "usage_report_pack",
                    "reason": "Open dashboard-shaped evidence cards for top aggregate drivers.",
                    "default_arguments": {"evidence_limit": normalized_limit},
                },
            ]
        )

    if not findings and normalized_goal != "allowance_change":
        findings.append(
            _agentic_finding(
                finding="No strong local signal at default thresholds",
                evidence=[],
                detail_mode=normalized_detail_mode,
                confidence="insufficient_local_evidence",
                why_it_matters="The current aggregate diagnostics did not find a clear candidate at the default threshold.",
                recommended_action="Lower thresholds, widen the time window, include archived sessions, or inspect top aggregate calls.",
                verify_with=["usage_calls", "usage_report_pack", "usage_investigation_walk"],
                privacy_notes="No raw context needed for this follow-up.",
                missing_access="No supported aggregate signal was found at the selected thresholds.",
            )
        )

    recommended_next_tools.extend(_goal_next_tools(normalized_goal))
    payload = {
        "schema": "codex-usage-tracker-agentic-investigation-v1",
        "content_mode": "aggregate_investigation",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "goal": normalized_goal,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": normalized_limit,
            "detail_mode": normalized_detail_mode,
        },
        "summary": {
            "finding_count": len(findings),
            "top_finding": findings[0]["finding"] if findings else None,
            "confidence": _overall_agentic_confidence(findings),
            "source_reports": source_reports,
        },
        "findings": findings,
        "recommended_next_tools": _dedupe_next_tools(recommended_next_tools),
        "caveats": caveats,
    }
    return AgenticInvestigationReport(payload)
