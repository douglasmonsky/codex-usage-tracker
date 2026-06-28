from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_summary


@dataclass
class _Report:
    value: dict[str, object]

    def payload(self) -> dict[str, object]:
        return dict(self.value)


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


def test_handle_summary_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_summary,
        "summary_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_summary.handle_summary_request(
        "group_by=model",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [
        (HTTPStatus.OK, {"query": "group_by=model"}),
    ]


def test_handle_summary_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def summary_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_summary, "summary_payload", summary_payload)

    server_summary.handle_summary_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading summary"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_summary_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "codex-usage-tracker-summary-v1"})

    monkeypatch.setattr(server_summary, "build_summary_report", build_report)

    payload = server_summary.summary_payload(
        "group_by=model&limit=9&preset=by-subagent-role&since=2026-06-01",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="strict",
    )

    assert payload["schema"] == "codex-usage-tracker-summary-v1"
    assert payload["raw_context_included"] is False
    assert calls["group_by"] == "model"
    assert calls["limit"] == 9
    assert calls["preset"] == "by-subagent-role"
    assert calls["since"] == "2026-06-01"
    assert calls["privacy_mode"] == "strict"


def test_summary_payload_uses_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({})

    monkeypatch.setattr(server_summary, "build_summary_report", build_report)

    payload = server_summary.summary_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
    )

    assert payload == {"raw_context_included": False}
    assert calls["group_by"] == "thread"
    assert calls["limit"] == 20
    assert calls["preset"] is None
