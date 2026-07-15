from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.jobs import CompressionJobRegistry
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.server import compression_routes


def test_compression_scope_parses_dashboard_filters() -> None:
    scope = compression_routes.compression_scope_from_query(
        "since=2026-07-01T00%3A00%3A00Z&until=2026-07-14T00%3A00%3A00Z"
        "&thread=thread-1&model=gpt-5.6&effort=high&include_archived=true",
        include_archived_default=False,
    )

    assert scope == CompressionScope(
        since="2026-07-01T00:00:00Z",
        until="2026-07-14T00:00:00Z",
        thread="thread-1",
        include_archived=True,
        model="gpt-5.6",
        effort="high",
    )


def test_compression_start_requires_token(tmp_path: Path) -> None:
    errors: list[tuple[HTTPStatus, str]] = []

    compression_routes.handle_compression_start_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        registry=CompressionJobRegistry(),
        include_archived_default=False,
        has_valid_api_token=lambda _params: False,
        send_error=lambda status, message: errors.append((status, message)),
        send_exception=lambda _prefix, _exc: None,
        send_json=lambda _status, _payload: None,
    )

    assert errors == [(HTTPStatus.FORBIDDEN, "Valid API token is required for Compression Lab")]


def test_compression_start_delegates_to_shared_application_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    expected = compression_payload(kind="status", status="running")

    def start(db_path, scope, *, detector_families, refresh, registry):
        calls.append(
            {
                "db_path": db_path,
                "scope": scope,
                "detector_families": detector_families,
                "refresh": refresh,
                "registry": registry,
            }
        )
        return expected

    monkeypatch.setattr(compression_routes, "start_compression_analysis", start)
    registry = CompressionJobRegistry()
    db_path = tmp_path / "usage.sqlite3"

    compression_routes.handle_compression_start_request(
        "include_archived=1&detector_family=stale_context"
        "&detector_family=tool_output_bloat&refresh=true",
        db_path=db_path,
        registry=registry,
        include_archived_default=False,
        has_valid_api_token=lambda _params: True,
        send_error=lambda _status, _message: None,
        send_exception=lambda _prefix, _exc: None,
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert calls == [
        {
            "db_path": db_path,
            "scope": CompressionScope(include_archived=True),
            "detector_families": ("stale_context", "tool_output_bloat"),
            "refresh": True,
            "registry": registry,
        }
    ]
    assert responses == [(HTTPStatus.ACCEPTED, expected)]


def test_compression_start_reports_refresh_lock_as_retryable_busy_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    exceptions: list[BaseException] = []

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(compression_routes, "start_compression_analysis", locked)
    compression_routes.handle_compression_start_request(
        "include_archived=1",
        db_path=tmp_path / "usage.sqlite3",
        registry=CompressionJobRegistry(),
        include_archived_default=False,
        has_valid_api_token=lambda _params: True,
        send_error=lambda _status, _message: None,
        send_exception=lambda _prefix, exc: exceptions.append(exc),
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert exceptions == []
    assert responses[0][0] == HTTPStatus.SERVICE_UNAVAILABLE
    assert responses[0][1]["error"] == {
        "code": "compression_database_busy",
        "message": "Usage data is refreshing; Compression Lab will retry when the index is ready.",
    }
    assert responses[0][1]["next"] == {
        "tool": "usage_compression_start",
        "arguments": {},
        "poll_after_ms": 1_000,
    }


def test_compression_status_and_profile_preserve_shared_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    status_payload = compression_payload(kind="status", status="completed")
    profile_payload = compression_payload(kind="profile", status="completed")
    profile_payload["profile"] = {"candidate_count": 4}

    monkeypatch.setattr(
        compression_routes,
        "compression_status",
        lambda _db_path, *, run_id, registry: status_payload if run_id == "compression-1" else None,
    )
    monkeypatch.setattr(
        compression_routes,
        "compression_profile",
        lambda _db_path, *, run_id, scope, detector_families: profile_payload,
    )
    common = {
        "db_path": tmp_path / "usage.sqlite3",
        "registry": CompressionJobRegistry(),
        "include_archived_default": False,
        "has_valid_api_token": lambda _params: True,
        "send_error": lambda _status, _message: None,
        "send_exception": lambda _prefix, _exc: None,
        "send_json": lambda status, payload: responses.append((status, payload)),
    }

    compression_routes.handle_compression_status_request("run_id=compression-1", **common)
    compression_routes.handle_compression_profile_request(
        "run_id=compression-1&include_archived=true",
        **common,
    )

    assert responses == [
        (HTTPStatus.OK, status_payload),
        (HTTPStatus.OK, profile_payload),
    ]


def test_compression_profile_returns_shared_missing_payload_as_not_found(
    tmp_path: Path,
    monkeypatch,
) -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    missing = compression_payload(kind="profile", status="error")
    missing["error"] = {"code": "compression_run_not_found"}
    monkeypatch.setattr(compression_routes, "compression_profile", lambda *args, **kwargs: missing)

    compression_routes.handle_compression_profile_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        registry=CompressionJobRegistry(),
        include_archived_default=False,
        has_valid_api_token=lambda _params: True,
        send_error=lambda _status, _message: None,
        send_exception=lambda _prefix, _exc: None,
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert responses == [(HTTPStatus.OK, missing)]


def compression_payload(*, kind: str, status: str) -> dict[str, object]:
    return {
        "schema": "codex-usage-tracker-compression-api-v1",
        "kind": kind,
        "run_id": "compression-1",
        "status": status,
        "progress": {"percent": 100.0},
        "error": None,
    }
