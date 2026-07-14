from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import summary as server_summary
from codex_usage_tracker.server.query_cache import AggregateQueryCache
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


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


def test_handle_summary_request_reuses_generation_keyed_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    calls = 0

    def summary_payload(query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"query": query, "rows": []}

    monkeypatch.setattr(server_summary, "summary_payload", summary_payload)

    for query in ("limit=20&group_by=model", "group_by=model&limit=20"):
        server_summary.handle_summary_request(
            query,
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            projects_path=tmp_path / "projects.json",
            privacy_mode="normal",
            query_cache=cache,
            send_error=senders.send_error,
            send_exception=senders.send_exception,
            send_json=senders.send_json,
        )

    assert calls == 1
    cache_metadata = [_cache_metadata(payload) for _, payload in senders.json_payloads]
    assert [metadata["status"] for metadata in cache_metadata] == ["miss", "hit"]
    assert all(metadata["source_revision"] == "generation:0" for metadata in cache_metadata)


def test_handle_summary_request_invalidates_after_source_generation_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    db_path = tmp_path / "usage.sqlite3"
    calls = 0

    def summary_payload(_query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [], "build": calls}

    monkeypatch.setattr(server_summary, "summary_payload", summary_payload)
    request: dict[str, Any] = {
        "db_path": db_path,
        "pricing_path": tmp_path / "pricing.json",
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "query_cache": cache,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }

    server_summary.handle_summary_request("group_by=model", **request)
    upsert_usage_events(
        [
            _usage_event(
                record_id="call-1",
                session_id="session-1",
                thread_key="thread:one",
                event_timestamp="2026-07-14T12:00:00Z",
                cumulative_total_tokens=100,
            )
        ],
        db_path=db_path,
    )
    server_summary.handle_summary_request("group_by=model", **request)

    assert calls == 2
    assert [
        _cache_metadata(payload)["source_revision"] for _, payload in senders.json_payloads
    ] == ["generation:0", "generation:1"]


def test_handle_summary_request_invalidates_relative_presets_after_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=4, max_payload_bytes=1_024)
    calls = 0
    current_day = "2026-07-14"

    def summary_payload(_query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [], "build": calls}

    monkeypatch.setattr(server_summary, "summary_payload", summary_payload)
    monkeypatch.setattr(server_summary, "_current_calendar_date", lambda: current_day)
    request: dict[str, Any] = {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "query_cache": cache,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }

    server_summary.handle_summary_request("preset=last-7-days&group_by=date", **request)
    server_summary.handle_summary_request("preset=last-7-days&group_by=date", **request)
    current_day = "2026-07-15"
    server_summary.handle_summary_request("preset=last-7-days&group_by=date", **request)

    assert calls == 2
    assert [_cache_metadata(payload)["status"] for _, payload in senders.json_payloads] == [
        "miss",
        "hit",
        "miss",
    ]


def test_handle_summary_request_bypasses_unbounded_thread_payload_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    calls = 0

    def summary_payload(_query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [], "build": calls}

    monkeypatch.setattr(server_summary, "summary_payload", summary_payload)
    request: dict[str, Any] = {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "query_cache": cache,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }

    server_summary.handle_summary_request("group_by=thread&limit=0", **request)
    server_summary.handle_summary_request("group_by=thread&limit=0", **request)

    assert calls == 2
    for _, payload in senders.json_payloads:
        assert _cache_metadata(payload) == {
            "status": "bypass",
            "source_revision": "generation:0",
            "freshness": "current",
            "payload_bytes": None,
            "stored": False,
        }


def _cache_metadata(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload["query_cache"]
    assert isinstance(metadata, dict)
    return metadata


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
        "group_by=model&limit=9&preset=by-subagent-role&since=2026-06-01&include_archived=true",
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
    assert calls["include_archived"] is True
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
    assert calls["include_archived"] is False


def test_summary_payload_accepts_an_unbounded_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({})

    monkeypatch.setattr(server_summary, "build_summary_report", build_report)

    server_summary.summary_payload(
        "limit=0",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
    )

    assert calls["limit"] is None
