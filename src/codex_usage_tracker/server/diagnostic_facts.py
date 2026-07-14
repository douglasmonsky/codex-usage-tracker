"""Diagnostic fact payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.diagnostics.reports import (
    build_diagnostics_fact_calls_report,
    build_diagnostics_facts_report,
    build_diagnostics_summary_report,
)
from codex_usage_tracker.server.query_cache import (
    AggregateQueryCache,
    cached_aggregate_payload,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_api_offset,
    parse_bool_query_value,
    parse_report_limit,
    safe_int,
)

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_diagnostics_summary_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle diagnostic summary route errors and response writing."""
    try:
        payload = diagnostics_summary_payload(
            query,
            db_path=db_path,
            include_archived_default=include_archived_default,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading diagnostics", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_diagnostics_facts_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    request_path: str,
    fact_type: str | None,
    fact_group: str | None,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
    privacy_mode: str = "normal",
    query_cache: AggregateQueryCache | None = None,
) -> None:
    """Handle diagnostic fact-list route errors and response writing."""
    try:
        payload = cached_aggregate_payload(
            query_cache,
            route=request_path,
            query=query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            dependencies=(),
            build=lambda: diagnostics_facts_payload(
                query,
                db_path=db_path,
                include_archived_default=include_archived_default,
                request_path=request_path,
                fact_type=fact_type,
                fact_group=fact_group,
            ),
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading diagnostics", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_diagnostics_fact_calls_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle diagnostic fact-call route errors and response writing."""
    try:
        payload = diagnostic_fact_calls_payload(
            query,
            db_path=db_path,
            include_archived_default=include_archived_default,
            privacy_mode=privacy_mode,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading diagnostic calls", exc)
        return
    send_json(HTTPStatus.OK, payload)


def diagnostics_summary_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
) -> dict[str, object]:
    """Build the call-level diagnostic summary API payload."""
    params = parse_qs(query)
    return build_diagnostics_summary_report(
        db_path=db_path,
        limit=parse_report_limit(first_query_value(params.get("limit")), 20),
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
        thread=first_query_value(params.get("thread")),
        min_tokens=_diagnostic_optional_int_query(params, "min_tokens"),
        fact_type=first_query_value(params.get("fact_type")),
        fact_name=first_query_value(params.get("fact_name")),
        fact_category=first_query_value(params.get("fact_category")),
        include_archived=_include_archived(params, include_archived_default),
        sort=first_query_value(params.get("sort")) or "uncached",
        direction=first_query_value(params.get("direction")) or "desc",
    ).payload


def diagnostics_facts_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    request_path: str,
    fact_type: str | None = None,
    fact_group: str | None = None,
) -> dict[str, object]:
    """Build the diagnostic facts API payload."""
    params = parse_qs(query)
    return build_diagnostics_facts_report(
        db_path=db_path,
        limit=parse_report_limit(first_query_value(params.get("limit")), 50),
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
        thread=first_query_value(params.get("thread")),
        min_tokens=_diagnostic_optional_int_query(params, "min_tokens"),
        fact_type=fact_type or first_query_value(params.get("fact_type")),
        fact_name=first_query_value(params.get("fact_name")),
        fact_category=first_query_value(params.get("fact_category")),
        include_archived=_include_archived(params, include_archived_default),
        sort=first_query_value(params.get("sort")) or "uncached",
        direction=first_query_value(params.get("direction")) or "desc",
        fact_group=fact_group,
        view=request_path.rsplit("/", 1)[-1],
    ).payload


def diagnostic_fact_calls_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
) -> dict[str, object]:
    """Build the diagnostic calls API payload for one fact."""
    params = parse_qs(query)
    fact_type = first_query_value(params.get("fact_type"))
    fact_name = first_query_value(params.get("fact_name"))
    if not fact_type or not fact_name:
        raise ValueError("fact_type and fact_name are required")
    return build_diagnostics_fact_calls_report(
        db_path=db_path,
        fact_type=fact_type,
        fact_name=fact_name,
        limit=parse_report_limit(first_query_value(params.get("limit")), 50),
        offset=parse_api_offset(first_query_value(params.get("offset"))),
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
        thread=first_query_value(params.get("thread")),
        min_tokens=_diagnostic_optional_int_query(params, "min_tokens"),
        include_archived=_include_archived(params, include_archived_default),
        sort=first_query_value(params.get("sort")) or "tokens",
        direction=first_query_value(params.get("direction")) or "desc",
        privacy_mode=privacy_mode,
    ).payload


def _diagnostic_optional_int_query(
    params: dict[str, list[str]],
    key: str,
) -> int | None:
    value = first_query_value(params.get(key))
    return None if value is None else safe_int(value)


def _include_archived(params: dict[str, list[str]], default: bool) -> bool:
    return parse_bool_query_value(first_query_value(params.get("include_archived")), default)
