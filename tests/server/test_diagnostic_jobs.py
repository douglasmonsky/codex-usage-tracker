from __future__ import annotations

import threading
import time
from http import HTTPStatus
from pathlib import Path

from codex_usage_tracker.server.analysis_jobs import AnalysisJobRegistry
from codex_usage_tracker.server.diagnostic_jobs import (
    handle_diagnostic_job_start_request,
    handle_diagnostic_job_status_request,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def test_diagnostic_refresh_starts_in_background_and_reports_persisted_result_action(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    initialize_db(db_path)
    release = threading.Event()
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def work(include_archived, progress):
        assert include_archived is True
        progress(stage="source-analysis", completed_units=1, total_units=2)
        assert release.wait(timeout=2)
        return {"refreshed_sections": ["overview", "commands"]}

    registry = AnalysisJobRegistry()
    handle_diagnostic_job_start_request(
        "include_archived=true",
        db_path=db_path,
        job_name="all",
        total_units=2,
        work=work,
        registry=registry,
        has_valid_api_token=lambda _params: True,
        send_error=lambda _status, _message: None,
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert responses[0][0] == HTTPStatus.ACCEPTED
    started = responses[0][1]
    assert started["job_kind"] == "diagnostic-refresh"
    assert started["source_revision"] == "generation:0"
    assert started["status"] in {"pending", "running"}

    release.set()
    job_id = str(started["job_id"])
    deadline = time.monotonic() + 2
    while registry.status(job_id)["status"] in {"pending", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    completed = registry.status(job_id)
    assert completed["result"] == {"refreshed_sections": ["overview", "commands"]}
    assert completed["next"] == {"action": "reload_persisted_results"}


def test_diagnostic_job_start_and_status_require_token(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    initialize_db(db_path)
    errors: list[tuple[HTTPStatus, str]] = []
    registry = AnalysisJobRegistry()

    handle_diagnostic_job_start_request(
        "",
        db_path=db_path,
        job_name="overview",
        total_units=1,
        work=lambda _archived, _progress: {},
        registry=registry,
        has_valid_api_token=lambda _params: False,
        send_error=lambda status, message: errors.append((status, message)),
        send_json=lambda _status, _payload: None,
    )
    handle_diagnostic_job_status_request(
        "job_id=missing",
        registry=registry,
        has_valid_api_token=lambda _params: False,
        send_error=lambda status, message: errors.append((status, message)),
        send_json=lambda _status, _payload: None,
    )

    assert errors == [
        (HTTPStatus.FORBIDDEN, "Valid API token is required for diagnostic refresh"),
        (HTTPStatus.FORBIDDEN, "Valid API token is required for diagnostic refresh"),
    ]


def test_diagnostic_job_status_rejects_missing_job_id() -> None:
    errors: list[tuple[HTTPStatus, str]] = []
    handle_diagnostic_job_status_request(
        "",
        registry=AnalysisJobRegistry(),
        has_valid_api_token=lambda _params: True,
        send_error=lambda status, message: errors.append((status, message)),
        send_json=lambda _status, _payload: None,
    )
    assert errors == [(HTTPStatus.BAD_REQUEST, "job_id is required")]


def test_diagnostic_job_status_returns_not_found_for_unknown_job() -> None:
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []
    handle_diagnostic_job_status_request(
        "job_id=unknown",
        registry=AnalysisJobRegistry(),
        has_valid_api_token=lambda _params: True,
        send_error=lambda _status, _message: None,
        send_json=lambda status, payload: responses.append((status, payload)),
    )

    assert responses[0][0] == HTTPStatus.NOT_FOUND
    assert responses[0][1]["status"] == "missing"
    assert responses[0][1]["next"] == {"action": "restart"}


def initialize_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        init_db(conn)
