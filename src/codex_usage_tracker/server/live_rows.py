"""Live dashboard API row query and annotation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.call_origin import ensure_call_origin
from codex_usage_tracker.core.projects import (
    annotate_rows_with_project_identity,
    apply_project_privacy_to_rows,
    load_project_config,
    project_identity_for_cwd,
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
from codex_usage_tracker.store.api import (
    query_usage_api_distinct_cwds,
    query_usage_api_event_count,
    query_usage_api_events,
)


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
    git_cwds = (
        _git_cwds_for_scope(
            db_path=db_path,
            query_params=query_params,
            projects_path=projects_path,
        )
        if query_params["source"] == "git"
        else None
    )
    rows = _query_raw_live_rows(
        db_path=db_path,
        query_params=query_params,
        cwds=git_cwds,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
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
    return rows, _query_live_total_count(
        db_path=db_path,
        query_params=query_params,
        cwds=git_cwds,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )


def _query_raw_live_rows(
    *,
    db_path: Path,
    query_params: dict[str, Any],
    cwds: list[str] | None,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> list[dict[str, Any]]:
    return query_usage_api_events(
        db_path=db_path,
        limit=query_params["limit"],
        offset=query_params["offset"],
        search=query_params["search"],
        since=query_params["since"],
        until=query_params["until"],
        model=query_params["model"],
        effort=query_params["effort"],
        source=None if cwds is not None else query_params["source"],
        cwds=cwds,
        thread=query_params["thread"],
        thread_key=query_params["thread_key"],
        include_archived=query_params["include_archived"],
        sort=query_params["sort"],
        direction=query_params["direction"],
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        legacy_archive_path_fallback=False,
    )


def _git_cwds_for_scope(
    *,
    db_path: Path,
    query_params: dict[str, Any],
    projects_path: Path,
) -> list[str]:
    projects = load_project_config(projects_path)
    cwds = query_usage_api_distinct_cwds(
        db_path=db_path,
        search=query_params["search"],
        since=query_params["since"],
        until=query_params["until"],
        model=query_params["model"],
        effort=query_params["effort"],
        thread=query_params["thread"],
        thread_key=query_params["thread_key"],
        include_archived=query_params["include_archived"],
        legacy_archive_path_fallback=False,
    )
    return [
        cwd
        for cwd in cwds
        if any(
            project_identity_for_cwd(cwd, projects).get(key)
            for key in ("git_branch", "git_remote_label", "git_remote_hash")
        )
    ]


def _query_live_total_count(
    *,
    db_path: Path,
    query_params: dict[str, Any],
    cwds: list[str] | None,
    pricing_status: str | None,
    credit_confidence: str | None,
) -> int:
    return query_usage_api_event_count(
        db_path=db_path,
        search=query_params["search"],
        since=query_params["since"],
        until=query_params["until"],
        model=query_params["model"],
        effort=query_params["effort"],
        source=None if cwds is not None else query_params["source"],
        cwds=cwds,
        thread=query_params["thread"],
        thread_key=query_params["thread_key"],
        include_archived=query_params["include_archived"],
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        legacy_archive_path_fallback=False,
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
