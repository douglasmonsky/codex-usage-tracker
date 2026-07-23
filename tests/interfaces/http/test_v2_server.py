from __future__ import annotations

import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from codex_usage_tracker.server.api import _UsageDashboardHandler
from tests.store_dashboard_helpers import _http_error_json, _read_json


@contextmanager
def _v2_server(tmp_path: Path) -> Iterator[str]:
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_live_v2_capabilities_and_dynamic_job_routes_are_json(tmp_path: Path) -> None:
    with _v2_server(tmp_path) as base_url:
        capabilities = _read_json(f"{base_url}/api/v2/capabilities")
        job = _read_json(f"{base_url}/api/v2/jobs/missing?include_result=1")

    assert capabilities["schema"] == "codex-usage-tracker.capabilities.v2"
    assert capabilities["analysis_goals"]
    assert job["schema"] == "codex-usage-tracker.job.v1"
    assert job["error"]["code"] == "job.not_found"  # type: ignore[index]


def test_live_v2_returns_json_errors_for_wrong_method_unknown_route_and_token(
    tmp_path: Path,
) -> None:
    json_headers = {"Content-Type": "application/json"}
    with _v2_server(tmp_path) as base_url:
        wrong_method = _http_error_json(
            f"{base_url}/api/v2/capabilities",
            headers=json_headers,
            data=b"{}",
            method="POST",
        )
        unknown = _http_error_json(f"{base_url}/api/v2/unknown")
        forbidden = _http_error_json(
            f"{base_url}/api/v2/analyze",
            headers=json_headers,
            data=b"{}",
            method="POST",
        )

    assert wrong_method == {
        "status": 405,
        "payload": {
            "schema": "codex-usage-tracker.error.v1",
            "error": {"code": "method_not_allowed", "message": "Method not allowed"},
        },
    }
    assert unknown["status"] == 404
    assert unknown["payload"]["error"]["code"] == "not_found"  # type: ignore[index]
    assert forbidden["status"] == 403
    assert forbidden["payload"]["error"]["code"] == "forbidden"  # type: ignore[index]


def test_live_v2_declares_json_content_type_and_allow_header(tmp_path: Path) -> None:
    with _v2_server(tmp_path) as base_url:
        request = urllib.request.Request(
            f"{base_url}/api/v2/status",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)  # noqa: S310 - local test server only
        except urllib.error.HTTPError as exc:
            with exc:
                assert exc.code == 405
                assert exc.headers["Allow"] == "GET"
                assert exc.headers["Content-Type"] == "application/json; charset=utf-8"
        else:
            raise AssertionError("expected HTTPError")


def test_live_v2_retains_the_local_origin_guard(tmp_path: Path) -> None:
    with _v2_server(tmp_path) as base_url:
        rejected = _http_error_json(
            f"{base_url}/api/v2/capabilities",
            headers={"Origin": "https://example.invalid"},
        )

    assert rejected["status"] == 403
    assert rejected["payload"]["error"] == "Request host or origin is not allowed"  # type: ignore[index]
