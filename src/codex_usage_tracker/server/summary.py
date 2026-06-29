"""Summary payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.reports.api import build_summary_report
from codex_usage_tracker.server.utils import first_query_value, parse_report_limit

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_summary_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    projects_path: Path,
    privacy_mode: str,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle summary route errors and response writing."""
    try:
        payload = summary_payload(
            query,
            db_path=db_path,
            pricing_path=pricing_path,
            projects_path=projects_path,
            privacy_mode=privacy_mode,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading summary", exc)
        return
    send_json(HTTPStatus.OK, payload)


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
