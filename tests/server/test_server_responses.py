from __future__ import annotations

import io
import json
from http import HTTPStatus

from codex_usage_tracker.server.responses import (
    send_error_response,
    send_exception_response,
    send_json_response,
)


class RecordingHandler:
    def __init__(self) -> None:
        self.status: int | HTTPStatus | None = None
        self.headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()
        self.ended = False

    def send_response(self, code: int | HTTPStatus) -> None:
        self.status = code

    def send_header(self, keyword: str, value: str) -> None:
        self.headers.append((keyword, value))

    def end_headers(self) -> None:
        self.ended = True


def test_send_error_response_builds_json_error_payload() -> None:
    handler = RecordingHandler()

    send_error_response(
        handler,
        HTTPStatus.FORBIDDEN,
        "Context loading disabled for dashboard server.",
        context_api_enabled=False,
        can_enable_context_api=True,
    )

    headers = dict(handler.headers)
    body = handler.wfile.getvalue()
    assert handler.status is HTTPStatus.FORBIDDEN
    assert handler.ended is True
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Length"] == str(len(body))
    assert json.loads(body) == {
        "error": "Context loading disabled for dashboard server.",
        "context_api_enabled": False,
        "can_enable_context_api": True,
    }


def test_send_exception_response_adds_exception_message() -> None:
    handler = RecordingHandler()

    send_exception_response(
        handler,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "Database error while reading usage data",
        RuntimeError("database locked"),
    )

    assert json.loads(handler.wfile.getvalue()) == {
        "error": "Database error while reading usage data: database locked",
    }


def test_send_json_response_includes_server_timing_when_provided() -> None:
    handler = RecordingHandler()

    send_json_response(
        handler,
        HTTPStatus.OK,
        {"status": "ok"},
        server_timing="app;dur=12.500",
    )

    assert dict(handler.headers)["Server-Timing"] == "app;dur=12.500"
