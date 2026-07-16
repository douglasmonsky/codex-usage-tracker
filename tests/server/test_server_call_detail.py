from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import call_detail as server_call_detail
from codex_usage_tracker.store.api import upsert_usage_events
from tests.otel_helpers import synthetic_usage_event


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


def test_handle_call_detail_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_call_detail,
        "call_detail_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_call_detail.handle_call_detail_request(
        "record_id=rec-1",
        db_path=tmp_path / "usage.sqlite3",
        annotate_rows=lambda rows: rows,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [(HTTPStatus.OK, {"query": "record_id=rec-1"})]


def test_handle_call_detail_request_sends_missing_record_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def call_detail_payload(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise server_call_detail.UsageRecordNotFoundError("No usage record found: missing")

    monkeypatch.setattr(server_call_detail, "call_detail_payload", call_detail_payload)

    server_call_detail.handle_call_detail_request(
        "record_id=missing",
        db_path=tmp_path / "usage.sqlite3",
        annotate_rows=lambda rows: rows,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == [(HTTPStatus.NOT_FOUND, "No usage record found: missing")]
    assert senders.json_payloads == []


def test_handle_call_detail_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def call_detail_payload(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_call_detail, "call_detail_payload", call_detail_payload)

    server_call_detail.handle_call_detail_request(
        "record_id=rec-1",
        db_path=tmp_path / "usage.sqlite3",
        annotate_rows=lambda rows: rows,
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading call"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_call_detail_payload_includes_annotated_adjacent_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: dict[str, dict[str, object]] = {
        "previous": {"record_id": "previous"},
        "current": {
            "record_id": "current",
            "previous_record_id": "previous",
            "next_record_id": "next",
        },
        "next": {"record_id": "next"},
    }
    calls: list[str] = []

    def query_record(**kwargs: Any) -> dict[str, object] | None:
        calls.append(kwargs["record_id"])
        return rows.get(kwargs["record_id"])

    def annotate_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
        return [candidate | {"annotated": True} for candidate in candidates]

    monkeypatch.setattr(server_call_detail, "query_usage_record", query_record)

    payload = server_call_detail.call_detail_payload(
        "record=current",
        db_path=tmp_path / "usage.sqlite3",
        annotate_rows=annotate_rows,
    )

    assert calls == ["current", "previous", "next"]
    assert payload["schema"] == "codex-usage-tracker-call-v1"
    assert payload["record"] == rows["current"] | {"annotated": True}
    assert payload["previous_record"] == rows["previous"] | {"annotated": True}
    assert payload["next_record"] == rows["next"] | {"annotated": True}
    assert payload["adjacent_records"] == [
        rows["previous"] | {"annotated": True},
        rows["current"] | {"annotated": True},
        rows["next"] | {"annotated": True},
    ]
    assert payload["previous_record_id"] == "previous"
    assert payload["next_record_id"] == "next"
    assert payload["raw_context_included"] is False


def test_call_detail_payload_requires_record_id(tmp_path: Path) -> None:
    with pytest.raises(server_call_detail.MissingRecordIdError, match="record_id required"):
        server_call_detail.call_detail_payload(
            "",
            db_path=tmp_path / "usage.sqlite3",
            annotate_rows=lambda rows: rows,
        )


def test_call_detail_exposes_tier_without_sidecar_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            synthetic_usage_event(
                "record-a", "conversation-a", (100, 40, 30, 10), fast=1
            )
        ],
        db_path=db_path,
    )

    payload = server_call_detail.call_detail_payload(
        "record_id=record-a", db_path=db_path, annotate_rows=lambda rows: rows
    )

    record = payload["record"]
    assert record["service_tier"] == "fast"
    assert record["service_tier_confidence"] == "exact"
    assert "source_path" not in record


def test_call_detail_payload_raises_when_record_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_call_detail, "query_usage_record", lambda **kwargs: None)

    with pytest.raises(server_call_detail.UsageRecordNotFoundError, match="missing"):
        server_call_detail.call_detail_payload(
            "record_id=missing",
            db_path=tmp_path / "usage.sqlite3",
            annotate_rows=lambda rows: rows,
        )
