"""Allowance intelligence payload helpers dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_diagnostics_report,
    build_allowance_export_report,
    build_allowance_history_report,
)
from codex_usage_tracker.server.query_cache import (
    AggregateQueryCache,
    cached_aggregate_payload,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
    parse_report_limit,
)

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def new_query_cache() -> AggregateQueryCache:
    return AggregateQueryCache(max_entries=4, max_payload_bytes=8 * 1_024 * 1_024)


def handle_allowance_history_request(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
    query_cache: AggregateQueryCache | None = None,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle normalized allowance history route."""

    try:
        payload = cached_aggregate_payload(
            query_cache,
            route="/api/allowance/history",
            query=query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            dependencies=(allowance_path, rate_card_path),
            build=lambda: allowance_history_payload(
                query,
                db_path=db_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                include_archived_default=include_archived_default,
                privacy_mode=privacy_mode,
            ),
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading allowance history", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_allowance_diagnostics_request(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
    query_cache: AggregateQueryCache | None = None,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle evidence-graded allowance diagnostics route."""

    try:
        payload = cached_aggregate_payload(
            query_cache,
            route="/api/allowance/diagnostics",
            query=query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            dependencies=(allowance_path, rate_card_path),
            build=lambda: allowance_diagnostics_payload(
                query,
                db_path=db_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                include_archived_default=include_archived_default,
                privacy_mode=privacy_mode,
            ),
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while allowance diagnostics", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_allowance_export_request(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle strict-privacy allowance evidence export route."""

    try:
        payload = allowance_export_payload(
            query,
            db_path=db_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived_default=include_archived_default,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while exporting allowance evidence", exc)
        return
    send_json(HTTPStatus.OK, payload)


def allowance_history_payload(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
) -> dict[str, object]:
    """Build normalized allowance history API payload."""

    params = parse_qs(query)
    report = build_allowance_history_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=_include_archived(params, include_archived_default),
        window_kind=first_query_value(params.get("window_kind")),
        limit=parse_report_limit(first_query_value(params.get("limit")), 1000),
        privacy_mode=first_query_value(params.get("privacy_mode")) or privacy_mode,
    )
    return report.payload


def allowance_diagnostics_payload(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    privacy_mode: str,
) -> dict[str, object]:
    """Build allowance diagnostics API payload."""

    params = parse_qs(query)
    report = build_allowance_diagnostics_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=_include_archived(params, include_archived_default),
        window_kind=first_query_value(params.get("window_kind")),
        limit=parse_report_limit(first_query_value(params.get("limit")), 10_000),
        privacy_mode=first_query_value(params.get("privacy_mode")) or privacy_mode,
    )
    return report.payload


def allowance_export_payload(
    query: str,
    *,
    db_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
) -> dict[str, object]:
    """Build strict-privacy allowance evidence export API payload."""

    params = parse_qs(query)
    report = build_allowance_export_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=_include_archived(params, include_archived_default),
        window_kind=first_query_value(params.get("window_kind")),
        limit=parse_report_limit(first_query_value(params.get("limit")), 10_000),
    )
    return report.payload


def _include_archived(params: dict[str, list[str]], include_archived_default: bool) -> bool:
    return parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
