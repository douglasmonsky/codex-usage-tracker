from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.server import status as server_status


class _RouteSenders:
    def __init__(self) -> None:
        self.exceptions: list[tuple[str, BaseException]] = []
        self.json_payloads: list[tuple[HTTPStatus, dict[str, object]]] = []

    def send_exception(self, prefix: str, exc: BaseException) -> None:
        self.exceptions.append((prefix, exc))

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.json_payloads.append((status, payload))


def test_handle_status_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_status,
        "status_payload",
        lambda query, **kwargs: {"query": query, "archived": kwargs["include_archived_default"]},
    )

    server_status.handle_status_request(
        "include_archived=true",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.exceptions == []
    assert senders.json_payloads == [
        (HTTPStatus.OK, {"query": "include_archived=true", "archived": False}),
    ]


def test_handle_status_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def status_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_status, "status_payload", status_payload)

    server_status.handle_status_request(
        "",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading status"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_status_payload_normalizes_include_archived_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    codex_home = tmp_path / ".codex"
    install_plugin(
        plugin_dir=codex_home.parent / "plugins" / "codex-usage-tracker",
        marketplace_path=tmp_path / "marketplace.json",
    )
    real_readiness = server_status.conversational_readiness
    readiness_homes: list[Path] = []

    def capture_readiness(*, codex_home: Path) -> dict[str, object]:
        readiness_homes.append(codex_home)
        return real_readiness(codex_home=codex_home)

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["status"] = kwargs
        return {"total_events": 4, "max_event_timestamp": "2026-06-01T00:00:00Z"}

    def query_observed(**kwargs: Any) -> dict[str, object]:
        calls["observed"] = kwargs
        return {"weekly_percent": 37}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "conversational_readiness", capture_readiness)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", query_observed)
    monkeypatch.setattr(
        server_status,
        "query_dedupe_diagnostics",
        lambda **kwargs: {"summary": {"excluded_copied_rows": 2}},
    )
    monkeypatch.setattr(
        server_status,
        "refresh_metadata",
        lambda db_path: {
            "latest_refresh_at": "2026-06-01T01:00:00Z",
            "parser_adapter": "jsonl",
            "parser_skipped_events": "3",
            "parser_duplicate_events": "0",
        },
    )

    payload = server_status.status_payload(
        "include_archived=true",
        codex_home=codex_home,
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert calls["status"]["include_archived"] is True
    assert calls["observed"]["include_archived"] is True
    assert payload["schema"] == "codex-usage-tracker-status-v1"
    assert payload["latest_refresh_at"] == "2026-06-01T01:00:00Z"
    assert payload["max_event_timestamp"] == "2026-06-01T00:00:00Z"
    assert payload["observed_usage"] == {"weekly_percent": 37}
    assert payload["parser_adapter"] == "jsonl"
    assert payload["parser_diagnostics"] == {"skipped_events": 3}
    assert payload["dedupe"] == {"excluded_copied_rows": 2}
    assert payload["conversational_analysis"]["state"] == "ready"
    assert readiness_homes == [codex_home]
    assert str(codex_home) not in str(payload["conversational_analysis"])


def test_status_payload_uses_include_archived_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["include_archived"] = kwargs["include_archived"]
        return {}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", lambda **kwargs: {})
    monkeypatch.setattr(
        server_status,
        "query_dedupe_diagnostics",
        lambda **kwargs: {"summary": {"excluded_copied_rows": 0}},
    )
    monkeypatch.setattr(server_status, "refresh_metadata", lambda db_path: {})

    payload = server_status.status_payload(
        "",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
    )

    assert calls["include_archived"] is True
    assert payload["include_archived"] is True
    assert payload["parser_diagnostics"] == {}
