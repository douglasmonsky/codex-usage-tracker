"""Asynchronous diagnostic refresh adapters for the localhost dashboard."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.server.analysis_jobs import (
    AnalysisJobRegistry,
    ProgressReporter,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
)
from codex_usage_tracker.store.compression_schema import (
    read_compression_source_generation,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

DiagnosticWork = Callable[[bool, ProgressReporter], Mapping[str, object] | None]
TokenValidator = Callable[[dict[str, list[str]]], bool]
ErrorSender = Callable[[HTTPStatus, str], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]

_AUTH_ERROR = "Valid API token is required for diagnostic refresh"


def handle_diagnostic_job_start_request(
    query: str,
    *,
    db_path: Path,
    job_name: str,
    total_units: int,
    work: DiagnosticWork,
    registry: AnalysisJobRegistry,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
    include_archived_default: bool = False,
) -> None:
    """Start or reuse one diagnostic refresh without blocking the request."""
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    source_revision = _source_revision(db_path)
    request_key = f"diagnostics:{source_revision}:{int(include_archived)}:{job_name}"
    payload = registry.start(
        job_kind="diagnostic-refresh",
        request_key=request_key,
        source_revision=source_revision,
        total_units=total_units,
        work=lambda progress: work(include_archived, progress),
    )
    send_json(HTTPStatus.ACCEPTED, payload)


def handle_diagnostic_job_status_request(
    query: str,
    *,
    registry: AnalysisJobRegistry,
    has_valid_api_token: TokenValidator,
    send_error: ErrorSender,
    send_json: JsonSender,
) -> None:
    """Return compact read-only progress for one diagnostic refresh."""
    params = parse_qs(query)
    if not has_valid_api_token(params):
        send_error(HTTPStatus.FORBIDDEN, _AUTH_ERROR)
        return
    job_id = first_query_value(params.get("job_id"))
    if not job_id:
        send_error(HTTPStatus.BAD_REQUEST, "job_id is required")
        return
    payload = registry.status(job_id)
    status = HTTPStatus.NOT_FOUND if payload["status"] == "missing" else HTTPStatus.OK
    send_json(status, payload)


def _source_revision(db_path: Path) -> str:
    with connect(db_path) as conn:
        init_db(conn)
        generation = read_compression_source_generation(conn)
    return f"generation:{generation}"
