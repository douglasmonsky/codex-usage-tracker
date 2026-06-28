"""Recommendation payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.reports import build_recommendations_report
from codex_usage_tracker.server_utils import (
    first_query_value,
    parse_optional_float,
    parse_report_limit,
)


def recommendations_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path,
    privacy_mode: str,
) -> dict[str, object]:
    """Build the recommendations API payload."""
    params = parse_qs(query)
    report = build_recommendations_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
        thread=first_query_value(params.get("thread")),
        project=first_query_value(params.get("project")),
        min_score=parse_optional_float(first_query_value(params.get("min_score")), "min_score"),
        limit=parse_report_limit(first_query_value(params.get("limit")), 20),
        privacy_mode=privacy_mode,
    )
    payload = dict(report.payload)
    payload["raw_context_included"] = False
    return payload
