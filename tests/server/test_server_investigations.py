from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import investigations


@dataclass
class _Report:
    payload: dict[str, Any]


class _Senders:
    def __init__(self) -> None:
        self.errors: list[tuple[HTTPStatus, str]] = []
        self.exceptions: list[tuple[str, BaseException]] = []
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def send_error(self, status: HTTPStatus, message: str) -> None:
        self.errors.append((status, message))

    def send_exception(self, prefix: str, exc: BaseException) -> None:
        self.exceptions.append((prefix, exc))

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.responses.append((status, payload))


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Any]:
    return {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "projects_path": tmp_path / "projects.json",
        "include_archived_default": False,
        "privacy_mode": "normal",
    }


@pytest.mark.parametrize(
    ("kind", "builder_name", "schema"),
    [
        (
            "agentic",
            "build_agentic_investigation_report",
            "codex-usage-tracker-agentic-investigation-v1",
        ),
        (
            "repeated-file-rediscovery",
            "build_repeated_file_rediscovery_report",
            "codex-usage-tracker-repeated-file-rediscovery-v1",
        ),
        ("shell-churn", "build_shell_churn_report", "codex-usage-tracker-shell-churn-v1"),
        (
            "large-low-output",
            "build_large_low_output_report",
            "codex-usage-tracker-large-low-output-v1",
        ),
        ("walk", "build_investigation_walk_report", "codex-usage-tracker-investigation-walk-v1"),
    ],
)
def test_investigation_payload_matches_existing_report_payload(
    kind: investigations.InvestigationKind,
    builder_name: str,
    schema: str,
    paths: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "schema": schema,
        "includes_indexed_content": kind in {"repeated-file-rediscovery", "shell-churn", "walk"},
        "includes_raw_fragments": False,
        "rows": [{"path_hash": "safe-hash"}],
    }
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report(expected)

    monkeypatch.setattr(investigations, builder_name, build_report)
    query = "question=where%3F&since=2026-07-01&include_archived=true&privacy_mode=strict"

    payload = investigations.investigation_payload(kind, query, **paths)

    assert payload == expected
    assert payload["includes_raw_fragments"] is False
    assert "content" not in payload["rows"][0]
    assert "raw_fragment" not in payload["rows"][0]
    assert calls["since"] == "2026-07-01"
    assert calls["include_archived"] is True
    assert calls["privacy_mode"] == "strict"


@pytest.mark.parametrize("kind", ["repeated-file-rediscovery", "shell-churn", "large-low-output"])
def test_unlimited_filter_preserves_zero_as_none(
    kind: investigations.InvestigationKind,
    paths: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    builder_name = {
        "repeated-file-rediscovery": "build_repeated_file_rediscovery_report",
        "shell-churn": "build_shell_churn_report",
        "large-low-output": "build_large_low_output_report",
    }[kind]

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "test"})

    monkeypatch.setattr(investigations, builder_name, build_report)

    investigations.investigation_payload(kind, "limit=0", **paths)

    assert calls["limit"] is None


def test_bounded_integer_filters_are_capped(
    paths: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "test"})

    monkeypatch.setattr(investigations, "build_shell_churn_report", build_report)

    investigations.investigation_payload(
        "shell-churn",
        "min_occurrences=999999&sample_limit=999999&limit=999999",
        **paths,
    )

    assert calls["min_occurrences"] == 10_000
    assert calls["sample_limit"] == 10_000
    assert calls["limit"] == 10_000


def test_walk_requires_question(paths: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="question is required"):
        investigations.investigation_payload("walk", "", **paths)


def test_handle_investigation_request_reports_bad_filter(
    paths: dict[str, Any],
) -> None:
    senders = _Senders()

    investigations.handle_investigation_request(
        "shell-churn",
        "min_occurrences=-1",
        **paths,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == [
        (HTTPStatus.BAD_REQUEST, "min_occurrences must be a non-negative integer")
    ]
    assert senders.responses == []


def test_handle_investigation_request_reports_database_error(
    paths: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _Senders()

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(investigations, "investigation_payload", fail)

    investigations.handle_investigation_request(
        "agentic",
        "",
        **paths,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.exceptions[0][0] == "Database error while building investigation report"
    assert str(senders.exceptions[0][1]) == "database is locked"
    assert senders.responses == []
