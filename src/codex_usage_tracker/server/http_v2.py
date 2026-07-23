"""Live-server integration for the transport-independent HTTP v2 facade."""

from __future__ import annotations

from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from urllib.parse import parse_qs, urlparse

from codex_usage_tracker.interfaces.http.v2 import ApplicationHttpV2Services, HttpV2Facade
from codex_usage_tracker.server.responses import send_json_response


class _HttpV2Handler(Protocol):
    path: str
    command: str
    rfile: BinaryIO
    headers: Message
    _db_path: Path
    _pricing_path: Path
    _allowance_path: Path
    _rate_card_path: Path
    _thresholds_path: Path
    _projects_path: Path
    _codex_home: Path

    def _has_valid_api_token(self, params: dict[str, list[str]]) -> bool: ...


class HttpV2RouteMixin:
    """Attach stable v2 application services to each localhost request handler."""

    def _configure_http_v2(self, facade: HttpV2Facade | None = None) -> None:
        if facade is not None:
            self._http_v2_facade = facade
            return
        handler = cast(_HttpV2Handler, self)
        self._http_v2_facade = HttpV2Facade(
            ApplicationHttpV2Services(
                db_path=handler._db_path,
                pricing_path=handler._pricing_path,
                allowance_path=handler._allowance_path,
                rate_card_path=handler._rate_card_path,
                thresholds_path=handler._thresholds_path,
                projects_path=handler._projects_path,
                codex_home=handler._codex_home,
            )
        )

    def _handle_http_v2(self, query: str) -> None:
        handler = cast(_HttpV2Handler, self)
        parsed = urlparse(handler.path)
        response = self._http_v2_facade.handle_stream(
            method=handler.command,
            path=parsed.path,
            query=query,
            stream=handler.rfile,
            content_length=handler.headers.get("Content-Length"),
            content_type=handler.headers.get("Content-Type", ""),
            authorized=handler._has_valid_api_token(parse_qs(query)),
        )
        send_json_response(
            cast(Any, self),
            HTTPStatus(response.status),
            response.payload,
            headers=response.headers,
        )
