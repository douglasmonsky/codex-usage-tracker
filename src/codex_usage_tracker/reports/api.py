"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.formatting import (
    format_calls,
    format_summary,
)
from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import (
    apply_project_privacy_to_rows,
    apply_project_privacy_to_summary_rows,
    validate_privacy_mode,
)
from codex_usage_tracker.pricing.api import (
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
    _count_confidence,
)
from codex_usage_tracker.reports.discovery import (
    ContentSearchReport as ContentSearchReport,
)
from codex_usage_tracker.reports.discovery import (
    LargeLowOutputReport as LargeLowOutputReport,
)
from codex_usage_tracker.reports.discovery import (
    PatternScanReport as PatternScanReport,
)
from codex_usage_tracker.reports.discovery import (
    PricingCoverageReport as PricingCoverageReport,
)
from codex_usage_tracker.reports.discovery import (
    RepeatedFileRediscoveryReport as RepeatedFileRediscoveryReport,
)
from codex_usage_tracker.reports.discovery import (
    ShellChurnReport as ShellChurnReport,
)
from codex_usage_tracker.reports.discovery import (
    SourceCoverageReport as SourceCoverageReport,
)
from codex_usage_tracker.reports.discovery import (
    ThreadTraceReport as ThreadTraceReport,
)
from codex_usage_tracker.reports.discovery import (
    build_content_search_report as build_content_search_report,
)
from codex_usage_tracker.reports.discovery import (
    build_large_low_output_report as build_large_low_output_report,
)
from codex_usage_tracker.reports.discovery import (
    build_pattern_scan_report as build_pattern_scan_report,
)
from codex_usage_tracker.reports.discovery import (
    build_pricing_coverage_report as build_pricing_coverage_report,
)
from codex_usage_tracker.reports.discovery import (
    build_repeated_file_rediscovery_report as build_repeated_file_rediscovery_report,
)
from codex_usage_tracker.reports.discovery import (
    build_shell_churn_report as build_shell_churn_report,
)
from codex_usage_tracker.reports.discovery import (
    build_source_coverage_report as build_source_coverage_report,
)
from codex_usage_tracker.reports.discovery import (
    build_thread_trace_report as build_thread_trace_report,
)
from codex_usage_tracker.reports.hypothesis_classification import (
    classify_hypothesis_family as _classify_hypothesis_family,
)
from codex_usage_tracker.reports.hypothesis_classification import (
    normalize_hypothesis_inputs as _normalize_hypothesis_inputs,
)
from codex_usage_tracker.reports.hypothesis_evaluators import (
    evaluate_hypothesis_spec as _evaluate_hypothesis_spec,
)
from codex_usage_tracker.reports.project_summary import project_summary_rows
from codex_usage_tracker.reports.query import (
    QUERY_CREDIT_CONFIDENCE_CHOICES as QUERY_CREDIT_CONFIDENCE_CHOICES,
)
from codex_usage_tracker.reports.query import (
    QUERY_PRICING_STATUS_CHOICES as QUERY_PRICING_STATUS_CHOICES,
)
from codex_usage_tracker.reports.query import (
    QueryReport as QueryReport,
)
from codex_usage_tracker.reports.query import (
    RecommendationsReport as RecommendationsReport,
)
from codex_usage_tracker.reports.query import (
    build_query_report as build_query_report,
)
from codex_usage_tracker.reports.query import (
    build_recommendations_report as build_recommendations_report,
)
from codex_usage_tracker.reports.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store.api import (
    query_large_low_output_calls,
    query_most_expensive_calls,
    query_pattern_scan,
    query_summary,
    record_investigation_run,
)

SUMMARY_GROUP_BY_CHOICES = (
    "date",
    "model",
    "effort",
    "cwd",
    "project",
    "project_tag",
    "thread",
    "session",
    "thread_source",
    "subagent_type",
    "agent_role",
    "parent_session",
    "parent_thread",
)
SUMMARY_PRESET_CHOICES = (
    "today",
    "last-7-days",
    "by-model",
    "by-cwd",
    "by-project",
    "by-project-tag",
    "by-thread",
    "by-subagent-role",
    "by-subagent-type",
    "expensive",
)
EXPENSIVE_PRESET_CHOICES = ("today", "last-7-days")
_SUMMARY_PRESET_GROUPS = {
    "by-model": "model",
    "by-cwd": "cwd",
    "by-project": "project",
    "by-project-tag": "project_tag",
    "by-thread": "thread",
    "by-subagent-role": "agent_role",
    "by-subagent-type": "subagent_type",
}


