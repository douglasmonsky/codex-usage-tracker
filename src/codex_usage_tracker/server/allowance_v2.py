"""Bounded HTTP adapters for allowance intelligence v2."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from codex_usage_tracker.allowance_intelligence.analysis import (
    ANALYSIS_SCHEMA,
    allowance_analysis_request,
    build_allowance_analysis,
    read_allowance_analysis,
)
from codex_usage_tracker.allowance_intelligence.service import (
    build_allowance_evidence,
    build_allowance_series,
    build_allowance_status,
)
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry, ProgressReporter
from codex_usage_tracker.server.utils import first_query_value, parse_bool_query_value
from codex_usage_tracker.store.allowance_intelligence import AllowanceCursorError
from codex_usage_tracker.store.connection import connect

JsonSender = Callable[[HTTPStatus, dict[str, object]], None]
ErrorSender = Callable[..., None]
TokenValidator = Callable[[Mapping[str, list[str]]], bool]

_AUTH_ERROR = "Valid API token is required for allowance analysis"
_MAX_CUSTOM_RANGE_DAYS = 366
_MAX_EVIDENCE_LIMIT = 500
_MAX_FORECAST_HORIZON = 12


def allowance_status_payload(
    query: str,
    *,
    db_path: Path,
    privacy_mode: str,
    include_archived_default: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    params = parse_qs(query, keep_blank_values=True)
    include_archived = _include_archived(params, include_archived_default)
    since_revision = _value(params, "since_revision")
    with connect(db_path) as connection:
        return build_allowance_status(
            connection,
            now=now or datetime.now(timezone.utc),
            privacy_mode=privacy_mode,
            include_archived=include_archived,
            since_revision=since_revision,
        )


def allowance_series_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    params = parse_qs(query, keep_blank_values=True)
    range_preset = _value(params, "range_preset") or "7d"
    start_at = _value(params, "start_at")
    end_at = _value(params, "end_at")
    _validate_custom_range(range_preset, start_at, end_at)
    with connect(db_path) as connection:
        return build_allowance_series(
            connection,
            now=now or datetime.now(timezone.utc),
            range_preset=range_preset,
            start_at=start_at,
            end_at=end_at,
            granularity=_value(params, "granularity") or "auto",
            window_kind=_window_kind(params, required=True) or "weekly",
            cohort_id=_value(params, "cohort_id"),
            include_archived=_include_archived(params, include_archived_default),
        )


def allowance_evidence_payload(
    query: str,
    *,
    db_path: Path,
    privacy_mode: str,
    include_archived_default: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    params = parse_qs(query, keep_blank_values=True)
    limit = _bounded_int(params, "limit", default=50, minimum=1, maximum=_MAX_EVIDENCE_LIMIT)
    order = _value(params, "order") or "desc"
    if order not in {"asc", "desc"}:
        raise ValueError("order must be asc or desc")
    requested_privacy = _value(params, "privacy_mode") or privacy_mode
    if requested_privacy not in {"strict", "normal", "local"}:
        raise ValueError("privacy_mode must be strict, normal, or local")
    with connect(db_path) as connection:
        return build_allowance_evidence(
            connection,
            now=now,
            privacy_mode=requested_privacy,
            limit=limit,
            cursor=_value(params, "before") or _value(params, "cursor"),
            window_kind=_window_kind(params, required=False),
            cohort_id=_value(params, "cohort_id"),
            start_at=_value(params, "start_at"),
            end_at=_value(params, "end_at"),
            order=order,
            include_archived=_include_archived(params, include_archived_default),
        )


def allowance_analysis_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
) -> dict[str, Any]:
    params = parse_qs(query, keep_blank_values=True)
    arguments = _analysis_arguments(params, include_archived_default)
    with connect(db_path) as connection:
        payload = read_allowance_analysis(connection, **arguments)
        if payload is not None:
            return payload
        request = allowance_analysis_request(connection, **arguments)
    return {
        "schema": ANALYSIS_SCHEMA,
        "status": "missing",
        "snapshot_id": request["snapshot_id"],
        "source_revision": request["source_revision"],
        "model_version": request["model_version"],
        "rate_card_revision": request["rate_card_revision"],
        "parameters": request["parameters"],
        "next": {"action": "start_analysis_job"},
    }


def handle_allowance_status_request(
    query: str,
    *,
    db_path: Path,
    privacy_mode: str,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    _send_payload(
        lambda: allowance_status_payload(
            query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            include_archived_default=include_archived_default,
        ),
        send_error=send_error,
        send_json=send_json,
    )


def handle_allowance_series_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    _send_payload(
        lambda: allowance_series_payload(
            query,
            db_path=db_path,
            include_archived_default=include_archived_default,
        ),
        send_error=send_error,
        send_json=send_json,
    )


def handle_allowance_evidence_request(
    query: str,
    *,
    db_path: Path,
    privacy_mode: str,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    try:
        payload = allowance_evidence_payload(
            query,
            db_path=db_path,
            privacy_mode=privacy_mode,
            include_archived_default=include_archived_default,
        )
    except AllowanceCursorError as error:
        if error.reason == "malformed_cursor":
            send_error(HTTPStatus.BAD_REQUEST, "Allowance evidence cursor is malformed")
            return
        send_error(
            HTTPStatus.CONFLICT,
            "Allowance evidence revision changed; restart from the newest page",
            code="allowance_revision_changed",
            next={"action": "restart_from_newest"},
        )
        return
    except ValueError as error:
        send_error(HTTPStatus.BAD_REQUEST, str(error))
        return
    send_json(HTTPStatus.OK, payload)


def handle_allowance_analysis_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    _send_payload(
        lambda: allowance_analysis_payload(
            query,
            db_path=db_path,
            include_archived_default=include_archived_default,
        ),
        send_error=send_error,
        send_json=send_json,
    )


def handle_allowance_analysis_job_start_request(
    query: str,
    *,
    db_path: Path,
    registry: AnalysisJobRegistry,
    include_archived_default: bool,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    params = parse_qs(query, keep_blank_values=True)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    try:
        payload = start_allowance_analysis_job(
            query,
            db_path=db_path,
            registry=registry,
            include_archived_default=include_archived_default,
        )
    except ValueError as error:
        send_error(HTTPStatus.BAD_REQUEST, str(error))
        return
    send_json(HTTPStatus.ACCEPTED, payload)


def start_allowance_analysis_job(
    query: str,
    *,
    db_path: Path,
    registry: AnalysisJobRegistry,
    include_archived_default: bool,
) -> dict[str, object]:
    """Start or reuse analysis work after the caller applies its auth policy."""
    params = parse_qs(query, keep_blank_values=True)
    arguments = _analysis_arguments(params, include_archived_default)
    with connect(db_path) as connection:
        request = allowance_analysis_request(connection, **arguments)

    def work(progress: ProgressReporter) -> dict[str, object]:
        progress(stage="analyzing", completed_units=0, total_units=1)
        with connect(db_path) as connection:
            result = build_allowance_analysis(connection, **arguments)
        progress(stage="persisted", completed_units=1, total_units=1)
        return {
            "analysis_schema": str(result["schema"]),
            "snapshot_id": str(result["snapshot_id"]),
            "status": str(result["status"]),
        }

    return registry.start(
        job_kind="allowance-analysis",
        request_key=f"allowance-analysis:{request['snapshot_id']}",
        source_revision=str(request["source_revision"]),
        total_units=1,
        work=work,
        reload_endpoint="/api/allowance/analysis",
    )


def handle_allowance_analysis_job_status_request(
    query: str,
    *,
    registry: AnalysisJobRegistry,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    params = parse_qs(query, keep_blank_values=True)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    job_id = _value(params, "job_id")
    if not job_id:
        send_error(HTTPStatus.BAD_REQUEST, "job_id is required")
        return
    payload = allowance_analysis_job_status(job_id, registry=registry)
    status = HTTPStatus.NOT_FOUND if payload["status"] == "missing" else HTTPStatus.OK
    send_json(status, payload)


def allowance_analysis_job_status(
    job_id: str,
    *,
    registry: AnalysisJobRegistry,
) -> dict[str, object]:
    """Return one read-only allowance analysis job view."""
    if not job_id:
        raise ValueError("job_id is required")
    return registry.status(job_id)


def _send_payload(
    build: Callable[[], dict[str, Any]],
    *,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    try:
        payload = build()
    except ValueError as error:
        send_error(HTTPStatus.BAD_REQUEST, str(error))
        return
    send_json(HTTPStatus.OK, payload)


def _analysis_arguments(
    params: Mapping[str, list[str]],
    include_archived_default: bool,
) -> dict[str, Any]:
    include_archived = _include_archived(params, include_archived_default)
    parameters: dict[str, int] = {}
    if _value(params, "min_cycles_per_side") is not None:
        parameters["min_cycles_per_side"] = _bounded_int(
            params, "min_cycles_per_side", default=3, minimum=2, maximum=100
        )
    if _value(params, "permutation_count") is not None:
        parameters["permutation_count"] = _bounded_int(
            params, "permutation_count", default=1_999, minimum=99, maximum=100_000
        )
    return {
        "rate_card_revision": _value(params, "rate_card_revision"),
        "archive_scope": "all" if include_archived else "active",
        "window_kind": _window_kind(params, required=True) or "weekly",
        "cohort_key": _value(params, "cohort_id") or "codex",
        "forecast_horizon": _bounded_int(
            params,
            "forecast_horizon",
            default=1,
            minimum=1,
            maximum=_MAX_FORECAST_HORIZON,
        ),
        "parameters": parameters or None,
    }


def _validate_custom_range(
    range_preset: str,
    start_at: str | None,
    end_at: str | None,
) -> None:
    if range_preset != "custom":
        return
    if not start_at or not end_at:
        raise ValueError("custom range requires start_at and end_at")
    start = _timestamp(start_at)
    end = _timestamp(end_at)
    if start >= end:
        raise ValueError("start_at must be before end_at")
    if end - start > timedelta(days=_MAX_CUSTOM_RANGE_DAYS):
        raise ValueError(f"custom range must not exceed {_MAX_CUSTOM_RANGE_DAYS} days")


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamps must be ISO-8601 timezone-aware values") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must be ISO-8601 timezone-aware values")
    return result


def _bounded_int(
    params: Mapping[str, list[str]],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _value(params, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _window_kind(
    params: Mapping[str, list[str]],
    *,
    required: bool,
) -> str | None:
    value = _value(params, "window_kind")
    if value is None:
        return "weekly" if required else None
    if value not in {"weekly", "five_hour"}:
        raise ValueError("window_kind must be weekly or five_hour")
    return value


def _include_archived(params: Mapping[str, list[str]], default: bool) -> bool:
    return parse_bool_query_value(_value(params, "include_archived"), default)


def _value(params: Mapping[str, list[str]], name: str) -> str | None:
    value = first_query_value(params.get(name))
    return value if value not in {None, ""} else None
