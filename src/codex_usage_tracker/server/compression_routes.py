"""Dashboard adapters for the persistent Compression Lab application API."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from codex_usage_tracker.compression.api import (
    compression_profile,
    compression_status,
    start_compression_analysis,
)
from codex_usage_tracker.compression.jobs import CompressionJobRegistry
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.payloads import compression_error_payload
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
)

TokenValidator = Callable[[dict[str, list[str]]], bool]
ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]

_AUTH_ERROR = "Valid API token is required for Compression Lab"


class CompressionRouteMixin:
    """Bind Compression Lab application services to dashboard route methods."""

    if TYPE_CHECKING:
        _db_path: Path
        _include_archived: bool
        _compression_jobs: CompressionJobRegistry

        def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool: ...

        def _send_error(self, status: HTTPStatus, message: str) -> None: ...

        def _send_exception(self, prefix: str, exc: BaseException) -> None: ...

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None: ...

    def _handle_compression_start(self, query: str) -> None:
        handle_compression_start_request(
            query,
            db_path=self._db_path,
            registry=self._compression_jobs,
            include_archived_default=self._include_archived,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_compression_status(self, query: str) -> None:
        handle_compression_status_request(
            query,
            db_path=self._db_path,
            registry=self._compression_jobs,
            include_archived_default=self._include_archived,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )

    def _handle_compression_profile(self, query: str) -> None:
        handle_compression_profile_request(
            query,
            db_path=self._db_path,
            registry=self._compression_jobs,
            include_archived_default=self._include_archived,
            has_valid_api_token=self._has_valid_api_token,
            send_error=self._send_error,
            send_exception=self._send_exception,
            send_json=self._send_json,
        )


def compression_scope_from_query(
    query: str,
    *,
    include_archived_default: bool,
) -> CompressionScope:
    """Parse one reproducible Compression Lab scope from dashboard query state."""
    params = parse_qs(query)
    return CompressionScope(
        since=first_query_value(params.get("since")),
        until=first_query_value(params.get("until")),
        thread=first_query_value(params.get("thread")),
        include_archived=parse_bool_query_value(
            first_query_value(params.get("include_archived")),
            include_archived_default,
        ),
        model=first_query_value(params.get("model")),
        effort=first_query_value(params.get("effort")),
    )


def handle_compression_start_request(
    query: str,
    *,
    db_path: Path,
    registry: CompressionJobRegistry,
    include_archived_default: bool,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Start or reuse one persistent Compression Lab run."""
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    scope = compression_scope_from_query(
        query,
        include_archived_default=include_archived_default,
    )
    detector_families = _detector_families(params.get("detector_family"))
    refresh = parse_bool_query_value(first_query_value(params.get("refresh")), False)
    try:
        payload = start_compression_analysis(
            db_path,
            scope,
            detector_families=detector_families,
            refresh=refresh,
            registry=registry,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        if _database_is_busy(exc):
            payload = compression_error_payload(
                kind="status",
                code="compression_database_busy",
                message=(
                    "Usage data is refreshing; Compression Lab will retry when the index is ready."
                ),
                next_tool="usage_compression_start",
            )
            payload["next"]["poll_after_ms"] = 1_000
            send_json(HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return
        send_exception("Database error while starting Compression Lab", exc)
        return
    send_json(HTTPStatus.ACCEPTED, payload)


def handle_compression_status_request(
    query: str,
    *,
    db_path: Path,
    registry: CompressionJobRegistry,
    include_archived_default: bool,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Read one persistent Compression Lab status without starting work."""
    del include_archived_default
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    run_id = first_query_value(params.get("run_id"))
    if not run_id:
        send_error(HTTPStatus.BAD_REQUEST, "run_id is required")
        return
    try:
        payload = compression_status(db_path, run_id=run_id, registry=registry)
    except sqlite3.Error as exc:
        send_exception("Database error while reading Compression Lab status", exc)
        return
    send_json(_compression_http_status(payload), payload)


def handle_compression_profile_request(
    query: str,
    *,
    db_path: Path,
    registry: CompressionJobRegistry,
    include_archived_default: bool,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Read the exact compact profile shared with MCP consumers."""
    del registry
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    run_id = first_query_value(params.get("run_id"))
    scope = compression_scope_from_query(
        query,
        include_archived_default=include_archived_default,
    )
    detector_families = _detector_families(params.get("detector_family"))
    try:
        payload = compression_profile(
            db_path,
            run_id=run_id,
            scope=None if run_id else scope,
            detector_families=detector_families,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading Compression Lab profile", exc)
        return
    send_json(_compression_http_status(payload), payload)


def _detector_families(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if not values:
        return None
    families = tuple(value.strip() for value in values if value.strip())
    return families or None


def _compression_http_status(payload: dict[str, object]) -> HTTPStatus:
    error = payload.get("error")
    if not isinstance(error, dict):
        return HTTPStatus.OK
    code = str(error.get("code") or "")
    if not code:
        return HTTPStatus.OK
    if code == "compression_run_not_found":
        return HTTPStatus.NOT_FOUND
    if code == "compression_run_not_complete":
        return HTTPStatus.CONFLICT
    return HTTPStatus.BAD_REQUEST


def _database_is_busy(exc: sqlite3.Error) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message
