from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Any

import pytest

from codex_usage_tracker.server import call_lists as server_call_lists


class _RouteSenders:
    def __init__(self) -> None:
        self.errors: list[tuple[HTTPStatus, str]] = []
        self.exceptions: list[tuple[str, BaseException]] = []
        self.json_payloads: list[tuple[HTTPStatus, dict[str, object]]] = []

    def send_error(self, status: HTTPStatus, message: str) -> None:
        self.errors.append((status, message))

    def send_exception(self, prefix: str, exc: BaseException) -> None:
        self.exceptions.append((prefix, exc))

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.json_payloads.append((status, payload))


def test_handle_calls_request_sends_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_call_lists,
        "calls_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_call_lists.handle_calls_request(
        "limit=2",
        live_query_params=lambda _params: {},
        live_call_rows=lambda **_kwargs: ([], 0),
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [(HTTPStatus.OK, {"query": "limit=2"})]


def test_handle_calls_request_sends_sqlite_error(monkeypatch: pytest.MonkeyPatch) -> None:
    senders = _RouteSenders()

    def calls_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_call_lists, "calls_payload", calls_payload)

    server_call_lists.handle_calls_request(
        "",
        live_query_params=lambda _params: {},
        live_call_rows=lambda **_kwargs: ([], 0),
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading calls"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_handle_thread_calls_request_sends_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_call_lists,
        "thread_calls_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_call_lists.handle_thread_calls_request(
        "thread_key=thread-1",
        live_query_params=lambda _params, **_kwargs: {},
        live_call_rows=lambda **_kwargs: ([], 0),
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [
        (HTTPStatus.OK, {"query": "thread_key=thread-1"}),
    ]


def test_handle_thread_calls_request_sends_missing_thread_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def thread_calls_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise server_call_lists.MissingThreadKeyError("thread_key required")

    monkeypatch.setattr(server_call_lists, "thread_calls_payload", thread_calls_payload)

    server_call_lists.handle_thread_calls_request(
        "",
        live_query_params=lambda _params, **_kwargs: {},
        live_call_rows=lambda **_kwargs: ([], 0),
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == [(HTTPStatus.BAD_REQUEST, "thread_key required")]
    assert senders.json_payloads == []


def test_calls_payload_applies_derived_filters_and_pagination() -> None:
    calls: dict[str, Any] = {}

    def live_query_params(params: dict[str, list[str]]) -> dict[str, object]:
        calls["params"] = params
        return {
            "limit": 2,
            "offset": 3,
            "since": "2026-07-01",
            "until": None,
            "include_archived": False,
            "filters": {"model": "gpt-5.5"},
        }

    def live_call_rows(**kwargs: Any) -> tuple[list[dict[str, object]], int]:
        calls["rows"] = kwargs
        return ([{"record_id": "one"}, {"record_id": "two"}], 8)

    payload = server_call_lists.calls_payload(
        "pricing_status=priced&credit_confidence=exact",
        live_query_params=live_query_params,
        live_call_rows=live_call_rows,
        live_call_filter_options=lambda **_kwargs: {
            "models": ["gpt-5.5", "gpt-older-page"],
            "efforts": ["high"],
        },
    )

    assert calls["rows"]["pricing_status"] == "priced"
    assert calls["rows"]["credit_confidence"] == "exact"
    assert payload["schema"] == "codex-usage-tracker-calls-v1"
    assert payload["row_count"] == 2
    assert payload["total_matched_rows"] == 8
    assert payload["has_more"] is True
    assert payload["next_offset"] == 5
    assert payload["filters"] == {
        "model": "gpt-5.5",
        "pricing_status": "priced",
        "credit_confidence": "exact",
    }
    assert payload["raw_context_included"] is False
    assert payload["filter_options"] == {
        "models": ["gpt-5.5", "gpt-older-page"],
        "efforts": ["high"],
    }


def test_thread_calls_payload_forwards_thread_key_and_omits_filters() -> None:
    calls: dict[str, Any] = {}

    def live_query_params(
        params: dict[str, list[str]],
        *,
        thread_key: str,
    ) -> dict[str, object]:
        calls["thread_key"] = thread_key
        return {"limit": None, "offset": 0, "filters": {"thread_key": thread_key}}

    def live_call_rows(**kwargs: Any) -> tuple[list[dict[str, object]], int]:
        calls["rows"] = kwargs
        return ([{"record_id": "one"}], 1)

    payload = server_call_lists.thread_calls_payload(
        "thread=thread-a",
        live_query_params=live_query_params,
        live_call_rows=live_call_rows,
    )

    assert calls["thread_key"] == "thread-a"
    assert calls["rows"]["pricing_status"] is None
    assert calls["rows"]["credit_confidence"] is None
    assert payload["schema"] == "codex-usage-tracker-thread-calls-v1"
    assert payload["thread_key"] == "thread-a"
    assert payload["limit"] is None
    assert payload["has_more"] is False
    assert "filters" not in payload


def test_thread_calls_payload_requires_thread_key() -> None:
    with pytest.raises(server_call_lists.MissingThreadKeyError, match="thread_key required"):
        server_call_lists.thread_calls_payload(
            "",
            live_query_params=lambda params, **kwargs: {},
            live_call_rows=lambda **kwargs: ([], 0),
        )


def test_calls_payload_rejects_invalid_derived_filter() -> None:
    with pytest.raises(ValueError, match="pricing_status"):
        server_call_lists.calls_payload(
            "pricing_status=weird",
            live_query_params=lambda params: {"limit": 1, "offset": 0, "filters": {}},
            live_call_rows=lambda **kwargs: ([], 0),
        )
