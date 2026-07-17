"""Persistent localhost dashboard service support."""

from __future__ import annotations

import os
import plistlib
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_SERVICE_PORT = 47821
SERVICE_HOST = "127.0.0.1"
SERVICE_LABEL = "com.codex-usage-tracker.dashboard"

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class DashboardServicePaths:
    """User-owned files managed by the dashboard service commands."""

    plist: Path
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class DashboardServiceStatus:
    """Installed, launchd, and HTTP state for the persistent dashboard."""

    installed: bool
    loaded: bool
    reachable: bool
    port: int
    detail: str

    @property
    def url(self) -> str:
        return f"http://{SERVICE_HOST}:{self.port}"


def service_paths(home: Path) -> DashboardServicePaths:
    """Return the LaunchAgent and diagnostic log paths for one user."""

    logs = home / ".codex-usage-tracker" / "logs"
    return DashboardServicePaths(
        plist=home / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist",
        stdout_log=logs / "dashboard-service.stdout.log",
        stderr_log=logs / "dashboard-service.stderr.log",
    )


def validate_service_port(port: int) -> int:
    """Reject privileged and invalid service ports."""

    if not 1024 <= port <= 65535:
        raise ValueError("dashboard service port must be 1024 through 65535")
    return port


def build_launch_agent(*, python: Path, home: Path, port: int) -> dict[str, Any]:
    """Build a deterministic localhost-only LaunchAgent property list."""

    paths = service_paths(home)
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [
            str(python),
            "-m",
            "codex_usage_tracker",
            "serve-dashboard",
            "--host",
            SERVICE_HOST,
            "--port",
            str(validate_service_port(port)),
            "--context-api",
            "explicit",
            "--no-refresh",
        ],
        "EnvironmentVariables": {"HOME": str(home)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(paths.stdout_log),
        "StandardErrorPath": str(paths.stderr_log),
    }