@dataclass(frozen=True)
class SummaryReport:
    """Resolved aggregate usage summary for one display surface."""

    rows: list[dict[str, Any]]
    group_by: str
    is_expensive: bool = False
    privacy_mode: str = "normal"

    def render(self) -> str:
        if self.is_expensive:
            return format_calls(self.rows)
        return format_summary(self.rows, self.group_by)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "codex-usage-tracker-summary-v1",
            "group_by": self.group_by,
            "is_expensive": self.is_expensive,
            "privacy_mode": self.privacy_mode,
            "row_count": len(self.rows),
            "rows": self.rows,
        }


@dataclass(frozen=True)
class InvestigationSuggestionsReport:
    """Stable machine-readable agentic investigation suggestions."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class AgenticInvestigationReport:
    """Stable machine-readable agentic investigation report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ActionBriefReport:
    """Stable machine-readable aggregate action brief."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class HypothesisTestReport:
    """Stable machine-readable agentic hypothesis test report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class InvestigationWalkReport:
    """Stable machine-readable local investigation walk."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class LocalEvidenceExportReport:
    """Stable shareable local evidence export without raw/indexed content."""

    payload: dict[str, Any]


def resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    """Resolve summary presets into a group and since filter."""

    return _SUMMARY_PRESET_GROUPS.get(preset or "", group_by), resolve_since(preset, since)


def resolve_since(preset: str | None, since: str | None) -> str | None:
    """Resolve date presets into an ISO date string."""

    if since:
        return since
    if preset == "today":
        return date.today().isoformat()
    if preset == "last-7-days":
        return (date.today() - timedelta(days=6)).isoformat()
    return None


def build_summary_report(
    *,
    db_path: Path,
    pricing_path: Path,
    group_by: str = "thread",
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
) -> SummaryReport:
    """Build a usage summary or expensive-call preset from aggregate rows."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    resolved_group_by, since_filter = resolve_summary_options(group_by, preset, since)
    pricing = load_pricing_config(pricing_path)
    if preset == "expensive":
        rows = query_most_expensive_calls(db_path, limit=limit, since=since_filter)
        return SummaryReport(
            rows=apply_project_privacy_to_rows(
                annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
                privacy_mode=privacy_mode,
            ),
            group_by=resolved_group_by,
            is_expensive=True,
            privacy_mode=privacy_mode,
        )

    if resolved_group_by in {"project", "project_tag"}:
        rows = project_summary_rows(
            db_path=db_path,
            pricing=pricing,
            group_by=resolved_group_by,
            limit=limit,
            since=since_filter,
            projects_path=projects_path,
            privacy_mode=privacy_mode,
        )
        return SummaryReport(rows=rows, group_by=resolved_group_by, privacy_mode=privacy_mode)

    rows = query_summary(
        db_path,
        group_by=resolved_group_by,
        limit=limit,
        since=since_filter,
    )
    if resolved_group_by == "model":
        rows = annotate_rows_with_efficiency(rows, pricing, model_field="group_key")
    rows = apply_project_privacy_to_summary_rows(
        rows, group_by=resolved_group_by, privacy_mode=privacy_mode
    )
    return SummaryReport(rows=rows, group_by=resolved_group_by, privacy_mode=privacy_mode)


