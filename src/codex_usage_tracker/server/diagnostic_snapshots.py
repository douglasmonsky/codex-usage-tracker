"""Diagnostic snapshot payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs

from codex_usage_tracker.diagnostics.snapshots import (
    build_diagnostic_usage_drain_report,
    refresh_diagnostic_snapshots,
)
from codex_usage_tracker.server.utils import first_query_value, parse_bool_query_value


class SnapshotReport(Protocol):
    payload: dict[str, object]


class SnapshotReportBuilder(Protocol):
    def __call__(
        self,
        *,
        db_path: Path,
        include_archived: bool,
        refresh: bool,
    ) -> SnapshotReport: ...


JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
ProgressCallback = Callable[..., None]
ExceptionSender = Callable[[str, BaseException], None]
RefreshAuthRejector = Callable[[dict[str, list[str]]], bool]


def handle_diagnostic_refresh_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    refresh_lock: Any,
    reject_missing_refresh_token: RefreshAuthRejector,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle the all-diagnostics refresh route."""
    params = parse_qs(query)
    if reject_missing_refresh_token(params):
        return
    try:
        payload = diagnostic_refresh_payload(
            query,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived_default=include_archived_default,
            refresh_lock=refresh_lock,
        )
    except sqlite3.Error as exc:
        send_exception("Database error while refreshing diagnostics", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_diagnostic_snapshot_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    refresh: bool,
    refresh_lock: Any,
    build_report: SnapshotReportBuilder,
    label: str,
    reject_missing_refresh_token: RefreshAuthRejector,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle one persisted diagnostic snapshot route."""
    params = parse_qs(query)
    if refresh and reject_missing_refresh_token(params):
        return
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    try:
        payload = diagnostic_snapshot_payload(
            db_path=db_path,
            include_archived=include_archived,
            refresh=refresh,
            refresh_lock=refresh_lock,
            build_report=build_report,
        )
    except sqlite3.Error as exc:
        send_exception(f"Database error while reading {label}", exc)
        return
    send_json(HTTPStatus.OK, payload)


def handle_usage_drain_snapshot_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    refresh: bool,
    refresh_lock: Any,
    reject_missing_refresh_token: RefreshAuthRejector,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle diagnostic usage-drain snapshot route."""
    params = parse_qs(query)
    if refresh and reject_missing_refresh_token(params):
        return
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    try:
        payload = usage_drain_snapshot_payload(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived=include_archived,
            refresh=refresh,
            refresh_lock=refresh_lock,
        )
    except sqlite3.Error as exc:
        send_exception("Database error while reading diagnostic usage drain", exc)
        return
    send_json(HTTPStatus.OK, payload)


def refresh_all_diagnostic_snapshots_payload(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
    refresh_lock: Any,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Refresh every diagnostic snapshot and return the aggregate payload."""
    with refresh_lock:
        return refresh_diagnostic_snapshots(
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            include_archived=include_archived,
            progress_callback=progress_callback,
        )


def diagnostic_refresh_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived_default: bool,
    refresh_lock: Any,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Refresh all diagnostic snapshots using dashboard query defaults."""
    params = parse_qs(query)
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    return refresh_all_diagnostic_snapshots_payload(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        refresh_lock=refresh_lock,
        progress_callback=progress_callback,
    )


def diagnostic_snapshot_payload(
    *,
    db_path: Path,
    include_archived: bool,
    refresh: bool,
    refresh_lock: Any,
    build_report: SnapshotReportBuilder,
) -> dict[str, object]:
    """Read or refresh one persisted diagnostic snapshot payload."""
    if refresh:
        with refresh_lock:
            return build_report(
                db_path=db_path,
                include_archived=include_archived,
                refresh=True,
            ).payload
    return build_report(
        db_path=db_path,
        include_archived=include_archived,
        refresh=False,
    ).payload


def usage_drain_snapshot_payload(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    rate_card_path: Path,
    include_archived: bool,
    refresh: bool,
    refresh_lock: Any,
) -> dict[str, object]:
    """Read or refresh the usage-drain diagnostic snapshot payload."""
    if refresh:
        with refresh_lock:
            return build_diagnostic_usage_drain_report(
                db_path=db_path,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                include_archived=include_archived,
                refresh=True,
            ).payload
    return build_diagnostic_usage_drain_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        refresh=False,
    ).payload
