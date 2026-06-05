"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.formatting import (
    format_calls,
    format_pricing_coverage,
    format_summary,
)
from codex_usage_tracker.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.pricing import (
    PricingConfig,
    annotate_rows_with_efficiency,
    load_pricing_config,
    summarize_pricing_coverage,
)
from codex_usage_tracker.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    apply_project_privacy_to_summary_rows,
    load_project_config,
    validate_privacy_mode,
)
from codex_usage_tracker.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store import (
    query_dashboard_events,
    query_most_expensive_calls,
    query_summary,
)
from codex_usage_tracker.threads import annotate_thread_attachments

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
class QueryReport:
    """Stable machine-readable aggregate usage query result."""

    payload: dict[str, Any]


def resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    """Resolve summary presets into a group and since filter."""

    return _SUMMARY_PRESET_GROUPS.get(preset, group_by), resolve_since(preset, since)


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
        rows = _project_summary_rows(
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
        if _query_row_matches(
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


def _query_row_matches(
    row: dict[str, Any],
    *,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    project: str | None,
    pricing_status: str | None,
    credit_confidence: str | None,
    min_tokens: int | None,
    min_credits: float | None,
) -> bool:
    if until and str(row.get("event_timestamp") or "") > until:
        return False
    if model and str(row.get("model") or "") != model:
        return False
    if effort and str(row.get("effort") or "") != effort:
        return False
    if thread:
        thread_values = {
            str(row.get("thread_name") or ""),
            str(row.get("parent_thread_name") or ""),
            str(row.get("resolved_parent_thread_name") or ""),
            str(row.get("thread_attachment_label") or ""),
            str(row.get("session_id") or ""),
        }
        if thread not in thread_values:
            return False
    if project:
        project_values = {
            str(row.get("project_name") or ""),
            str(row.get("project_key") or ""),
            str(row.get("project_relative_cwd") or ""),
        }
        if project not in project_values and project not in (row.get("project_tags") or []):
            return False
    if pricing_status == "priced" and not row.get("pricing_model"):
        return False
    if pricing_status == "estimated" and not row.get("pricing_estimated"):
        return False
    if pricing_status == "unpriced" and row.get("pricing_model"):
        return False
    if credit_confidence and row.get("usage_credit_confidence") != credit_confidence:
        return False
    if min_tokens is not None and int(row.get("total_tokens") or 0) < min_tokens:
        return False
    return not (min_credits is not None and float(row.get("usage_credits") or 0) < min_credits)


def _project_summary_rows(
    *,
    db_path: Path,
    pricing: PricingConfig,
    group_by: str,
    limit: int,
    since: str | None,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
) -> list[dict[str, Any]]:
    rows = annotate_rows_with_project_identity(
        annotate_rows_with_efficiency(query_dashboard_events(db_path, limit=0, since=since), pricing),
        load_project_config(projects_path),
    )
    rows = apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if group_by == "project_tag":
            keys = row.get("project_tags") or ["untagged"]
        else:
            keys = [row.get("project_name") or "Unknown project"]
        for key in keys:
            bucket = buckets.setdefault(
                str(key),
                {
                    "group_key": str(key),
                    "model_calls": 0,
                    "sessions": set(),
                    "turns": set(),
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "uncached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "_cache_ratio_sum": 0.0,
                    "_reasoning_ratio_sum": 0.0,
                    "_context_sum": 0.0,
                    "latest_event": "",
                },
            )
            bucket["model_calls"] += 1
            bucket["sessions"].add(row.get("session_id"))
            if row.get("turn_id"):
                bucket["turns"].add(row.get("turn_id"))
            for token_key in (
                "input_tokens",
                "cached_input_tokens",
                "uncached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            ):
                bucket[token_key] += int(row.get(token_key) or 0)
            bucket["estimated_cost_usd"] += float(row.get("estimated_cost_usd") or 0)
            bucket["_cache_ratio_sum"] += float(row.get("cache_ratio") or 0)
            bucket["_reasoning_ratio_sum"] += float(row.get("reasoning_output_ratio") or 0)
            bucket["_context_sum"] += float(row.get("context_window_percent") or 0)
            if str(row.get("event_timestamp") or "") > bucket["latest_event"]:
                bucket["latest_event"] = str(row.get("event_timestamp") or "")
    summaries: list[dict[str, Any]] = []
    for bucket in buckets.values():
        calls = max(int(bucket["model_calls"]), 1)
        bucket["sessions"] = len(bucket["sessions"])
        bucket["turns"] = len(bucket["turns"])
        bucket["avg_cache_ratio"] = bucket.pop("_cache_ratio_sum") / calls
        bucket["avg_reasoning_output_ratio"] = bucket.pop("_reasoning_ratio_sum") / calls
        bucket["avg_context_window_percent"] = bucket.pop("_context_sum") / calls
        summaries.append(bucket)
    summaries.sort(key=lambda row: (-int(row["total_tokens"]), str(row["group_key"])))
    return summaries[:limit]
