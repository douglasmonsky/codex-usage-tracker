from __future__ import annotations

from email.message import Message
from http import HTTPStatus

import pytest

from codex_usage_tracker.server.api import _UsageDashboardHandler


def _handler_with_token(token: str) -> _UsageDashboardHandler:
    handler = object.__new__(_UsageDashboardHandler)
    handler._api_token = token
    handler.headers = Message()
    return handler


def test_reject_missing_diagnostic_refresh_token_sends_stable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _handler_with_token("secret-token")
    sent_errors: list[tuple[HTTPStatus, str]] = []
    monkeypatch.setattr(
        handler,
        "_send_error",
        lambda status, message: sent_errors.append((status, message)),
    )

    assert handler._reject_missing_diagnostic_refresh_token({}) is True
    assert sent_errors == [
        (
            HTTPStatus.FORBIDDEN,
            "Valid API token is required for diagnostic refresh",
        ),
    ]


def test_reject_missing_diagnostic_refresh_token_accepts_valid_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _handler_with_token("secret-token")
    handler.headers["X-Codex-Usage-Token"] = "secret-token"
    monkeypatch.setattr(
        handler,
        "_send_error",
        lambda _status, _message: None,
    )

    assert handler._reject_missing_diagnostic_refresh_token({}) is False
