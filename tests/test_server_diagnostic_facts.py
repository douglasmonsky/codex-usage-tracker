from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_diagnostic_facts


@dataclass
class _Report:
    payload: dict[str, object]


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


def test_handle_diagnostics_summary_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def diagnostics_summary_payload(query: str, **kwargs: Any) -> dict[str, object]:
        return {"query": query, "archived": kwargs["include_archived_default"]}

    monkeypatch.setattr(
        server_diagnostic_facts,
        "diagnostics_summary_payload",
        diagnostics_summary_payload,
    )

    server_diagnostic_facts.handle_diagnostics_summary_request(
        "limit=5",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [(HTTPStatus.OK, {"query": "limit=5", "archived": True})]


def test_handle_diagnostics_facts_request_sends_bad_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def diagnostics_facts_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise ValueError("bad sort")

    monkeypatch.setattr(
        server_diagnostic_facts,
        "diagnostics_facts_payload",
        diagnostics_facts_payload,
    )

    server_diagnostic_facts.handle_diagnostics_facts_request(
        "sort=bad",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        request_path="/api/diagnostics/tools",
        fact_type="tool_call",
        fact_group="tools",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == [(HTTPStatus.BAD_REQUEST, "bad sort")]
    assert senders.json_payloads == []


def test_handle_diagnostics_fact_calls_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def diagnostic_fact_calls_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        server_diagnostic_facts,
        "diagnostic_fact_calls_payload",
        diagnostic_fact_calls_payload,
    )

    server_diagnostic_facts.handle_diagnostics_fact_calls_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading diagnostic calls"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_diagnostics_summary_payload_normalizes_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"ok": True})

    monkeypatch.setattr(server_diagnostic_facts, "build_diagnostics_summary_report", build_report)

    payload = server_diagnostic_facts.diagnostics_summary_payload(
        "limit=7&min_tokens=42&include_archived=true&sort=tokens&direction=asc",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert payload == {"ok": True}
    assert calls["limit"] == 7
    assert calls["min_tokens"] == 42
    assert calls["include_archived"] is True
    assert calls["sort"] == "tokens"
    assert calls["direction"] == "asc"


def test_diagnostics_facts_payload_applies_route_fact_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"facts": []})

    monkeypatch.setattr(server_diagnostic_facts, "build_diagnostics_facts_report", build_report)

    payload = server_diagnostic_facts.diagnostics_facts_payload(
        "fact_type=ignored&fact_name=name",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        request_path="/api/diagnostics/tools",
        fact_type="tool_call",
        fact_group="tools",
    )

    assert payload == {"facts": []}
    assert calls["fact_type"] == "tool_call"
    assert calls["fact_name"] == "name"
    assert calls["fact_group"] == "tools"
    assert calls["view"] == "tools"
    assert calls["include_archived"] is True


def test_diagnostic_fact_calls_payload_requires_fact_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fact_type and fact_name are required"):
        server_diagnostic_facts.diagnostic_fact_calls_payload(
            "fact_type=tool_call",
            db_path=tmp_path / "usage.sqlite3",
            include_archived_default=False,
            privacy_mode="normal",
        )


def test_diagnostic_fact_calls_payload_forwards_paging_and_privacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"calls": []})

    monkeypatch.setattr(
        server_diagnostic_facts,
        "build_diagnostics_fact_calls_report",
        build_report,
    )

    payload = server_diagnostic_facts.diagnostic_fact_calls_payload(
        "fact_type=tool_call&fact_name=exec_command&limit=11&offset=3",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
        privacy_mode="strict",
    )

    assert payload == {"calls": []}
    assert calls["fact_type"] == "tool_call"
    assert calls["fact_name"] == "exec_command"
    assert calls["limit"] == 11
    assert calls["offset"] == 3
    assert calls["sort"] == "tokens"
    assert calls["privacy_mode"] == "strict"
