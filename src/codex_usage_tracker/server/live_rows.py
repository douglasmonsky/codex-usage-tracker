"""Live dashboard API row query and annotation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.call_origin import ensure_call_origin
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.pricing.api import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.reports.recommendations import (
    annotate_rows_with_recommendations,
    load_threshold_config,
)
from codex_usage_tracker.server.utils import matches_live_derived_filters
from codex_usage_tracker.store.api import query_usage_api_event_count, query_usage_api_events


def query_live_call_rows(
    *,
    db_path: Path,
    query_params: dict[str, Any],
    pricing_status: str | None,
    credit_confidence: str | None,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
    privacy_mode: str,
) -> tuple[list[dict[str, Any]], int]:
    """Return annotated live API rows plus the total row count for pagination."""
    derived_filter = bool(pricing_status or credit_confidence)
    rows = _query_raw_live_rows(
        db_path=db_path,
        query_params=query_params,
        derived_filter=derived_filter,
    )
    rows = annotate_live_rows(
        rows,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
    )
    if derived_filter:
        return _filter_derived_live_rows(
            rows,
            query_params=query_params,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
        )
    return rows, _query_live_total_count(db_path=db_path, query_params=query_params)


def _query_raw_live_rows(
    *,
    db_path: Path,
    query_params: dict[str, Any],
    derived_filter: bool,
) -> list[dict[str, Any]]:
    return query_usage_api_events(
        db_path=db_path,
        limit=None if derived_filter else query_params["limit"],
        offset=0 if derived_filter else query_params["offset"],
        search=query_params["search"],
        since=query_params["since"],
        until=query_params["until"],
        model=query_params["model"],
        effort=query_params["effort"],
        thread=query_params["thread"],
        thread_key=query_params["thread_key"],
        include_archived=query_params["include_archived"],
        sort=query_params["sort"],
        direction=query_params["direction"],
    )


def _filter_derived_live_rows(
    rows: list[dict[str, Any]],
    *,
    query_params: dict[str, Any],
    pricing_status: str | None,
    credit_confidence: str | None,
) -> tuple[list[dict[str, Any]], int]:
    filtered_rows = [
        row
        for row in rows
        if matches_live_derived_filters(
            row,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
        )
    ]
    total_matched = len(filtered_rows)
    limit = query_params["limit"]
    offset = query_params["offset"]
    rows_page = filtered_rows[offset:] if limit is None else filtered_rows[offset : offset + limit]
    return rows_page, total_matched


def _query_live_total_count(*, db_path: Path, query_params: dict[str, Any]) -> int:
    return query_usage_api_event_count(
        db_path=db_path,
        search=query_params["search"],
        since=query_params["since"],
        until=query_params["until"],
        model=query_params["model"],
        effort=query_params["effort"],
        thread=query_params["thread"],
        thread_key=query_params["thread_key"],
        include_archived=query_params["include_archived"],
    )


def annotate_live_rows(
    rows: list[dict[str, Any]],
    *,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
    privacy_mode: str,
) -> list[dict[str, Any]]:
    """Apply dashboard live API annotations to already queried rows."""
    if not rows:
        return []
    rows = annotate_thread_attachments([ensure_call_origin(row) for row in rows])
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(
        allowance_path,
        rate_card_path=rate_card_path,
    )
    thresholds = load_threshold_config(thresholds_path)
    projects = load_project_config(projects_path)
    rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, pricing),
        allowance,
    )
    rows = annotate_rows_with_recommendations(rows, thresholds)
    rows = annotate_rows_with_project_identity(rows, projects)
    return apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)
