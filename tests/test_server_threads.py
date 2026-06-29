from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_threads


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


def test_handle_threads_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_threads,
        "threads_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_threads.handle_threads_request(
        "limit=2",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [(HTTPStatus.OK, {"query": "limit=2"})]


def test_handle_threads_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def threads_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_threads, "threads_payload", threads_payload)

    server_threads.handle_threads_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading threads"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_threads_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_threads(**kwargs: Any) -> list[dict[str, object]]:
        calls.update(kwargs)
        return [{"thread_key": "thread-1"}]

    monkeypatch.setattr(server_threads, "query_thread_summaries", query_threads)

    payload = server_threads.threads_payload(
        "limit=7&offset=3&include_archived=true&q=preferred&search=ignored&sort=calls&direction=asc",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert payload["schema"] == "codex-usage-tracker-threads-v1"
    assert payload["rows"] == [{"thread_key": "thread-1"}]
    assert payload["row_count"] == 1
    assert payload["limit"] == 7
    assert payload["offset"] == 3
    assert payload["include_archived"] is True
    assert payload["raw_context_included"] is False
    assert calls["search"] == "preferred"
    assert calls["sort"] == "calls"
    assert calls["direction"] == "asc"


def test_threads_payload_uses_defaults_and_all_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_threads(**kwargs: Any) -> list[dict[str, object]]:
        calls.update(kwargs)
        return []

    monkeypatch.setattr(server_threads, "query_thread_summaries", query_threads)

    payload = server_threads.threads_payload(
        "limit=all",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
    )

    assert payload["limit"] is None
    assert payload["offset"] == 0
    assert payload["include_archived"] is True
    assert calls["limit"] is None
    assert calls["search"] is None
    assert calls["sort"] == "tokens"
    assert calls["direction"] == "desc"


def test_threads_payload_rejects_invalid_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit must be .*positive integer.*all"):
        server_threads.threads_payload(
            "limit=0",
            db_path=tmp_path / "usage.sqlite3",
            include_archived_default=False,
        )
