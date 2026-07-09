"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.formatting import (
    format_calls,
    format_pricing_coverage,
    format_recommendations,
    format_source_coverage,
    format_summary,
)
from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    apply_project_privacy_to_summary_rows,
    load_project_config,
    validate_privacy_mode,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.pricing.api import (
    PricingConfig,
    annotate_rows_with_efficiency,
    load_pricing_config,
    summarize_pricing_coverage,
)
from codex_usage_tracker.reports.filters import query_row_matches
from codex_usage_tracker.reports.project_summary import project_summary_rows
from codex_usage_tracker.reports.recommendation_builder import (
    recommendation_sort_key,
    thread_recommendation_rows,
)
from codex_usage_tracker.reports.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store.api import (
    query_content_search,
    query_dashboard_events,
    query_large_low_output_calls,
    query_most_expensive_calls,
    query_pattern_scan,
    query_repeated_file_rediscovery,
    query_shell_churn,
    query_source_record_coverage,
    query_source_record_totals,
    query_summary,
    query_thread_trace,
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
QUERY_PRICING_STATUS_CHOICES = ("priced", "estimated", "unpriced")
QUERY_CREDIT_CONFIDENCE_CHOICES = ("exact", "estimated", "unpriced", "user_override")

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
class PricingCoverageReport:
    """Resolved pricing coverage report."""

    payload: dict[str, Any]

    def render(self, limit: int = 20) -> str:
        return format_pricing_coverage(self.payload, limit=limit)


@dataclass(frozen=True)
class SourceCoverageReport:
    """Resolved source provenance parser coverage report."""

    payload: dict[str, Any]

    def render(self, limit: int = 20) -> str:
        return format_source_coverage(self.payload, limit=limit)


@dataclass(frozen=True)
class ContentSearchReport:
    """Stable machine-readable local content-index search result."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ThreadTraceReport:
    """Stable machine-readable local content-index thread trace."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class PatternScanReport:
    """Stable machine-readable local content/event-index pattern scan."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class RepeatedFileRediscoveryReport:
    """Stable machine-readable repeated safe file-identity report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ShellChurnReport:
    """Stable machine-readable repeated shell command churn report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class LargeLowOutputReport:
    """Stable machine-readable large low-output call report."""

    payload: dict[str, Any]


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


@dataclass(frozen=True)
class QueryReport:
    """Stable machine-readable aggregate usage query result."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class RecommendationsReport:
    """Stable recommendation ranking for aggregate usage rows and threads."""

    payload: dict[str, Any]

    def render(self) -> str:
        return format_recommendations(self.payload)


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


def build_pricing_coverage_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 1000,
    since: str | None = None,
    pricing: PricingConfig | None = None,
) -> PricingCoverageReport:
    """Build pricing coverage data grouped by model."""

    config = pricing or load_pricing_config(pricing_path)
    rows = query_summary(db_path, group_by="model", limit=limit, since=since)
    return PricingCoverageReport(summarize_pricing_coverage(rows, pricing=config))


def build_source_coverage_report(
    *,
    db_path: Path,
    include_archived: bool = False,
) -> SourceCoverageReport:
    """Build parser/source provenance coverage report."""

    rows = query_source_record_coverage(
        db_path=db_path,
        include_archived=include_archived,
    )
    totals = query_source_record_totals(
        db_path=db_path,
        include_archived=include_archived,
    )
    return SourceCoverageReport(
        {
            "schema": "codex-usage-tracker-source-coverage-v1",
            "content_mode": "aggregate_only",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "include_archived": include_archived,
            "source_record_count": int(totals.get("source_record_count") or 0),
            "source_file_count": int(totals.get("source_file_count") or 0),
            "parser_version_count": int(totals.get("parser_version_count") or 0),
            "warning_record_count": int(totals.get("warning_record_count") or 0),
            "rows": rows,
        }
    )


