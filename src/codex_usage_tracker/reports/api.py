"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

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
                annotate_rows_with_recommendations(
                    annotate_rows_with_efficiency(rows, pricing)
                ),
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
    has_more = (
        False
        if normalized_limit is None
        else normalized_offset + len(rows) < total_matched
    )
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
            "next_offset": (
                normalized_offset + len(rows) if has_more else None
            ),
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
    has_more = (
        False
        if normalized_limit is None
        else normalized_offset + len(calls) < total_matched
    )
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
            "next_offset": (
                normalized_offset + len(calls) if has_more else None
            ),
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
    privacy_mode: str = "normal",
) -> AgenticInvestigationReport:
    """Build a compact goal-led investigation using existing reports."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_goal = _normalize_agentic_goal(goal) or "token_waste"
    normalized_limit = max(1, evidence_limit)
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
                    confidence=_count_confidence(int(large_low_output["total_candidates"])),
                    why_it_matters=(
                        "Large input/context usage with low output is a strong candidate for "
                        "cold resumes, stale thread continuation, or low-value continuation."
                    ),
                    recommended_action=(
                        "Open the top calls, check whether a smaller fresh thread or preserved handoff "
                        "would avoid resending large context."
                    ),
                    verify_with=["usage_large_low_output_calls", "usage_call_detail", "usage_thread_trace"],
                    privacy_notes="Aggregate token/activity counts only; no raw fragments or command output.",
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
            limit=normalized_limit,
            privacy_mode=privacy_mode,
        ).payload
        source_reports.append(str(recommendations["schema"]))
        if recommendations["rows"]:
            findings.append(
                _agentic_finding(
                    finding="Ranked aggregate usage recommendations",
                    evidence=recommendations["rows"][:normalized_limit],
                    confidence="medium",
                    why_it_matters="Existing recommendation scoring combines aggregate cost, cache, context, and pricing signals.",
                    recommended_action="Start with the highest recommendation score, then verify with the specific diagnostic tool.",
                    verify_with=["usage_recommendations", "usage_calls", "usage_call_detail"],
                    privacy_notes="Aggregate recommendations only; no prompt or tool-output text.",
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
        caveats.append("Weekly allowance evidence is the primary signal; 5-hour counters are rolling-window context.")

    if normalized_goal == "overview":
        recommended_next_tools.extend(
            [
                {"tool": "usage_status", "reason": "Confirm index freshness and row counts.", "default_arguments": {}},
                {
                    "tool": "usage_summary",
                    "reason": "Rank projects, threads, models, or dates depending on the user's next question.",
                    "default_arguments": {"group_by": "thread", "limit": 10, "response_format": "json"},
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
                confidence="insufficient_local_evidence",
                why_it_matters="The current aggregate diagnostics did not find a clear candidate at the default threshold.",
                recommended_action="Lower thresholds, widen the time window, include archived sessions, or inspect top aggregate calls.",
                verify_with=["usage_calls", "usage_report_pack", "usage_investigation_walk"],
                privacy_notes="No raw context needed for this follow-up.",
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
            "follow_up_tools": ["usage_shell_churn", "usage_repeated_file_rediscovery", "usage_thread_trace"],
            "privacy_notes": "Uses safe command labels and path identities, not raw command output or full paths.",
        },
        {
            "goal": "overview",
            "label": "Summarize current usage drivers",
            "why_it_matters": "Starts with index freshness, thread/model/project summaries, and existing recommendation cards.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "overview", "evidence_limit": 5},
            "follow_up_tools": ["usage_status", "usage_summary", "usage_report_pack", "usage_recommendations"],
            "privacy_notes": "Aggregate dashboard/report-pack evidence.",
        },
    ]
    if goal is None:
        return suggestions
    return [row for row in suggestions if row["goal"] == goal] or suggestions


def _agentic_finding(
    *,
    finding: str,
    evidence: list[dict[str, Any]],
    confidence: str,
    why_it_matters: str,
    recommended_action: str,
    verify_with: list[str],
    privacy_notes: str,
) -> dict[str, Any]:
    return {
        "finding": finding,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "confidence": confidence,
        "why_it_matters": why_it_matters,
        "recommended_action": recommended_action,
        "verify_with": verify_with,
        "privacy_notes": privacy_notes,
    }


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
    return max((str(row.get("confidence") or "") for row in findings), key=lambda value: priorities.get(value, 0))


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
        evidence.sort(key=lambda row: (-int(row.get("total_tokens") or 0), -int(row.get("occurrences") or 0)))
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
                "pruned_reason": None if selected else "No matching normalized local evidence at this threshold.",
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
        "aggregate_evidence": {
            "total_tokens": sum(int(row.get("total_tokens") or 0) for row in evidence_rows),
            "occurrences": sum(int(row.get("occurrences") or 0) for row in evidence_rows),
            "call_count": sum(int(row.get("call_count") or 0) for row in evidence_rows),
            "thread_count": sum(int(row.get("thread_count") or 0) for row in evidence_rows),
            "first_seen_date": _date_bucket(_first_seen(evidence_rows)),
            "last_seen_date": _date_bucket(_last_seen(evidence_rows)),
        },
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
    min_score: float | None = None,
    limit: int = 20,
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
                "min_score": min_score,
                "limit": normalized_limit,
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
) -> list[dict[str, Any]]:
    return annotate_thread_attachments(
        query_dashboard_events(
            db_path,
            limit=0,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
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
