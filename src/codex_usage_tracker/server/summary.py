"""Summary payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.reports.api import build_summary_report
from codex_usage_tracker.server.query_cache import (
    AggregateQueryCache,
    cached_aggregate_payload,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_api_limit,
    parse_bool_query_value,
)

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]

_MAX_CACHEABLE_GROUPS = 1_000
_RELATIVE_DATE_PRESETS = frozenset({"today", "last-7-days"})


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
    query_cache: AggregateQueryCache | None = None,
) -> None:
    """Handle summary route errors and response writing."""
    try:
        cacheable, semantic_inputs = _summary_cache_policy(query)
        payload = cached_aggregate_payload(
            query_cache,
            route="/api/summary",
            query=query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            dependencies=(pricing_path, projects_path),
            semantic_inputs=semantic_inputs,
            cacheable=cacheable,
            build=lambda: summary_payload(
                query,
                db_path=db_path,
                pricing_path=pricing_path,
                projects_path=projects_path,
                privacy_mode=privacy_mode,
            ),
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading summary", exc)
        return
    send_json(HTTPStatus.OK, payload)


def _summary_cache_policy(query: str) -> tuple[bool, tuple[tuple[str, str], ...]]:
    params = parse_qs(query)
    group_by = first_query_value(params.get("group_by")) or "thread"
    limit = parse_api_limit(first_query_value(params.get("limit")), 20)
    preset = first_query_value(params.get("preset"))
    semantic_inputs = (
        (("calendar_date", _current_calendar_date()),) if preset in _RELATIVE_DATE_PRESETS else ()
    )
    cacheable = group_by == "date" or (limit is not None and limit <= _MAX_CACHEABLE_GROUPS)
    return cacheable, semantic_inputs


def _current_calendar_date() -> str:
    return date.today().isoformat()


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
        limit=parse_api_limit(first_query_value(params.get("limit")), 20),
        preset=first_query_value(params.get("preset")),
        since=first_query_value(params.get("since")),
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        include_archived=parse_bool_query_value(
            first_query_value(params.get("include_archived")),
            False,
        ),
    )
    payload = report.payload()
    payload["raw_context_included"] = False
    return payload
