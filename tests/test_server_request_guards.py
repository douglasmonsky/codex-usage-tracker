from __future__ import annotations

from codex_usage_tracker.server_request_guards import (
    has_valid_api_token,
    request_origin_allowed,
)


def test_request_origin_allowed_accepts_loopback_host_without_origin() -> None:
    headers = {"Host": "127.0.0.1:8898"}

    assert request_origin_allowed(headers, server_port=8898) is True


def test_request_origin_allowed_rejects_external_host() -> None:
    headers = {"Host": "example.com:8898"}

    assert request_origin_allowed(headers, server_port=8898) is False


def test_request_origin_allowed_requires_loopback_origin_same_port() -> None:
    assert (
        request_origin_allowed(
            {"Host": "localhost:8898", "Origin": "http://127.0.0.1:8898"},
            server_port=8898,
        )
        is True
    )
    assert (
        request_origin_allowed(
            {"Host": "localhost:8898", "Origin": "http://127.0.0.1:9999"},
            server_port=8898,
        )
        is False
    )
    assert (
        request_origin_allowed(
            {"Host": "localhost:8898", "Origin": "https://example.com"},
            server_port=8898,
        )
        is False
    )


def test_has_valid_api_token_accepts_header_before_query() -> None:
    headers = {"X-Codex-Usage-Token": "secret-token"}
    params = {"api_token": ["wrong-token"]}

    assert has_valid_api_token(headers, params, "secret-token") is True
    assert has_valid_api_token(headers, params, "wrong-token") is False


def test_has_valid_api_token_accepts_query_fallback() -> None:
    headers: dict[str, str] = {}
    params = {"api_token": ["secret-token"]}

    assert has_valid_api_token(headers, params, "secret-token") is True
    assert has_valid_api_token(headers, {}, "secret-token") is False
