"""Filtered usage query and recommendation reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.formatting import format_recommendations
from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
    validate_privacy_mode,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.pricing.api import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.reports.filters import query_row_matches
from codex_usage_tracker.reports.recommendation_builder import (
    recommendation_sort_key,
    thread_recommendation_rows,
)
from codex_usage_tracker.reports.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store.api import query_dashboard_events

QUERY_PRICING_STATUS_CHOICES = ("priced", "estimated", "unpriced")
QUERY_CREDIT_CONFIDENCE_CHOICES = ("exact", "estimated", "unpriced", "user_override")


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
