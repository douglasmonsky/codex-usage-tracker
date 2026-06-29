"""Usage dashboard API payload helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs

from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.server.utils import (
    elapsed_ms,
    first_query_value,
    parse_bool_query_value,
    parse_dashboard_limit,
    parse_dashboard_offset,
    truthy_query_value,
    utc_now,
)
from codex_usage_tracker.store.api import refresh_usage_index


class UsageRefreshAuthError(PermissionError):
    """Raised when a live usage refresh lacks a valid dashboard token."""


ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
TokenValidator = Callable[[dict[str, list[str]]], bool]


def handle_usage_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
    privacy_mode: str,
    since: str | None,
    api_token: str,
    context_api_enabled: bool,
    include_archived_default: bool,
    language_default: str,
    limit_default: int,
    codex_home: Path,
    refresh_lock: Any,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle usage route errors and response writing."""
    params = parse_qs(query)
    try:
        payload = usage_payload(
            query,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
            projects_path=projects_path,
            privacy_mode=privacy_mode,
            since=since,
            api_token=api_token,
            context_api_enabled=context_api_enabled,
            include_archived_default=include_archived_default,
            language_default=language_default,
            limit_default=limit_default,
            codex_home=codex_home,
            refresh_lock=refresh_lock,
            refresh_allowed=has_valid_api_token(params),
        )
    except UsageRefreshAuthError as exc:
        send_error(HTTPStatus.FORBIDDEN, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading usage data", exc)
        return
    except OSError as exc:
        send_exception("Could not read aggregate dashboard data", exc)
        return
    send_json(HTTPStatus.OK, payload)


def refresh_usage_payload(
    *,
    codex_home: Path,
    db_path: Path,
    include_archived: bool,
    refresh_lock: Any,
) -> tuple[dict[str, object], float]:
    """Refresh the usage index and return the live API refresh payload."""
    refresh_started = perf_counter()
    with refresh_lock:
        result = refresh_usage_index(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=include_archived,
        )
    return (
        {
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "skipped_events": result.skipped_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "db_path": result.db_path,
            "parser_diagnostics": result.parser_diagnostics,
            "include_archived": include_archived,
        },
        elapsed_ms(refresh_started),
    )


def usage_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    thresholds_path: Path,
    projects_path: Path,
    privacy_mode: str,
    since: str | None,
    api_token: str,
    context_api_enabled: bool,
    include_archived_default: bool,
    language_default: str,
    limit_default: int,
    codex_home: Path,
    refresh_lock: Any,
    refresh_allowed: bool,
) -> dict[str, object]:
    """Build the live usage dashboard payload from query parameters."""
    params = parse_qs(query)
    limit = parse_dashboard_limit(first_query_value(params.get("limit")), limit_default)
    offset = parse_dashboard_offset(first_query_value(params.get("offset")))
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    language = normalize_language(first_query_value(params.get("lang")) or language_default)
    diagnostics_enabled = parse_bool_query_value(first_query_value(params.get("diagnostics")), False)
    shell_only = parse_bool_query_value(first_query_value(params.get("shell")), False)
    refresh_result = None
    refresh_ms: float | None = None

    if truthy_query_value(first_query_value(params.get("refresh"))):
        if not refresh_allowed:
            raise UsageRefreshAuthError("Valid API token is required for refresh")
        refresh_result, refresh_ms = refresh_usage_payload(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=include_archived,
            refresh_lock=refresh_lock,
        )

    payload_started = perf_counter()
    payload = dashboard_payload(
        db_path=db_path,
        limit=limit,
        offset=offset,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=projects_path,
        privacy_mode=privacy_mode,
        since=since,
        api_token=api_token,
        context_api_enabled=context_api_enabled,
        include_archived=include_archived,
        language=language,
        include_rows=not shell_only,
    )
    dashboard_payload_ms = elapsed_ms(payload_started)
    payload["refreshed_at"] = utc_now()
    payload["refresh_result"] = refresh_result

    if diagnostics_enabled:
        diagnostic_payload: dict[str, object] = {
            "dashboard_payload_ms": dashboard_payload_ms,
            "rows_returned": len(payload.get("rows") or []),
            "include_archived": include_archived,
            "limit": limit,
            "offset": offset,
        }
        if refresh_ms is not None:
            diagnostic_payload["refresh_ms"] = refresh_ms
        payload["diagnostics"] = diagnostic_payload
    return payload