def build_expensive_calls_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    privacy_mode: str = "normal",
) -> SummaryReport:
    """Build a highest-token-call report with pricing efficiency annotations."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    pricing = load_pricing_config(pricing_path)
    rows = query_most_expensive_calls(
        db_path,
        limit=limit,
        since=resolve_since(preset, since),
    )
    return SummaryReport(
        rows=apply_project_privacy_to_rows(
            annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
            privacy_mode=privacy_mode,
        ),
        group_by="call",
        is_expensive=True,
        privacy_mode=privacy_mode,
    )


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


def build_action_brief_report(
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
    privacy_mode: str = "normal",
    precomputed_reports: dict[str, dict[str, Any]] | None = None,
) -> ActionBriefReport:
    """Build a compact remediation brief from aggregate diagnostics."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_goal = _normalize_agentic_goal(goal) or "token_waste"
    normalized_limit = max(1, evidence_limit)
    report_cache = precomputed_reports if precomputed_reports is not None else {}
    actions: list[dict[str, Any]] = []
    source_reports: list[str] = []
    caveats = [
        "Local Codex logs only; this is not an official OpenAI usage ledger.",
        "Actions are aggregate recommendations; expensive work may still have been valuable.",
        "Archived sessions are excluded unless include_archived is true.",
    ]

    if normalized_goal in {"overview", "token_waste", "cache_failure"}:
        large_low_output = report_cache.get("large_low_output")
        if large_low_output is None:
            large_low_output = build_large_low_output_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["large_low_output"] = large_low_output
        source_reports.append(str(large_low_output["schema"]))
        if large_low_output["rows"]:
            actions.append(
                _action_brief_action(
                    family="large_low_output_context_pressure",
                    finding="Large calls produced little output",
                    confidence=_count_confidence(int(large_low_output["total_candidates"])),
                    evidence=large_low_output["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "Large input or context payloads with little output can indicate cold resumes, "
                        "stale thread continuation, or context copied forward after the useful work ended."
                    ),
                    recommended_workflow_change=(
                        "Create a short handoff, start a fresh thread for the next task, and keep only the "
                        "specific files or facts needed for the follow-up."
                    ),
                    recommended_existing_tool={
                        "tool": "Headroom",
                        "reason": "Use when available to estimate context pressure before continuing a long thread.",
                    },
                    recommended_custom_solution=(
                        "Add a repo-local handoff/checkpoint command or template that summarizes stable facts "
                        "without rereading broad context."
                    ),
                    how_to_verify=(
                        "Re-run `usage_large_low_output_calls` and inspect whether future high-token calls have "
                        "higher output, lower context pressure, or clearer task boundaries."
                    ),
                    recommended_next_tools=[
                        "usage_large_low_output_calls",
                        "usage_call_detail",
                        "usage_threads",
                    ],
                    missing_access="The aggregate report cannot know whether a low-output call produced valuable reasoning.",
                )
            )

        recommendations = report_cache.get("recommendations")
        if recommendations is None:
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
            report_cache["recommendations"] = recommendations
        source_reports.append(str(recommendations["schema"]))

    if normalized_goal in {"overview", "token_waste", "cache_failure", "workflow_churn"}:
        repeated_files = report_cache.get("repeated_files")
        if repeated_files is None:
            repeated_files = build_repeated_file_rediscovery_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["repeated_files"] = repeated_files
        source_reports.append(str(repeated_files["schema"]))
        if repeated_files["rows"]:
            actions.append(
                _action_brief_action(
                    family="repeated_file_rediscovery",
                    finding="Repeated file rediscovery",
                    confidence=_count_confidence(int(repeated_files["total_candidates"])),
                    evidence=repeated_files["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "The same safe file identities keep being rediscovered, which can mean the agent is "
                        "spending turns rebuilding local context instead of using a durable note or helper."
                    ),
                    recommended_workflow_change=(
                        "Write stable file roles or investigation findings into a project note, then ask Codex "
                        "to use that note before opening the same files again."
                    ),
                    recommended_existing_tool=None,
                    recommended_custom_solution=(
                        "Create a small repo command or skill section that returns the exact file map, owner, "
                        "or test selector the agent keeps rediscovering."
                    ),
                    how_to_verify=(
                        "Re-run `usage_repeated_file_rediscovery` and confirm repeated safe file identities "
                        "drop or move to intentional focused reads."
                    ),
                    recommended_next_tools=[
                        "usage_repeated_file_rediscovery",
                        "usage_thread_trace",
                    ],
                    missing_access="Safe hashes prove recurrence, not whether each reread was necessary.",
                )
            )

        shell_churn = report_cache.get("shell_churn")
        if shell_churn is None:
            shell_churn = build_shell_churn_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                min_occurrences=2,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["shell_churn"] = shell_churn
        source_reports.append(str(shell_churn["schema"]))
        if shell_churn["rows"]:
            actions.append(
                _action_brief_action(
                    family="shell_churn",
                    finding="Repeated shell probing",
                    confidence=_count_confidence(int(shell_churn["total_candidates"])),
                    evidence=shell_churn["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "Repeated command families can indicate trial-and-error probing, especially when reads, "
                        "searches, or failed checks repeat without converging on an edit."
                    ),
                    recommended_workflow_change=(
                        "After two similar failed probes, summarize what was learned and switch to a narrower "
                        "query, helper script, or test selector."
                    ),
                    recommended_existing_tool=None,
                    recommended_custom_solution=(
                        "Add a project command for the repeated search/test sequence, or encode the sequence "
                        "in a repo skill so it is executed once intentionally."
                    ),
                    how_to_verify=(
                        "Re-run `usage_shell_churn` and compare repeated sed/rg/git/nl families before and "
                        "after the workflow change."
                    ),
                    recommended_next_tools=["usage_shell_churn", "usage_investigation_walk"],
                    missing_access="Aggregate command families omit raw command arguments in strict/shareable modes.",
                )
            )

    if normalized_goal in {"overview", "allowance_change"}:
        actions.append(
            _action_brief_action(
                family="allowance_change_readiness",
                finding="Allowance-change claims need weekly evidence first",
                confidence="evidence_required",
                evidence=[],
                likely_waste_pattern=(
                    "Five-hour movement is rolling-window context and can look noisy even when weekly allowance "
                    "behavior is stable."
                ),
                recommended_workflow_change=(
                    "Use weekly diagnostics before making public claims; treat outside usage and missing "
                    "observations as downgrade caveats."
                ),
                recommended_existing_tool=None,
                recommended_custom_solution=(
                    "Keep a local strict evidence export for Reddit/issues rather than sharing screenshots or raw logs."
                ),
                how_to_verify=(
                    'Run `usage_allowance_diagnostics(window_kind="weekly", privacy_mode="strict")` and '
                    '`usage_allowance_export(window_kind="weekly")`.'
                ),
                recommended_next_tools=["usage_allowance_diagnostics", "usage_allowance_export"],
                missing_access="OpenAI's internal ledger and other-surface account usage are not available locally.",
            )
        )

    if not actions:
        actions.append(
            _action_brief_action(
                family="insufficient_signal",
                finding="No strong aggregate action candidate at default thresholds",
                confidence="insufficient_local_evidence",
                evidence=[],
                likely_waste_pattern="No supported aggregate diagnostic crossed the default action threshold.",
                recommended_workflow_change=(
                    "Widen the time range, include archived sessions, lower tool-specific thresholds, or inspect "
                    "top calls/threads manually."
                ),
                recommended_existing_tool=None,
                recommended_custom_solution="Create a narrower hypothesis and test it with direct aggregate tools.",
                how_to_verify="Run `usage_suggest_investigations` or `usage_investigate` with a more specific goal.",
                recommended_next_tools=[
                    "usage_suggest_investigations",
                    "usage_investigate",
                    "usage_calls",
                ],
                missing_access="The brief needs stronger aggregate signals or a narrower user question.",
            )
        )

    payload = {
        "schema": "codex-usage-tracker-action-brief-v1",
        "content_mode": "aggregate_action_brief",
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
        },
        "summary": {
            "action_count": len(actions),
            "top_action_family": actions[0]["family"] if actions else None,
            "source_reports": source_reports,
            "shared_report_cache_keys": sorted(report_cache),
        },
        "actions": actions,
        "recommended_next_tools": _dedupe_action_tools(actions),
        "caveats": caveats,
    }
    return ActionBriefReport(payload)


