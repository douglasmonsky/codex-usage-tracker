"""Usage dashboard API payload helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from functools import partial
from http import HTTPStatus
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs

from codex_usage_tracker.application.refresh import refresh_usage
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.jobs import JobService
from codex_usage_tracker.jobs.models import JobStatusV1
from codex_usage_tracker.recommendation_engine.api import refresh_usage_index
from codex_usage_tracker.server.utils import (
    elapsed_ms,
    first_query_value,
    parse_bool_query_value,
    parse_dashboard_limit,
    parse_dashboard_offset,
    truthy_query_value,
    utc_now,
)


class UsageRefreshAuthError(PermissionError):
    """Raised when a live usage refresh lacks a valid dashboard token."""


ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
TokenValidator = Callable[[dict[str, list[str]]], bool]


class RefreshJobRegistry:
    """Compatibility adapter over the shared semantic refresh job service."""

    def __init__(self, *, job_service: JobService | None = None) -> None:
        self.job_service = job_service or JobService()

    def start_refresh(
        self,
        *,
        codex_home: Path,
        db_path: Path,
        pricing_path: Path = DEFAULT_PRICING_PATH,
        allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
        rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
        thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
        include_archived: bool,
        aggregate_only: bool,
        refresh_lock: Any,
    ) -> dict[str, object]:
        del refresh_lock  # Compatibility parameter; semantic jobs own refresh coordination.
        request = RefreshRequest(
            history="all" if include_archived else "active",
            aggregate_only=aggregate_only,
            execution="async",
        )
        outcome = refresh_usage(
            request,
            codex_home=codex_home,
            db_path=db_path,
            pricing_path=pricing_path,
            job_service=self.job_service,
            refresh_fn=partial(
                refresh_usage_index,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                rate_card_path=rate_card_path,
                thresholds_path=thresholds_path,
            ),
        )
        if outcome.job is None:
            raise RuntimeError("asynchronous dashboard refresh did not register a job")
        return _legacy_refresh_job_payload(outcome.job, include_result=False)

    def status(self, job_id: str) -> dict[str, object]:
        status = self.job_service.status(job_id, include_result=True)
        if status.stage == "not_found":
            return {
                "schema": "codex-usage-tracker-refresh-job-v1",
                "job_id": job_id,
                "status": "missing",
                "error": "Unknown refresh job_id.",
            }
        return _legacy_refresh_job_payload(status, include_result=True)


def _legacy_refresh_job_payload(
    status: JobStatusV1,
    *,
    include_result: bool,
) -> dict[str, object]:
    state = "running" if status.state == "queued" else status.state
    payload: dict[str, object] = {
        "schema": "codex-usage-tracker-refresh-job-v1",
        "job_id": status.job_id,
        "status": state,
        "started_at": status.created_at,
        "updated_at": status.updated_at,
        "progress": {
            "schema": "codex-usage-tracker-refresh-progress-v1",
            "phase": status.stage,
            "status": state,
            "message": f"Refresh {status.stage.replace('_', ' ')}",
            "completed": status.progress_percent,
            "total": 100,
            "percent": float(status.progress_percent),
        },
    }
    if status.completed_at is not None:
        payload["finished_at"] = status.completed_at
    if status.error is not None:
        payload["error"] = status.error.message
    if include_result and status.result is not None:
        result = status.result
        if isinstance(result, Mapping):
            refresh = result.get("refresh")
            payload["result"] = dict(refresh) if isinstance(refresh, Mapping) else dict(result)
    return payload


def handle_refresh_job_start_request(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
    include_archived_default: bool,
    refresh_lock: Any,
    refresh_jobs: RefreshJobRegistry,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    """Start an async refresh job and return its initial status."""
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, "Valid API token is required for refresh")
        return
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")), include_archived_default
    )
    aggregate_only = parse_bool_query_value(first_query_value(params.get("aggregate_only")), False)
    payload = refresh_jobs.start_refresh(
        codex_home=codex_home,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        refresh_lock=refresh_lock,
    )
    send_json(HTTPStatus.ACCEPTED, payload)


def handle_refresh_job_status_request(
    query: str,
    *,
    refresh_jobs: RefreshJobRegistry,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    """Return async refresh job progress/result."""
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, "Valid API token is required for refresh")
        return
    job_id = first_query_value(params.get("job_id"))
    if not job_id:
        send_error(HTTPStatus.BAD_REQUEST, "job_id is required")
        return
    send_json(HTTPStatus.OK, refresh_jobs.status(job_id))


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
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
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
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
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
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
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
    diagnostics_enabled = parse_bool_query_value(
        first_query_value(params.get("diagnostics")), False
    )
    shell_only = parse_bool_query_value(first_query_value(params.get("shell")), False)
    requested_since = first_query_value(params.get("since"))
    effective_since = requested_since or since
    requested_load_window = first_query_value(params.get("load_window"))
    if requested_load_window and requested_load_window not in {"day", "week", "rows", "all"}:
        raise ValueError("load_window must be one of: day, week, rows, all")
    refresh_result = None
    refresh_ms: float | None = None

    if truthy_query_value(first_query_value(params.get("refresh"))):
        if not refresh_allowed:
            raise UsageRefreshAuthError("Valid API token is required for refresh")
        refresh_result, refresh_ms = refresh_usage_payload(
            codex_home=codex_home,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            rate_card_path=rate_card_path,
            thresholds_path=thresholds_path,
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
        since=effective_since,
        api_token=api_token,
        context_api_enabled=context_api_enabled,
        include_archived=include_archived,
        language=language,
        include_rows=not shell_only,
        load_window=requested_load_window,
    )
    dashboard_payload_ms = elapsed_ms(payload_started)
    payload["refreshed_at"] = utc_now()
    payload["refresh_result"] = refresh_result

    if diagnostics_enabled:
        payload_rows = payload.get("rows")
        diagnostic_payload: dict[str, object] = {
            "dashboard_payload_ms": dashboard_payload_ms,
            "rows_returned": len(payload_rows) if isinstance(payload_rows, list) else 0,
            "include_archived": include_archived,
            "limit": limit,
            "offset": offset,
            "since": effective_since,
            "load_window": payload.get("load_window"),
        }
        if refresh_ms is not None:
            diagnostic_payload["refresh_ms"] = refresh_ms
        payload["diagnostics"] = diagnostic_payload
    return payload