def port_is_available(port: int) -> bool:
    """Return whether the fixed loopback port can be bound now."""

    validate_service_port(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        try:
            candidate.bind((SERVICE_HOST, port))
        except OSError:
            return False
    return True


def dashboard_is_reachable(port: int, *, timeout: float = 1.0) -> bool:
    """Return whether the dashboard's lightweight health endpoint responds."""

    validate_service_port(port)
    try:
        with urlopen(  # noqa: S310 - fixed loopback URL only
            f"http://{SERVICE_HOST}:{port}/api/health",
            timeout=timeout,
        ) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def install_dashboard_service(
    *,
    home: Path,
    python: Path,
    port: int = DEFAULT_SERVICE_PORT,
    platform: str = sys.platform,
    uid: int | None = None,
    runner: Runner = subprocess.run,
    port_available: Callable[[int], bool] = port_is_available,
    reachable: Callable[[int], bool] = dashboard_is_reachable,
) -> DashboardServiceStatus:
    """Install or update the current user's persistent dashboard service."""

    _require_macos(platform)
    validate_service_port(port)
    if not python.is_file():
        raise FileNotFoundError(f"dashboard service Python interpreter not found: {python}")

    paths = service_paths(home)
    desired = plistlib.dumps(
        build_launch_agent(python=python, home=home, port=port),
        sort_keys=True,
    )
    previous = paths.plist.read_bytes() if paths.plist.exists() else None
    target_uid = os.getuid() if uid is None else uid
    loaded = _is_loaded(target_uid, runner)

    if previous == desired and loaded:
        healthy = reachable(port)
        return DashboardServiceStatus(
            True,
            True,
            healthy,
            port,
            "healthy" if healthy else "loaded but unreachable",
        )

    if loaded:
        result = _run_launchctl(runner, "bootout", _target(target_uid))
        if result.returncode != 0:
            raise RuntimeError(_launchctl_error("bootout", result))

    if not port_available(port):
        if loaded and previous is not None:
            _restore_previous(paths, previous, target_uid, runner)
        raise RuntimeError(
            f"dashboard service port {port} is already in use; "
            "stop its owner or install with --port PORT"
        )

    paths.plist.parent.mkdir(parents=True, exist_ok=True)
    paths.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(paths.plist, desired)

    result = _run_launchctl(runner, "bootstrap", _domain(target_uid), str(paths.plist))
    if result.returncode != 0:
        _restore_after_failure(paths, previous, loaded, target_uid, runner)
        raise RuntimeError(_launchctl_error("bootstrap", result))

    result = _run_launchctl(runner, "kickstart", "-k", _target(target_uid))
    if result.returncode != 0:
        _restore_after_failure(paths, previous, loaded, target_uid, runner)
        raise RuntimeError(_launchctl_error("kickstart", result))

    healthy = _wait_until_reachable(port, reachable)
    return DashboardServiceStatus(
        True,
        True,
        healthy,
        port,
        "healthy" if healthy else "loaded but unreachable",
    )


def dashboard_service_status(
    *,
    home: Path,
    platform: str = sys.platform,
    uid: int | None = None,
    runner: Runner = subprocess.run,
    reachable: Callable[[int], bool] = dashboard_is_reachable,
) -> DashboardServiceStatus:
    """Inspect managed plist, launchd state, and localhost reachability."""

    _require_macos(platform)
    paths = service_paths(home)
    target_uid = os.getuid() if uid is None else uid
    loaded = _is_loaded(target_uid, runner)
    if not paths.plist.exists():
        detail = "loaded without managed plist" if loaded else "not installed"
        return DashboardServiceStatus(False, loaded, False, DEFAULT_SERVICE_PORT, detail)

    port, python = _read_installed_config(paths.plist)
    if not python.is_file():
        return DashboardServiceStatus(
            True,
            loaded,
            False,
            port,
            f"interpreter missing: {python}",
        )
    if not loaded:
        return DashboardServiceStatus(True, False, False, port, "installed but not loaded")

    healthy = reachable(port)
    return DashboardServiceStatus(
        True,
        True,
        healthy,
        port,
        "healthy" if healthy else "loaded but unreachable",
    )


def uninstall_dashboard_service(
    *,
    home: Path,
    platform: str = sys.platform,
    uid: int | None = None,
    runner: Runner = subprocess.run,
) -> DashboardServiceStatus:
    """Unload the managed agent and remove only its package-owned plist."""

    _require_macos(platform)
    paths = service_paths(home)
    target_uid = os.getuid() if uid is None else uid
    loaded = _is_loaded(target_uid, runner)
    port = DEFAULT_SERVICE_PORT
    if paths.plist.exists():
        port, _ = _read_installed_config(paths.plist)
    if loaded:
        result = _run_launchctl(runner, "bootout", _target(target_uid))
        if result.returncode != 0:
            raise RuntimeError(_launchctl_error("bootout", result))
    paths.plist.unlink(missing_ok=True)
    return DashboardServiceStatus(False, False, False, port, "not installed")


def _require_macos(platform: str) -> None:
    if platform != "darwin":
        raise RuntimeError("persistent dashboard service management is macOS only")


def _domain(uid: int) -> str:
    return f"gui/{uid}"


def _target(uid: int) -> str:
    return f"{_domain(uid)}/{SERVICE_LABEL}"


def _run_launchctl(runner: Runner, *arguments: str) -> subprocess.CompletedProcess[str]:
    return runner(
        ["launchctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _is_loaded(uid: int, runner: Runner) -> bool:
    return _run_launchctl(runner, "print", _target(uid)).returncode == 0


def _launchctl_error(action: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
    return f"launchctl {action} failed: {detail}"


def _read_installed_config(plist_path: Path) -> tuple[int, Path]:
    try:
        payload = plistlib.loads(plist_path.read_bytes())
        if payload.get("Label") != SERVICE_LABEL:
            raise ValueError("unexpected service label")
        arguments = payload["ProgramArguments"]
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise ValueError("invalid ProgramArguments")
        port_index = arguments.index("--port") + 1
        port = validate_service_port(int(arguments[port_index]))
        python = Path(arguments[0])
    except (IndexError, KeyError, TypeError, ValueError, plistlib.InvalidFileException) as exc:
        raise RuntimeError(f"invalid managed dashboard service plist: {plist_path}") from exc
    return port, python


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _restore_previous(
    paths: DashboardServicePaths,
    previous: bytes,
    uid: int,
    runner: Runner,
) -> None:
    _atomic_write(paths.plist, previous)
    _run_launchctl(runner, "bootstrap", _domain(uid), str(paths.plist))
    _run_launchctl(runner, "kickstart", "-k", _target(uid))


def _restore_after_failure(
    paths: DashboardServicePaths,
    previous: bytes | None,
    was_loaded: bool,
    uid: int,
    runner: Runner,
) -> None:
    _run_launchctl(runner, "bootout", _target(uid))
    if previous is None:
        paths.plist.unlink(missing_ok=True)
        return
    _atomic_write(paths.plist, previous)
    if was_loaded:
        _run_launchctl(runner, "bootstrap", _domain(uid), str(paths.plist))
        _run_launchctl(runner, "kickstart", "-k", _target(uid))


def _wait_until_reachable(
    port: int,
    reachable: Callable[[int], bool],
    *,
    attempts: int = 60,
    delay: float = 0.25,
) -> bool:
    for attempt in range(attempts):
        if reachable(port):
            return True
        if attempt + 1 < attempts:
            time.sleep(delay)
    return False