def _action_brief_action(
    *,
    family: str,
    finding: str,
    confidence: str,
    evidence: list[dict[str, Any]],
    likely_waste_pattern: str,
    recommended_workflow_change: str,
    recommended_existing_tool: dict[str, str] | None,
    recommended_custom_solution: str,
    how_to_verify: str,
    recommended_next_tools: list[str],
    missing_access: str,
) -> dict[str, Any]:
    return {
        "family": family,
        "finding": finding,
        "confidence": confidence,
        "evidence_count": len(evidence),
        "evidence_summary": _agentic_evidence_summary(evidence),
        "evidence": [_compact_agentic_evidence_row(row) for row in evidence],
        "likely_waste_pattern": likely_waste_pattern,
        "recommended_workflow_change": recommended_workflow_change,
        "recommended_existing_tool": recommended_existing_tool,
        "recommended_custom_solution": recommended_custom_solution,
        "how_to_verify": how_to_verify,
        "recommended_next_tools": recommended_next_tools,
        "missing_access": missing_access,
    }


def _dedupe_action_tools(actions: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    seen: set[str] = set()
    for action in actions:
        for tool in action.get("recommended_next_tools", []):
            tool_name = str(tool)
            if tool_name in seen:
                continue
            seen.add(tool_name)
            tools.append(tool_name)
    return tools


HYPOTHESIS_TEST_FAMILIES = (
    "token_waste",
    "cache_failure",
    "repeated_file_rediscovery",
    "shell_churn",
    "effort_model_choice",
    "allowance_change",
)

_DEFAULT_HYPOTHESES = {
    "token_waste": "Token waste is concentrated in obvious high-token low-output calls.",
    "cache_failure": "Cache misses or cold resumes are inflating large calls.",
    "repeated_file_rediscovery": "Repeated file rediscovery is wasting tokens.",
    "shell_churn": "Repeated shell probing is creating workflow churn.",
    "effort_model_choice": "Model or effort choices are a meaningful usage driver.",
    "allowance_change": "Weekly allowance behavior may have changed.",
}


def build_hypothesis_test_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    question: str,
    hypotheses: list[str] | str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> HypothesisTestReport:
    """Test usage hypotheses using bounded existing diagnostics."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = max(1, evidence_limit)
    requested = _normalize_hypothesis_inputs(hypotheses)
    hypothesis_specs = (
        [
            {
                "id": f"hypothesis-{index}",
                "hypothesis": hypothesis,
                "family": _classify_hypothesis_family(hypothesis, question),
            }
            for index, hypothesis in enumerate(requested, start=1)
        ]
        if requested
        else [
            {
                "id": family,
                "hypothesis": _DEFAULT_HYPOTHESES[family],
                "family": family,
            }
            for family in HYPOTHESIS_TEST_FAMILIES
        ]
    )

    context: dict[str, Any] = {}
    tested = [
        _evaluate_hypothesis_spec(
            spec,
            context=context,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=normalized_limit,
            privacy_mode=privacy_mode,
        )
        for spec in hypothesis_specs
    ]
    status_counts: dict[str, int] = {}
    for result in tested:
        status = str(result["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    payload = {
        "schema": "codex-usage-tracker-hypothesis-test-v1",
        "content_mode": "aggregate_with_local_index_signals",
        "includes_indexed_content": True,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "question": question,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": normalized_limit,
        },
        "summary": {
            "hypothesis_count": len(tested),
            "status_counts": status_counts,
            "top_status": tested[0]["status"] if tested else None,
        },
        "hypotheses": tested,
        "recommended_next_tools": _dedupe_next_tools(
            [
                tool
                for result in tested
                for tool in result.get("recommended_next_tools", [])
                if isinstance(tool, dict)
            ]
        ),
        "caveats": [
            "Local Codex logs only; this is not an official OpenAI usage ledger.",
            "Hypothesis results are local evidence classifications, not proof of user intent.",
            "Raw prompts, assistant text, tool output, raw commands, and full paths are not included.",
        ],
    }
    return HypothesisTestReport(payload)


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


def build_investigation_walk_report(
    *,
    db_path: Path,
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> InvestigationWalkReport:
    """Build a bounded local investigation walk over normalized pattern evidence."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_evidence_limit = max(1, evidence_limit)
    pattern_result = query_pattern_scan(
        db_path=db_path,
        scan_type="all",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=normalized_evidence_limit * 4,
    )
    large_low_output_result = query_large_low_output_calls(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=20_000,
        max_output_tokens=1_000,
        limit=normalized_evidence_limit,
    )
    patterns = pattern_result["patterns"]
    branches = _investigation_branches(patterns=patterns, evidence_limit=normalized_evidence_limit)
    branches.append(
        _large_low_output_branch(
            rows=large_low_output_result["rows"],
            evidence_limit=normalized_evidence_limit,
        )
    )
    branches.sort(key=lambda branch: (-int(branch["score"]), str(branch["scan_type"])))
    supported = [branch for branch in branches if branch["status"] != "no_evidence"]
    payload = {
        "schema": "codex-usage-tracker-investigation-walk-v1",
        "content_mode": "local_content_index",
        "includes_indexed_content": True,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "question": question,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "min_occurrences": max(1, min_occurrences),
            "evidence_limit": normalized_evidence_limit,
        },
        "summary": {
            "branch_count": len(branches),
            "supported_branch_count": len(supported),
            "top_hypothesis": supported[0]["hypothesis"] if supported else None,
            "confidence": _walk_confidence(supported),
        },
        "branches": branches,
        "recommended_next_tools": _recommended_investigation_tools(supported),
    }
    record_investigation_run(db_path=db_path, run_kind="investigation_walk", payload=payload)
    return InvestigationWalkReport(payload)


