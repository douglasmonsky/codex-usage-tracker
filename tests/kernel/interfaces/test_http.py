from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from unittest.mock import create_autospec
from urllib.request import Request, urlopen

import pytest

import codex_usage_tracker.kernel.application.service as application_service
from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.hydration import HydrationPreset
from codex_usage_tracker.kernel.interfaces.http.app import API_PREFIX, HttpApp
from codex_usage_tracker.kernel.interfaces.http.server import create_server

from .support import active_runtime, synthetic_sources


def _application(tmp_path: Path) -> KernelApplication:
    return KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda _paths, _preset: None,
        source_provider=lambda _home: synthetic_sources(),
    )


def test_http_routes_match_application_and_reject_non_loopback_host(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    adapter = HttpApp(application)

    status = adapter.handle(
        "GET",
        f"{API_PREFIX}/status",
        headers={"Host": "127.0.0.1:8765"},
    )
    blocked = adapter.handle(
        "GET",
        f"{API_PREFIX}/status",
        headers={"Host": "example.com"},
    )
    stream = adapter.handle(
        "GET",
        f"{API_PREFIX}/events?limit=5",
        headers={
            "Host": "localhost:8765",
            "Origin": "http://localhost:8765",
            "Last-Event-ID": "0",
        },
    )

    assert json.loads(status.body)["generation"] == application.status()["generation"]
    assert blocked.status == 400
    assert stream.content_type == "text/event-stream"
    assert b"event: generation_committed" in stream.body


def test_real_loopback_listener_serves_new_status_prefix(tmp_path: Path) -> None:
    server = create_server(_application(tmp_path))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    host, port = server.server_address
    try:
        request = Request(
            f"http://{host}:{port}{API_PREFIX}/status",
            headers={"Host": f"127.0.0.1:{port}"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert payload["generation"] == 1


def test_http_refresh_transports_hydration_preset() -> None:
    launches = []
    application = create_autospec(KernelApplication, instance=True)

    def refresh(
        *,
        wait_seconds: float,
        hydration_preset: HydrationPreset,
    ) -> dict:
        launches.append(hydration_preset.value)
        return {"state": "queued", "wait_seconds": wait_seconds}

    application.refresh.side_effect = refresh

    response = HttpApp(application).handle(
        "POST",
        f"{API_PREFIX}/refresh",
        body=b'{"preset":"recent_90d"}',
        headers={"Host": "127.0.0.1:8765"},
    )

    assert response.status == 202
    assert launches == ["recent_90d"]


def test_real_listener_rejects_invalid_content_length(tmp_path: Path) -> None:
    server = create_server(_application(tmp_path))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    host, port = server.server_address
    try:
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(
                (
                    f"POST {API_PREFIX}/query HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    "Content-Length: nope\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
            )
            response = connection.recv(1_024)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert b" 400 " in response.splitlines()[0]


def test_http_query_response_budget_returns_a_bounded_client_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(application_service, "MAX_QUERY_RESPONSE_BYTES", 1)
    response = HttpApp(
        KernelApplication(
            RuntimePaths(tmp_path / "codex-home", tmp_path / "cache"),
            worker_launcher=lambda _paths, _preset: None,
        )
    ).handle(
        "POST",
        f"{API_PREFIX}/query",
        body=json.dumps(
            {"requests": [], "include_guidance": True}
        ).encode(),
        headers={"Host": "127.0.0.1:8765"},
    )

    assert response.status == 400
    assert json.loads(response.body) == {
        "error": "query response exceeds byte budget; lower request limits"
    }


def test_corrupt_cache_returns_sanitized_service_unavailable(
    tmp_path: Path,
) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.kernel.operational.parent.mkdir(parents=True)
    runtime.kernel.operational.write_bytes(b"not sqlite")
    response = HttpApp(
        KernelApplication(runtime, worker_launcher=lambda _paths, _preset: None)
    ).handle(
        "GET",
        f"{API_PREFIX}/status",
        headers={"Host": "127.0.0.1:8765"},
    )

    assert response.status == 503
    assert json.loads(response.body) == {
        "error": "kernel cache is unavailable"
    }
