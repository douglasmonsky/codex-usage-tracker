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
from codex_usage_tracker.reports.action_brief import (
    ActionBriefReport as ActionBriefReport,
)
from codex_usage_tracker.reports.action_brief import (
    build_action_brief_report as build_action_brief_report,
)
from codex_usage_tracker.reports.agentic import (
    AgenticInvestigationReport as AgenticInvestigationReport,
)
from codex_usage_tracker.reports.agentic import (
    InvestigationSuggestionsReport as InvestigationSuggestionsReport,
)
from codex_usage_tracker.reports.agentic import (
    _dedupe_next_tools,
)
from codex_usage_tracker.reports.agentic import (
    build_agentic_investigation_report as build_agentic_investigation_report,
)
from codex_usage_tracker.reports.agentic import (
    build_investigation_suggestions_report as build_investigation_suggestions_report,
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
from codex_usage_tracker.reports.investigation_walk import (
    InvestigationWalkReport as InvestigationWalkReport,
)
from codex_usage_tracker.reports.investigation_walk import (
    LocalEvidenceExportReport as LocalEvidenceExportReport,
)
from codex_usage_tracker.reports.investigation_walk import (
    build_investigation_walk_report as build_investigation_walk_report,
)
from codex_usage_tracker.reports.investigation_walk import (
    build_local_evidence_export_report as build_local_evidence_export_report,
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
    query_most_expensive_calls,
    query_summary,
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
class HypothesisTestReport:
    """Stable machine-readable agentic hypothesis test report."""

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
