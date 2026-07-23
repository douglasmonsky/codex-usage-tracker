from __future__ import annotations

import plistlib
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from pathlib import Path
from threading import Thread

import pytest

from codex_usage_tracker.cli import dashboard_service as cli_dashboard_service
from codex_usage_tracker.cli.parser import build_parser
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

cli_main = import_module("codex_usage_tracker.cli.main")


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
        "--no-refresh",
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
            assert self.path == "/api/health"
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


def test_install_waits_for_cached_dashboard_to_bind(tmp_path: Path, monkeypatch) -> None:
    python = tmp_path / "python"
    python.touch()
    attempts = 0

    def reachable(_: int) -> bool:
        nonlocal attempts
        attempts += 1
        return attempts == 25

    monkeypatch.setattr("codex_usage_tracker.dashboard_service.time.sleep", lambda _: None)

    status = install_dashboard_service(
        home=tmp_path,
        python=python,
        platform="darwin",
        uid=501,
        runner=FakeRunner(),
        port_available=lambda _: True,
        reachable=reachable,
    )

    assert status.reachable is True
    assert attempts == 25


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


def test_dashboard_service_parser_defaults_install_port() -> None:
    args = build_parser("en").parse_args(["dashboard-service", "install"])

    assert args.command == "dashboard-service"
    assert args.service_action == "install"
    assert args.port == DEFAULT_SERVICE_PORT


def test_dashboard_service_parser_accepts_install_port_override() -> None:
    args = build_parser("en").parse_args(
        ["dashboard-service", "install", "--port", "48123"]
    )

    assert args.port == 48123


def test_dashboard_service_uninstall_rejects_port_override() -> None:
    with pytest.raises(SystemExit):
        build_parser("en").parse_args(
            ["dashboard-service", "uninstall", "--port", "48123"]
        )


def test_dashboard_service_status_prints_stable_url(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_dashboard_service,
        "dashboard_service_status",
        lambda **_: DashboardServiceStatus(True, True, True, 47821, "healthy"),
    )

    args = build_parser("en").parse_args(["dashboard-service", "status"])

    assert cli_dashboard_service.run_dashboard_service(args) == 0
    assert capsys.readouterr().out == (
        "Dashboard service is healthy at http://127.0.0.1:47821\n"
    )


def test_dashboard_service_unhealthy_status_returns_one(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_dashboard_service,
        "dashboard_service_status",
        lambda **_: DashboardServiceStatus(
            True,
            True,
            False,
            47821,
            "loaded but unreachable",
        ),
    )

    args = build_parser("en").parse_args(["dashboard-service", "status"])

    assert cli_dashboard_service.run_dashboard_service(args) == 1
    assert capsys.readouterr().out == (
        "Dashboard service is loaded but unreachable; "
        "expected http://127.0.0.1:47821\n"
    )


def test_dashboard_service_install_forwards_port(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def install(**kwargs: object) -> DashboardServiceStatus:
        captured.update(kwargs)
        return DashboardServiceStatus(True, True, True, 48123, "healthy")

    monkeypatch.setattr(cli_dashboard_service, "install_dashboard_service", install)
    args = build_parser("en").parse_args(
        ["dashboard-service", "install", "--port", "48123"]
    )

    assert cli_dashboard_service.run_dashboard_service(args) == 0
    assert captured["port"] == 48123
    assert capsys.readouterr().out == (
        "Dashboard service installed at http://127.0.0.1:48123\n"
    )


def test_dashboard_service_command_is_registered() -> None:
    assert (
        cli_main._COMMAND_HANDLERS["dashboard-service"]
        is cli_dashboard_service.run_dashboard_service
    )


def test_dashboard_service_status_exposes_react_url_without_changing_root_url() -> None:
    status = DashboardServiceStatus(True, True, True, 47821, "healthy")

    assert status.url == "http://127.0.0.1:47821"
    assert status.react_url == "http://127.0.0.1:47821/react-dashboard.html"


def test_dashboard_service_help_is_localized() -> None:
    help_text = build_parser("zh-Hans").format_help()

    assert "管理本地仪表盘服务" in help_text
