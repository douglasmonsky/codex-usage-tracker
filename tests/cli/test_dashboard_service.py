from __future__ import annotations

import plistlib
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from codex_usage_tracker.dashboard_service import (
    DEFAULT_SERVICE_PORT,
    SERVICE_LABEL,
    DashboardServiceStatus,
    build_launch_agent,
    dashboard_is_reachable,
    dashboard_service_status,
    install_dashboard_service,
    port_is_available,
    service_paths,
    uninstall_dashboard_service,
    validate_service_port,
)


class FakeRunner:
    def __init__(
        self,
        *,
        print_returncode: int = 1,
        bootstrap_returncode: int = 0,
    ) -> None:
        self.print_returncode = print_returncode
        self.bootstrap_returncode = bootstrap_returncode
        self.commands: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[1] == "print":
            return subprocess.CompletedProcess(
                command,
                self.print_returncode,
                "",
                "not loaded",
            )
        if command[1] == "bootstrap":
            return subprocess.CompletedProcess(
                command,
                self.bootstrap_returncode,
                "",
                "bootstrap failed",
            )
        return subprocess.CompletedProcess(command, 0, "", "")


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


def test_install_writes_valid_plist_and_bootstraps_user_domain(tmp_path: Path) -> None:
    runner = FakeRunner()
    python = tmp_path / "python"
    python.touch()

    status = install_dashboard_service(
        home=tmp_path,
        python=python,
        port=DEFAULT_SERVICE_PORT,
        platform="darwin",
        uid=501,
        runner=runner,
        port_available=lambda _: True,
        reachable=lambda _: True,
    )

    paths = service_paths(tmp_path)
    payload = plistlib.loads(paths.plist.read_bytes())
    assert payload["Label"] == SERVICE_LABEL
    assert runner.commands[-2:] == [
        ["launchctl", "bootstrap", "gui/501", str(paths.plist)],
        ["launchctl", "kickstart", "-k", f"gui/501/{SERVICE_LABEL}"],
    ]
    assert status == DashboardServiceStatus(True, True, True, 47821, "healthy")


def test_install_refuses_unknown_port_owner_without_writing(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()

    with pytest.raises(RuntimeError, match="47821 is already in use"):
        install_dashboard_service(
            home=tmp_path,
            python=python,
            port=DEFAULT_SERVICE_PORT,
            platform="darwin",
            uid=501,
            runner=FakeRunner(),
            port_available=lambda _: False,
            reachable=lambda _: False,
        )

    assert not service_paths(tmp_path).plist.exists()


def test_install_reuses_identical_healthy_service_without_restart(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(
        plistlib.dumps(
            build_launch_agent(python=python, home=tmp_path, port=DEFAULT_SERVICE_PORT),
            sort_keys=True,
        )
    )
    runner = FakeRunner(print_returncode=0)

    status = install_dashboard_service(
        home=tmp_path,
        python=python,
        platform="darwin",
        uid=501,
        runner=runner,
        port_available=lambda _: False,
        reachable=lambda _: True,
    )

    assert status.detail == "healthy"
    assert runner.commands == [
        ["launchctl", "print", f"gui/501/{SERVICE_LABEL}"],
    ]


def test_install_restores_previous_plist_when_bootstrap_fails(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    previous = plistlib.dumps(
        build_launch_agent(python=python, home=tmp_path, port=48123),
        sort_keys=True,
    )
    paths.plist.write_bytes(previous)

    with pytest.raises(RuntimeError, match="launchctl bootstrap failed"):
        install_dashboard_service(
            home=tmp_path,
            python=python,
            platform="darwin",
            uid=501,
            runner=FakeRunner(bootstrap_returncode=5),
            port_available=lambda _: True,
            reachable=lambda _: False,
        )

    assert paths.plist.read_bytes() == previous


def test_status_is_read_only_and_reports_loaded_but_unreachable(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(
        plistlib.dumps(
            build_launch_agent(
                python=python,
                home=tmp_path,
                port=DEFAULT_SERVICE_PORT,
            )
        )
    )
    runner = FakeRunner(print_returncode=0)

    status = dashboard_service_status(
        home=tmp_path,
        platform="darwin",
        uid=501,
        runner=runner,
        reachable=lambda _: False,
    )

    assert status == DashboardServiceStatus(
        True,
        True,
        False,
        DEFAULT_SERVICE_PORT,
        "loaded but unreachable",
    )
    assert runner.commands == [
        ["launchctl", "print", f"gui/501/{SERVICE_LABEL}"],
    ]


def test_status_reports_missing_installed_interpreter(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(
        plistlib.dumps(
            build_launch_agent(
                python=tmp_path / "missing-python",
                home=tmp_path,
                port=DEFAULT_SERVICE_PORT,
            )
        )
    )

    status = dashboard_service_status(
        home=tmp_path,
        platform="darwin",
        uid=501,
        runner=FakeRunner(print_returncode=0),
        reachable=lambda _: True,
    )

    assert status.reachable is False
    assert status.detail == f"interpreter missing: {tmp_path / 'missing-python'}"


def test_uninstall_is_idempotent_and_removes_only_managed_plist(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(
        plistlib.dumps(
            build_launch_agent(
                python=Path("/opt/tracker/bin/python"),
                home=tmp_path,
                port=DEFAULT_SERVICE_PORT,
            )
        )
    )
    unrelated = paths.plist.parent / "other.plist"
    unrelated.write_text("keep")
    runner = FakeRunner(print_returncode=0)

    status = uninstall_dashboard_service(
        home=tmp_path,
        platform="darwin",
        uid=501,
        runner=runner,
    )

    assert not paths.plist.exists()
    assert unrelated.read_text() == "keep"
    assert status == DashboardServiceStatus(False, False, False, 47821, "not installed")
    assert runner.commands[-1] == [
        "launchctl",
        "bootout",
        f"gui/501/{SERVICE_LABEL}",
    ]


def test_lifecycle_refuses_unsupported_platform(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()

    with pytest.raises(RuntimeError, match="macOS only"):
        install_dashboard_service(home=tmp_path, python=python, platform="linux")
