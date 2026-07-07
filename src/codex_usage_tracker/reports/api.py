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
    query_most_expensive_calls,
    query_source_record_coverage,
    query_source_record_totals,
    query_summary,
    query_thread_trace,
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
