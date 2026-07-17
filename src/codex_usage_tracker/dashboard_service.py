"""Persistent localhost dashboard service support."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_SERVICE_PORT = 47821
SERVICE_HOST = "127.0.0.1"
SERVICE_LABEL = "com.codex-usage-tracker.dashboard"


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
    """Return whether an HTTP server responds at the dashboard root."""

    validate_service_port(port)
    try:
        with urlopen(  # noqa: S310 - fixed loopback URL only
            f"http://{SERVICE_HOST}:{port}/",
            timeout=timeout,
        ) as response:
            return response.status == 200
    except (OSError, URLError):
        return False