def _investigation_branches(
    *,
    patterns: list[dict[str, Any]],
    evidence_limit: int,
) -> list[dict[str, Any]]:
    specs = (
        (
            "context_bloat",
            "High-token thread/context bloat",
            "Threads with concentrated token use or dense local evidence may be driving usage.",
        ),
        (
            "command_loop",
            "Repeated or failing command loop",
            "Repeated command roots/labels can indicate retry loops or avoidable automation waste.",
        ),
        (
            "file_churn",
            "Repeated file rediscovery or churn",
            "Repeated reads or edits of the same path hash can indicate rediscovery or unstable workflow loops.",
        ),
        (
            "repetition",
            "Repeated local content pattern",
            "Repeated fragment hashes can indicate recurring prompts, summaries, or copied context.",
        ),
    )
    branches: list[dict[str, Any]] = []
    for scan_type, hypothesis, rationale in specs:
        evidence = [row for row in patterns if row.get("scan_type") == scan_type]
        evidence.sort(
            key=lambda row: (-int(row.get("total_tokens") or 0), -int(row.get("occurrences") or 0))
        )
        selected = evidence[:evidence_limit]
        score = _branch_score(selected)
        branches.append(
            {
                "scan_type": scan_type,
                "hypothesis": hypothesis,
                "rationale": rationale,
                "status": _branch_status(score, selected),
                "score": score,
                "evidence_count": len(selected),
                "evidence": selected,
                "pruned_reason": None
                if selected
                else "No matching normalized local evidence at this threshold.",
            }
        )
    branches.sort(key=lambda branch: (-int(branch["score"]), str(branch["scan_type"])))
    return branches


