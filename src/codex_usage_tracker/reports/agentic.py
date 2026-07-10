"""Goal-led investigation suggestions and agentic findings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
    _count_confidence,
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


AGENTIC_INVESTIGATION_GOALS = (
    "overview",
    "token_waste",
    "allowance_change",
    "cache_failure",
    "workflow_churn",
)


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


def _normalize_agentic_goal(goal: str | None) -> str | None:
    if goal is None:
        return None
    normalized = goal.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "waste": "token_waste",
        "token": "token_waste",
        "tokens": "token_waste",
        "usage_waste": "token_waste",
        "limits": "allowance_change",
        "limit_change": "allowance_change",
        "allowance": "allowance_change",
        "usage_limit": "allowance_change",
        "cache": "cache_failure",
        "caching": "cache_failure",
        "churn": "workflow_churn",
        "workflow": "workflow_churn",
        "summary": "overview",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in AGENTIC_INVESTIGATION_GOALS:
        return normalized
    return None


def _investigation_suggestions(goal: str | None) -> list[dict[str, Any]]:
    suggestions = [
        {
            "goal": "token_waste",
            "label": "Find obvious token-waste candidates",
            "why_it_matters": "Combines large low-output calls, shell churn, repeated file rediscovery, and recommendation scores.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "token_waste", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_large_low_output_calls",
                "usage_shell_churn",
                "usage_repeated_file_rediscovery",
                "usage_calls",
            ],
            "privacy_notes": "Aggregate-first; no raw prompts, tool output, or full paths.",
        },
        {
            "goal": "allowance_change",
            "label": "Check whether weekly allowance behavior changed",
            "why_it_matters": "Separates weekly evidence from noisy 5-hour rolling-window behavior.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "allowance_change", "privacy_mode": "strict"},
            "follow_up_tools": ["usage_allowance_diagnostics", "usage_allowance_export"],
            "privacy_notes": "Use strict privacy for shareable evidence bundles.",
        },
        {
            "goal": "cache_failure",
            "label": "Find cache misses and high-context continuations",
            "why_it_matters": "Low cache ratio and high context-window use often explain avoidable usage spikes.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "cache_failure", "evidence_limit": 5},
            "follow_up_tools": ["usage_large_low_output_calls", "usage_calls", "usage_call_detail"],
            "privacy_notes": "Aggregate token/cache fields only.",
        },
        {
            "goal": "workflow_churn",
            "label": "Find repeated shell and file rediscovery loops",
            "why_it_matters": "Repeated probes, command failures, and rereads suggest automation or documentation opportunities.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "workflow_churn", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_shell_churn",
                "usage_repeated_file_rediscovery",
                "usage_thread_trace",
            ],
            "privacy_notes": "Uses safe command labels and path identities, not raw command output or full paths.",
        },
        {
            "goal": "overview",
            "label": "Summarize current usage drivers",
            "why_it_matters": "Starts with index freshness, thread/model/project summaries, and existing recommendation cards.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "overview", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_status",
                "usage_summary",
                "usage_report_pack",
                "usage_recommendations",
            ],
            "privacy_notes": "Aggregate dashboard/report-pack evidence.",
        },
    ]
    if goal is None:
        return suggestions
    related_goals = {
        "overview": [
            "overview",
            "token_waste",
            "cache_failure",
            "workflow_churn",
            "allowance_change",
        ],
        "token_waste": ["token_waste", "cache_failure", "workflow_churn", "overview"],
        "cache_failure": ["cache_failure", "token_waste", "overview"],
        "workflow_churn": ["workflow_churn", "token_waste", "cache_failure", "overview"],
        "allowance_change": ["allowance_change", "overview", "token_waste"],
    }.get(goal, [goal])
    by_goal = {row["goal"]: row for row in suggestions}
    return [by_goal[row_goal] for row_goal in related_goals if row_goal in by_goal] or suggestions


def _normalize_agentic_detail_mode(detail_mode: str | None) -> str:
    normalized = (detail_mode or "compact").strip().lower().replace("-", "_")
    if normalized in {"full", "verbose", "raw", "rows"}:
        return "full"
    return "compact"


def _agentic_finding(
    *,
    finding: str,
    evidence: list[dict[str, Any]],
    detail_mode: str,
    confidence: str,
    why_it_matters: str,
    recommended_action: str,
    verify_with: list[str],
    privacy_notes: str,
    missing_access: str,
) -> dict[str, Any]:
    evidence_rows = (
        evidence
        if detail_mode == "full"
        else [_compact_agentic_evidence_row(row) for row in evidence]
    )
    return {
        "finding": finding,
        "evidence_count": len(evidence),
        "evidence_summary": _agentic_evidence_summary(evidence),
        "evidence": evidence_rows,
        "confidence": confidence,
        "why_it_matters": why_it_matters,
        "recommended_action": recommended_action,
        "verify_with": verify_with,
        "missing_access": missing_access,
        "privacy_notes": privacy_notes,
    }


def _overall_agentic_confidence(findings: list[dict[str, Any]]) -> str:
    priorities = {
        "high": 4,
        "medium": 3,
        "low": 2,
        "insufficient_local_evidence": 1,
    }
    if not findings:
        return "insufficient_local_evidence"
    return max(
        (str(row.get("confidence") or "") for row in findings),
        key=lambda value: priorities.get(value, 0),
    )


def _goal_next_tools(goal: str) -> list[dict[str, Any]]:
    mapping: dict[str, list[dict[str, Any]]] = {
        "token_waste": [
            {
                "tool": "usage_report_pack",
                "reason": "Inspect dashboard-shaped evidence rows for top aggregate drivers.",
                "default_arguments": {"evidence_limit": 10},
            },
            {
                "tool": "usage_calls",
                "reason": "Open high-token rows and sort/filter the underlying call table.",
                "default_arguments": {"sort": "tokens", "direction": "desc", "limit": 20},
            },
        ],
        "allowance_change": [
            {
                "tool": "usage_allowance_diagnostics",
                "reason": "Compare observed usage movement against estimated local credits.",
                "default_arguments": {"window_kind": "weekly", "privacy_mode": "strict"},
            }
        ],
        "cache_failure": [
            {
                "tool": "usage_calls",
                "reason": "Filter high context-window and low-cache calls.",
                "default_arguments": {"sort": "tokens", "direction": "desc", "limit": 20},
            }
        ],
        "workflow_churn": [
            {
                "tool": "usage_shell_churn",
                "reason": "Inspect repeated command families and failure/retry patterns.",
                "default_arguments": {"min_occurrences": 3, "limit": 20},
            }
        ],
        "overview": [
            {"tool": "usage_status", "reason": "Check index freshness.", "default_arguments": {}}
        ],
    }
    return mapping.get(goal, [])


def _dedupe_next_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("tool") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(tool)
    return deduped
