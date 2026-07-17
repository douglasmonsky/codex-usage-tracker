from __future__ import annotations

import plistlib
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from codex_usage_tracker.dashboard_service import (
    DEFAULT_SERVICE_PORT,
    SERVICE_LABEL,
    build_launch_agent,
    dashboard_is_reachable,
    port_is_available,
    service_paths,
    validate_service_port,
)


def test_service_paths_stay_in_user_owned_locations(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)

    assert paths.plist == (
        tmp_path / "Library/LaunchAgents/com.codex-usage-tracker.dashboard.plist"
    )
    assert paths.stdout_log == (
        tmp_path / ".codex-usage-tracker/logs/dashboard-service.stdout.log"
    )
    assert paths.stderr_log == (
        tmp_path / ".codex-usage-tracker/logs/dashboard-service.stderr.log"
    )


def test_launch_agent_is_loopback_only_and_contains_no_content(tmp_path: Path) -> None:
    payload = build_launch_agent(
        python=Path("/opt/tracker/bin/python"),
        home=tmp_path,
        port=DEFAULT_SERVICE_PORT,
    )

    encoded = plistlib.dumps(payload).decode("utf-8")
    assert payload["Label"] == SERVICE_LABEL
    assert payload["ProgramArguments"] == [
        "/opt/tracker/bin/python",
        "-m",
        "codex_usage_tracker",
        "serve-dashboard",
        "--host",
        "127.0.0.1",
        "--port",
        "47821",
        "--context-api",
        "explicit",
    ]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert "--open" not in encoded
    assert "prompt" not in encoded.lower()
    assert "assistant" not in encoded.lower()


@pytest.mark.parametrize("port", [0, 1, 1023, 65536])
def test_service_port_rejects_privileged_or_invalid_values(port: int) -> None:
    with pytest.raises(ValueError, match="1024 through 65535"):
        validate_service_port(port)


def test_port_check_detects_an_existing_listener() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        assert port_is_available(port) is False
    finally:
        listener.close()

    assert port_is_available(port) is True


def test_dashboard_probe_distinguishes_reachable_http_server() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Codex Usage Tracker")

        def log_message(self, *_: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert dashboard_is_reachable(server.server_port) is True
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