def build_content_search_report(
    *,
    db_path: Path,
    query: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 20,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> ContentSearchReport:
    """Build explicit local content-index search payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_content_search(
        db_path=db_path,
        query=query,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
    )
    rows = result["rows"]
    normalized_limit = None if limit is None or limit <= 0 else limit
    normalized_offset = max(0, offset)
    total_matched = int(result["total_matched_rows"])
    has_more = False if normalized_limit is None else normalized_offset + len(rows) < total_matched
    return ContentSearchReport(
        {
            "schema": "codex-usage-tracker-content-search-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": True,
            "privacy_mode": privacy_mode,
            "query": query,
            "filters": {
                "since": since,
                "until": until,
                "model": model,
                "effort": effort,
                "thread": thread,
                "include_archived": include_archived,
                "limit": limit,
                "offset": normalized_offset,
                "max_snippet_chars": max_snippet_chars,
            },
            "search_mode": result["search_mode"],
            "row_count": len(rows),
            "total_matched_rows": total_matched,
            "truncated": has_more,
            "has_more": has_more,
            "next_offset": (normalized_offset + len(rows) if has_more else None),
            "rows": rows,
        }
    )


def build_thread_trace_report(
    *,
    db_path: Path,
    thread: str | None = None,
    thread_key: str | None = None,
    session_id: str | None = None,
    record_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> ThreadTraceReport:
    """Build explicit local content-index thread/session trace payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_thread_trace(
        db_path=db_path,
        thread=thread,
        thread_key=thread_key,
        session_id=session_id,
        record_id=record_id,
        since=since,
        until=until,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
    )
    calls = result["calls"]
    normalized_limit = None if limit is None or limit <= 0 else limit
    normalized_offset = max(0, offset)
    total_matched = int(result["total_matched_calls"])
    has_more = False if normalized_limit is None else normalized_offset + len(calls) < total_matched
    return ThreadTraceReport(
        {
            "schema": "codex-usage-tracker-thread-trace-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": True,
            "privacy_mode": privacy_mode,
            "filters": {
                "thread": thread,
                "thread_key": thread_key,
                "session_id": session_id,
                "record_id": record_id,
                "since": since,
                "until": until,
                "include_archived": include_archived,
                "limit": limit,
                "offset": normalized_offset,
                "max_snippet_chars": max_snippet_chars,
            },
            "call_count": len(calls),
            "total_matched_calls": total_matched,
            "truncated": has_more,
            "has_more": has_more,
            "next_offset": (normalized_offset + len(calls) if has_more else None),
            "calls": calls,
        }
    )


def build_pattern_scan_report(
    *,
    db_path: Path,
    scan_type: str = "all",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> PatternScanReport:
    """Build local content/event-index pattern scan payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_pattern_scan(
        db_path=db_path,
        scan_type=scan_type,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
    )
    patterns = result["patterns"]
    return PatternScanReport(
        {
            "schema": "codex-usage-tracker-pattern-scan-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "scan_type": scan_type,
            "scan_types": list(result["scan_types"]),
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
            },
            "pattern_count": len(patterns),
            "total_patterns": result["total_patterns"],
            "patterns": patterns,
        }
    )


def build_repeated_file_rediscovery_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> RepeatedFileRediscoveryReport:
    """Build repeated safe file-identity rediscovery payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_repeated_file_rediscovery(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
    )
    rows = result["rows"]
    return RepeatedFileRediscoveryReport(
        {
            "schema": "codex-usage-tracker-repeated-file-rediscovery-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
                "sample_limit": max(1, sample_limit),
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
    )


def build_shell_churn_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> ShellChurnReport:
    """Build repeated shell command family churn payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_shell_churn(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
    )
    rows = result["rows"]
    return ShellChurnReport(
        {
            "schema": "codex-usage-tracker-shell-churn-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
                "sample_limit": max(1, sample_limit),
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
    )


def build_large_low_output_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> LargeLowOutputReport:
    """Build aggregate-first large low-output call payload."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_min_total = max(0, min_total_tokens)
    normalized_max_output = max(0, max_output_tokens)
    result = query_large_low_output_calls(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=normalized_min_total,
        max_output_tokens=normalized_max_output,
        limit=limit,
    )
    rows = result["rows"]
    return LargeLowOutputReport(
        {
            "schema": "codex-usage-tracker-large-low-output-v1",
            "content_mode": "aggregate_with_local_activity",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_total_tokens": normalized_min_total,
                "max_output_tokens": normalized_max_output,
                "limit": limit,
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
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


def _normalize_hypothesis_inputs(hypotheses: list[str] | str | None) -> list[str]:
    if hypotheses is None:
        return []
    if isinstance(hypotheses, str):
        return [hypotheses.strip()] if hypotheses.strip() else []
    return [str(hypothesis).strip() for hypothesis in hypotheses if str(hypothesis).strip()]


def _classify_hypothesis_family(hypothesis: str, question: str) -> str:
    hypothesis_family = _classify_hypothesis_text(hypothesis.lower())
    if hypothesis_family is not None:
        return hypothesis_family
    question_family = _classify_hypothesis_text(question.lower())
    if question_family is not None:
        return question_family
    return "token_waste"


def _classify_hypothesis_text(text: str) -> str | None:
    if _has_any_phrase(
        text,
        (
            "allowance",
            "usage allowance",
            "allowance change",
            "limit change",
            "limit changed",
            "codex limit",
            "usage limit",
            "weekly allowance",
            "weekly limit",
            "5-hour",
            "5 hour",
            "throttle",
            "throttled",
        ),
    ):
        return "allowance_change"
    if _has_any_phrase(text, ("cache", "cold resume", "cold resumes", "cold", "resume")):
        return "cache_failure"
    if _has_any_phrase(
        text,
        (
            "file",
            "rediscover",
            "rediscovery",
            "reread",
            "rereads",
            "re-read",
            "re-reads",
            "repeated read",
            "repeated reads",
            "path",
            "content-index",
            "content index",
            "thread-trace",
            "thread trace",
        ),
    ):
        return "repeated_file_rediscovery"
    if _has_shell_hypothesis_signal(text):
        return "shell_churn"
    if _has_any_word(text, ("effort", "model", "xhigh", "high", "medium", "gpt")):
        return "effort_model_choice"
    if _has_any_phrase(
        text,
        (
            "token waste",
            "wasting tokens",
            "waste",
            "expensive",
            "cost",
            "large low-output",
            "large low output",
            "low-output",
            "low output",
            "output length",
            "context pressure",
            "large call",
            "large calls",
            "cleanup target",
        ),
    ):
        return "token_waste"
    return None


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_any_word(text: str, words: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9_-]){re.escape(word)}(?![a-z0-9_-])", text) for word in words
    )


def _has_shell_hypothesis_signal(text: str) -> bool:
    if "shell" in text or "command" in text:
        return True
    tokens = {token for token in re.split(r"[^a-z0-9]+", text) if token}
    return bool(tokens & {"sed", "rg", "git", "nl", "npm", "python", "pytest"})


def _evaluate_hypothesis_spec(
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
    total_tokens = sum(_number(row.get("total_tokens")) for row in rows)
    effort_totals = _token_totals_by(rows, "effort")
    model_totals = _token_totals_by(rows, "model")
    high_effort_tokens = sum(
        value
        for effort, value in effort_totals.items()
        if effort.lower() in {"high", "xhigh", "maximum"}
    )
    high_effort_ratio = high_effort_tokens / total_tokens if total_tokens else 0.0
    if not rows or not total_tokens:
        status = "insufficient_evidence"
        confidence = "insufficient_local_evidence"
    elif high_effort_ratio >= 0.5:
        status = "true"
        confidence = "medium"
    elif high_effort_ratio >= 0.2:
        status = "partially_true"
        confidence = "low"
    else:
        status = "false"
        confidence = "low"
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
        counter_evidence=[]
        if high_effort_ratio
        else ["No high-effort token share found in the selected scope."],
        next_action="Compare high-effort calls against task type, then use lower effort for routine edits and reserve higher effort for uncertain design work.",
        recommended_next_tools=[
            _next_tool("usage_summary", "Summarize usage by model or effort."),
            _next_tool("usage_calls", "Filter calls by effort and inspect outliers."),
            _next_tool(
                "usage_recommendations", "Compare effort choices with aggregate recommendations."
            ),
        ],
    )


def _evaluate_allowance_hypothesis(
    *,
    db_path: Path,
    allowance_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    from codex_usage_tracker.allowance_intelligence import build_allowance_diagnostics_report

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


def build_query_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    min_tokens: int | None = None,
    min_credits: float | None = None,
    limit: int = 100,
    privacy_mode: str = "normal",
) -> QueryReport:
    """Build a stable JSON usage query with aggregate-only annotated rows."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    if pricing_status and pricing_status not in QUERY_PRICING_STATUS_CHOICES:
        raise ValueError(
            f"pricing_status must be one of: {', '.join(QUERY_PRICING_STATUS_CHOICES)}"
        )
    if credit_confidence and credit_confidence not in QUERY_CREDIT_CONFIDENCE_CHOICES:
        raise ValueError(
            f"credit_confidence must be one of: {', '.join(QUERY_CREDIT_CONFIDENCE_CHOICES)}"
        )
    rows = annotate_thread_attachments(
        query_dashboard_events(
            db_path,
            limit=0,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            min_tokens=min_tokens,
        )
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path)
    rows = annotate_rows_with_allowance(annotate_rows_with_efficiency(rows, pricing), allowance)
    rows = annotate_rows_with_recommendations(rows)
    rows = annotate_rows_with_project_identity(rows, load_project_config(projects_path))
    rows = [
        row
        for row in rows
        if query_row_matches(
            row,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            project=project,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
            min_tokens=min_tokens,
            min_credits=min_credits,
        )
    ]
    rows = apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)
    normalized_limit = None if limit <= 0 else limit
    limited_rows = rows if normalized_limit is None else rows[:normalized_limit]
    return QueryReport(
        {
            "schema": "codex-usage-tracker-query-v1",
            "filters": {
                "since": since,
                "until": until,
                "model": model,
                "effort": effort,
                "thread": thread,
                "project": project,
                "pricing_status": pricing_status,
                "credit_confidence": credit_confidence,
                "min_tokens": min_tokens,
                "min_credits": min_credits,
                "limit": normalized_limit,
                "privacy_mode": privacy_mode,
            },
            "row_count": len(limited_rows),
            "total_matched_rows": len(rows),
            "truncated": normalized_limit is not None and len(rows) > normalized_limit,
            "rows": limited_rows,
        }
    )


def build_recommendations_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    min_score: float | None = None,
    limit: int = 20,
    source_limit: int | None = None,
    privacy_mode: str = "normal",
) -> RecommendationsReport:
    """Build ranked aggregate recommendations for usage investigations."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    rows = _recommendation_source_rows(
        db_path=db_path,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        source_limit=source_limit,
    )
    rows = _annotated_recommendation_rows(
        rows,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
    )
    scored_rows = _recommendation_filtered_rows(
        rows,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        min_score=min_score,
    )
    scored_rows.sort(key=recommendation_sort_key)
    normalized_limit = None if limit <= 0 else limit
    limited_rows = scored_rows if normalized_limit is None else scored_rows[:normalized_limit]
    private_rows = apply_project_privacy_to_rows(limited_rows, privacy_mode=privacy_mode)
    return RecommendationsReport(
        {
            "schema": "codex-usage-tracker-recommendations-v1",
            "filters": {
                "since": since,
                "until": until,
                "model": model,
                "effort": effort,
                "thread": thread,
                "project": project,
                "include_archived": include_archived,
                "min_score": min_score,
                "limit": normalized_limit,
                "source_limit": source_limit,
                "privacy_mode": privacy_mode,
            },
            "row_count": len(private_rows),
            "total_matched_rows": len(scored_rows),
            "truncated": normalized_limit is not None and len(scored_rows) > normalized_limit,
            "threads": thread_recommendation_rows(scored_rows, limit=normalized_limit or 20),
            "rows": private_rows,
        }
    )


def _recommendation_source_rows(
    *,
    db_path: Path,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
    source_limit: int | None = None,
) -> list[dict[str, Any]]:
    return annotate_thread_attachments(
        query_dashboard_events(
            db_path,
            limit=0 if source_limit is None else source_limit,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
        )
    )


def _annotated_recommendation_rows(
    rows: list[dict[str, Any]],
    *,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
) -> list[dict[str, Any]]:
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path)
    rows = annotate_rows_with_allowance(annotate_rows_with_efficiency(rows, pricing), allowance)
    rows = annotate_rows_with_recommendations(rows)
    return annotate_rows_with_project_identity(rows, load_project_config(projects_path))


def _recommendation_filtered_rows(
    rows: list[dict[str, Any]],
    *,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    project: str | None,
    min_score: float | None,
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if _has_actionable_recommendation(row, min_score)
        and query_row_matches(
            row,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            project=project,
            pricing_status=None,
            credit_confidence=None,
            min_tokens=None,
            min_credits=None,
        )
    ]


def _has_actionable_recommendation(row: dict[str, Any], min_score: float | None) -> bool:
    if not row.get("action_recommendations"):
        return False
    return min_score is None or float(row.get("recommendation_score") or 0) >= min_score
