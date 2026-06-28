"""Summary payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.reports import build_summary_report
from codex_usage_tracker.server_utils import first_query_value, parse_report_limit


def summary_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    projects_path: Path,
    privacy_mode: str,
) -> dict[str, object]:
    """Build the summary API payload."""
    params = parse_qs(query)
    report = build_summary_report(
        db_path=db_path,
        pricing_path=pricing_path,
        group_by=first_query_value(params.get("group_by")) or "thread",
        limit=parse_report_limit(first_query_value(params.get("limit")), 20),
        preset=first_query_value(params.get("preset")),
        since=first_query_value(params.get("since")),
        projects_path=projects_path,
        privacy_mode=privacy_mode,
    )
    payload = report.payload()
    payload["raw_context_included"] = False
    return payload
