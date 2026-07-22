from __future__ import annotations

import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import allowance_v2
from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
from codex_usage_tracker.server.responses import send_json_response
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def test_status_payload_is_constant_size_and_supports_revision_polling(tmp_path: Path) -> None:
    payload = allowance_v2.allowance_status_payload(
        "since_revision=missing&include_archived=false",
        db_path=_initialized_db(tmp_path),
        privacy_mode="strict",
        include_archived_default=True,
    )

    assert payload == {
        "schema": "codex-usage-tracker-allowance-status-v2",
        "revision": "missing",
        "changed": False,
        "quality": {"canonical": True, "copied_rows_excluded": 0},
        "next": {"action": "poll_status", "poll_after_seconds": 60},
    }


@pytest.mark.parametrize(
    ("query", "message"),
    [
        (
            "range_preset=custom&start_at=2025-01-01T00:00:00Z&end_at=2026-07-01T00:00:00Z",
            "custom range must not exceed 366 days",
        ),
    ],
)
def test_series_rejects_unbounded_ranges(tmp_path: Path, query: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        allowance_v2.allowance_series_payload(
            query,
            db_path=_initialized_db(tmp_path),
            include_archived_default=False,
        )


def test_evidence_rejects_unbounded_page_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 500"):
        allowance_v2.allowance_evidence_payload(
            "limit=501",
            db_path=_initialized_db(tmp_path),
            privacy_mode="strict",
            include_archived_default=False,
        )


def test_stale_evidence_cursor_returns_revision_conflict(tmp_path: Path) -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    allowance_v2.handle_allowance_evidence_request(
        "before=stale-cursor",
        db_path=_initialized_db(tmp_path),
        privacy_mode="strict",
        include_archived_default=False,
        send_error=lambda status, message, **extra: responses.append(
            (status, {"error": message, **extra})
        ),
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert responses == [
        (
            HTTPStatus.CONFLICT,
            {
                "error": "Allowance evidence revision changed; restart from the newest page",
                "code": "allowance_revision_changed",
                "next": {"action": "restart_from_newest"},
            },
        )
    ]


def test_analysis_get_returns_missing_without_running_detector(tmp_path: Path) -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    allowance_v2.handle_allowance_analysis_request(
        "window_kind=weekly&cohort_id=codex&forecast_horizon=1",
        db_path=_initialized_db(tmp_path),
        include_archived_default=False,
        send_error=lambda *_args, **_kwargs: None,
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert responses[0][0] == HTTPStatus.OK
    assert responses[0][1]["schema"] == "codex-usage-tracker-allowance-analysis-v2"
    assert responses[0][1]["status"] == "missing"
    assert responses[0][1]["next"] == {"action": "start_analysis_job"}


def test_analysis_job_is_token_protected_deduplicated_and_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _initialized_db(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    errors: list[tuple[HTTPStatus, str]] = []

    def build_analysis(_connection: Any, **_kwargs: object) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=2)
        return {
            "schema": "codex-usage-tracker-allowance-analysis-v2",
            "snapshot_id": "snapshot-1",
            "status": "no_supported_change",
        }

    monkeypatch.setattr(allowance_v2, "build_allowance_analysis", build_analysis)
    registry = AnalysisJobRegistry()
    kwargs = {
        "db_path": db_path,
        "registry": registry,
        "include_archived_default": False,
        "has_valid_api_token": lambda _params: True,
        "send_error": lambda status, message, **_extra: errors.append((status, message)),
        "send_json": lambda status, payload: responses.append((status, payload)),
    }
    query = "api_token=test&window_kind=weekly&cohort_id=codex&forecast_horizon=1"

    allowance_v2.handle_allowance_analysis_job_start_request(query, **kwargs)
    assert entered.wait(timeout=2)
    allowance_v2.handle_allowance_analysis_job_start_request(query, **kwargs)

    assert errors == []
    assert [status for status, _payload in responses] == [HTTPStatus.ACCEPTED] * 2
    assert responses[0][1]["job_id"] == responses[1][1]["job_id"]
    assert responses[1][1]["cache"] == {"request_reused": "active"}
    next_action = responses[1][1]["next"]
    assert isinstance(next_action, dict)
    assert next_action["poll_after_ms"] == 500

    release.set()
    job_id = str(responses[0][1]["job_id"])
    completed = _wait_for_terminal(registry, job_id)
    assert completed["status"] == "completed"
    assert completed["result"] == {
        "analysis_schema": "codex-usage-tracker-allowance-analysis-v2",
        "snapshot_id": "snapshot-1",
        "status": "no_supported_change",
    }
    assert completed["next"] == {
        "action": "reload_persisted_results",
        "endpoint": "/api/allowance/analysis",
    }
    generic = registry.job_service.status(job_id, include_result=True)
    assert generic.kind == "allowance"
    assert generic.state == "completed"
    assert generic.result == completed["result"]


def test_analysis_job_start_and_status_require_token(tmp_path: Path) -> None:
    errors: list[tuple[HTTPStatus, str]] = []
    registry = AnalysisJobRegistry()
    common = {
        "registry": registry,
        "has_valid_api_token": lambda _params: False,
        "send_error": lambda status, message, **_extra: errors.append((status, message)),
        "send_json": lambda _status, _payload: None,
    }

    allowance_v2.handle_allowance_analysis_job_start_request(
        "",
        db_path=_initialized_db(tmp_path),
        include_archived_default=False,
        **common,
    )
    allowance_v2.handle_allowance_analysis_job_status_request("job_id=missing", **common)

    assert errors == [
        (HTTPStatus.FORBIDDEN, "Valid API token is required for allowance analysis"),
        (HTTPStatus.FORBIDDEN, "Valid API token is required for allowance analysis"),
    ]


def test_json_response_supports_explicit_headers_and_keeps_status_no_store() -> None:
    handler = _ResponseRecorder()

    send_json_response(
        handler,
        HTTPStatus.OK,
        {"schema": "test"},
        headers={"Cache-Control": "no-store", "X-Allowance-Revision": "r1"},
    )

    assert handler.headers.count(("Cache-Control", "no-store")) == 1
    assert ("X-Allowance-Revision", "r1") in handler.headers


def _initialized_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)
    return db_path


def _wait_for_terminal(registry: AnalysisJobRegistry, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while True:
        payload = registry.status(job_id)
        if payload["status"] not in {"pending", "running"}:
            return payload
        assert time.monotonic() < deadline
        time.sleep(0.01)


class _ResponseRecorder:
    def __init__(self) -> None:
        self.status: HTTPStatus | None = None
        self.headers: list[tuple[str, str]] = []
        self.wfile = _BodyRecorder()

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.headers.append((name, value))

    def end_headers(self) -> None:
        return None


class _BodyRecorder:
    def __init__(self) -> None:
        self.body = b""

    def write(self, body: bytes) -> None:
        self.body += body
