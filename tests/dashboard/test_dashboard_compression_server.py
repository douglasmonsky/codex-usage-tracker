from __future__ import annotations

import threading
import time
import urllib.parse
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.compression.jobs import CompressionJobRegistry
from codex_usage_tracker.server.api import _UsageDashboardHandler
from codex_usage_tracker.store.api import connect, init_db
from tests.store_dashboard_helpers import _http_error_json, _read_json


def test_dashboard_compression_routes_share_persistent_application_job(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)

    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=db_path,
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
        context_api_enabled=False,
        refresh_lock=threading.Lock(),
        compression_jobs=CompressionJobRegistry(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        headers = {"X-Codex-Usage-Token": "test-token"}
        forbidden = _http_error_json(f"{base_url}/api/compression/profile")
        missing = _read_json(
            f"{base_url}/api/compression/profile?include_archived=0",
            headers=headers,
        )
        started = _read_json(
            f"{base_url}/api/compression/start?include_archived=0",
            headers=headers,
            data=b"",
            method="POST",
        )
        run_id = urllib.parse.quote(str(started["run_id"]))
        completed = _wait_for_compression_run(base_url, run_id, headers)
        profile = _read_json(
            f"{base_url}/api/compression/profile?run_id={run_id}",
            headers=headers,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert forbidden["status"] == 403
    assert missing["schema"] == "codex-usage-tracker-compression-api-v1"
    assert missing["error"]["code"] == "compression_run_not_found"
    assert started["schema"] == "codex-usage-tracker-compression-api-v1"
    assert started["kind"] == "status"
    assert completed["status"] in {"completed", "completed_with_warnings"}
    assert profile["schema"] == "codex-usage-tracker-compression-api-v1"
    assert profile["kind"] == "profile"
    assert profile["run_id"] == started["run_id"]
    profile_payload = cast(dict[str, Any], profile["profile"])
    assert profile_payload["includes_raw_fragments"] is False


def _wait_for_compression_run(
    base_url: str,
    run_id: str,
    headers: dict[str, str],
) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while True:
        status = _read_json(
            f"{base_url}/api/compression/status?run_id={run_id}",
            headers=headers,
        )
        if status["status"] not in {"pending", "running"}:
            return status
        assert time.monotonic() < deadline, "compression analysis did not finish"
        time.sleep(0.01)