def _large_low_output_branch(
    *,
    rows: list[dict[str, Any]],
    evidence_limit: int,
) -> dict[str, Any]:
    selected = [dict(row, scan_type="large_low_output") for row in rows[:evidence_limit]]
    score = _branch_score(selected)
    return {
        "scan_type": "large_low_output",
        "hypothesis": "Large calls with little output",
        "rationale": (
            "Large input/context usage with low output can indicate cold resumes, "
            "tool-output pressure, stale thread continuation, or low-value continuation."
        ),
        "status": _branch_status(score, selected),
        "score": score,
        "evidence_count": len(selected),
        "evidence": selected,
        "pruned_reason": None if selected else "No calls matched large low-output thresholds.",
    }


def _branch_score(evidence: list[dict[str, Any]]) -> int:
    total = 0
    for row in evidence:
        total += int(row.get("total_tokens") or 0)
        total += int(row.get("occurrences") or 0) * 100
        total += int(row.get("call_count") or 0) * 50
    return total


def _branch_status(score: int, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "no_evidence"
    if score >= 10_000:
        return "strong_local_signal"
    return "candidate"


def _walk_confidence(supported: list[dict[str, Any]]) -> str:
    if not supported:
        return "insufficient_local_evidence"
    if supported[0]["status"] == "strong_local_signal":
        return "moderate_local_evidence"
    return "weak_local_evidence"


def _recommended_investigation_tools(supported: list[dict[str, Any]]) -> list[dict[str, str]]:
    tools = [
        {
            "tool": "usage_calls",
            "reason": "Inspect the aggregate call rows behind high-token evidence.",
        }
    ]
    if not supported:
        tools.append(
            {
                "tool": "usage_report_pack",
                "reason": "Start from aggregate report cards when local pattern evidence is sparse.",
            }
        )
        return tools
    top_scan = str(supported[0]["scan_type"])
    if top_scan == "context_bloat":
        tools.append(
            {
                "tool": "usage_thread_trace",
                "reason": "Trace the highest-scoring thread to inspect call sequence and indexed fragments.",
            }
        )
    elif top_scan == "command_loop":
        tools.append(
            {
                "tool": "usage_command_loop_scan",
                "reason": "Raise limit or lower occurrence threshold to inspect repeated command families.",
            }
        )
    elif top_scan == "file_churn":
        tools.append(
            {
                "tool": "usage_file_churn_scan",
                "reason": "Inspect repeated file path hashes and linked aggregate calls.",
            }
        )
    elif top_scan == "large_low_output":
        tools.append(
            {
                "tool": "usage_large_low_output_calls",
                "reason": "Inspect large input/context calls that produced little output.",
            }
        )
    else:
        tools.append(
            {
                "tool": "usage_content_search",
                "reason": "Use explicit local snippet search only when transcript-level evidence is needed.",
            }
        )
    if any(str(branch["scan_type"]) == "large_low_output" for branch in supported) and all(
        tool["tool"] != "usage_large_low_output_calls" for tool in tools
    ):
        tools.append(
            {
                "tool": "usage_large_low_output_calls",
                "reason": "Inspect large input/context calls that produced little output.",
            }
        )
    return tools


def build_local_evidence_export_report(
    *,
    db_path: Path,
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
) -> LocalEvidenceExportReport:
    """Build shareable local evidence summary without raw/indexed records."""

    walk = build_investigation_walk_report(
        db_path=db_path,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
        privacy_mode="strict",
    ).payload
    branches = [_export_branch(branch) for branch in walk["branches"]]
    payload = {
        "schema": "codex-usage-tracker-local-evidence-export-v1",
        "content_mode": "shareable_local_evidence",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": "strict",
        "question": question,
        "filters": walk["filters"],
        "summary": {
            **walk["summary"],
            "export_branch_count": len(branches),
        },
        "branches": branches,
        "omitted_fields": [
            "record_id",
            "session_id",
            "thread_name",
            "raw_fragment",
            "snippet",
            "raw_command",
            "raw_tool_output",
            "full_path",
            "path_basename",
            "command_label",
        ],
        "caveats": [
            "Local evidence only; not an official OpenAI ledger.",
            "Counts are derived from local Codex logs and normalized tracker indexes.",
            "Export intentionally omits prompts, snippets, thread names, record ids, raw command output, and file names.",
        ],
    }
    record_investigation_run(db_path=db_path, run_kind="local_evidence_export", payload=payload)
    return LocalEvidenceExportReport(payload)


def _export_branch(branch: dict[str, Any]) -> dict[str, Any]:
    evidence = branch.get("evidence")
    evidence_rows = evidence if isinstance(evidence, list) else []
    return {
        "scan_type": branch["scan_type"],
        "hypothesis": branch["hypothesis"],
        "status": branch["status"],
        "score_bucket": _score_bucket(int(branch.get("score") or 0)),
        "evidence_count": int(branch.get("evidence_count") or 0),
        "pruned": branch["status"] == "no_evidence",
        "pruned_reason": branch.get("pruned_reason"),
        "aggregate_evidence": _export_aggregate_evidence(evidence_rows),
    }


def _export_aggregate_evidence(evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(evidence_rows)
    occurrences = sum(int(row.get("occurrences") or 0) for row in evidence_rows)
    call_count = sum(int(row.get("call_count") or 0) for row in evidence_rows)
    thread_count = sum(int(row.get("thread_count") or 0) for row in evidence_rows)
    record_ids = {str(row.get("record_id")) for row in evidence_rows if row.get("record_id")}
    thread_keys = {
        str(row.get("thread_key") or row.get("thread_name"))
        for row in evidence_rows
        if row.get("thread_key") or row.get("thread_name")
    }
    return {
        "evidence_row_count": row_count,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in evidence_rows),
        "occurrences": occurrences or row_count,
        "call_count": call_count or len(record_ids) or row_count,
        "thread_count": thread_count or len(thread_keys),
        "first_seen_date": _date_bucket(_first_seen(evidence_rows)),
        "last_seen_date": _date_bucket(_last_seen(evidence_rows)),
    }


def _score_bucket(score: int) -> str:
    if score >= 100_000:
        return "100k_plus"
    if score >= 10_000:
        return "10k_to_100k"
    if score > 0:
        return "under_10k"
    return "none"


def _first_seen(rows: list[dict[str, Any]]) -> str | None:
    values = [str(row["first_seen_at"]) for row in rows if row.get("first_seen_at")]
    return min(values) if values else None


def _last_seen(rows: list[dict[str, Any]]) -> str | None:
    values = [str(row["last_seen_at"]) for row in rows if row.get("last_seen_at")]
    return max(values) if values else None


def _date_bucket(value: str | None) -> str | None:
    return value[:10] if value else None
