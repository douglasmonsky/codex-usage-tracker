"""HTTP response helpers for the local dashboard server."""

from __future__ import annotations

from http import HTTPStatus
from time import perf_counter
from typing import Any, Protocol

from codex_usage_tracker.server.request_timing import server_timing_header
from codex_usage_tracker.server.utils import json_response_body


class ResponseHandler(Protocol):
    """Small protocol covering SimpleHTTPRequestHandler response methods."""

    wfile: Any

    def send_response(self, code: int | HTTPStatus) -> None: ...

    def send_header(self, keyword: str, value: str) -> None: ...

    def end_headers(self) -> None: ...


def send_html_response(handler: ResponseHandler, body: bytes) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write_response_body(handler, body)


def send_json_response(
    handler: ResponseHandler,
    status: HTTPStatus,
    payload: dict[str, object],
    *,
    server_timing: str | None = None,
) -> None:
    body = json_response_body(payload)
    timing = server_timing or server_timing_header(
        started_at=getattr(handler, "_request_started_at", None),
        finished_at=perf_counter(),
    )
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    if timing is not None:
        handler.send_header("Server-Timing", timing)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write_response_body(handler, body)


def send_error_response(
    handler: ResponseHandler,
    status: HTTPStatus,
    message: str,
    **extra: object,
) -> None:
    payload: dict[str, object] = {"error": message}
    payload.update(extra)
    send_json_response(handler, status, payload)


def send_exception_response(
    handler: ResponseHandler,
    status: HTTPStatus,
    prefix: str,
    exc: BaseException,
) -> None:
    send_error_response(handler, status, f"{prefix}: {exc}")


def write_response_body(handler: ResponseHandler, body: bytes) -> None:
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        return
