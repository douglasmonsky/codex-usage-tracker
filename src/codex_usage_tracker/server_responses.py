"""HTTP response helpers for the local dashboard server."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Protocol

from codex_usage_tracker.server_utils import json_response_body


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
) -> None:
    body = json_response_body(payload)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write_response_body(handler, body)


def write_response_body(handler: ResponseHandler, body: bytes) -> None:
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        return
