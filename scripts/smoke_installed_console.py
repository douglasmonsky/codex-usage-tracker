#!/usr/bin/env python3
"""Smoke the installed K7 Console or retained public 0.25.1 Console assets."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import venv
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORACLE = _REPO_ROOT / "tests" / "kernel" / "fixtures" / "accounting-oracle-v1"


def _python(venv_root: Path) -> Path:
    return venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _command(venv_root: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv_root / ("Scripts" if os.name == "nt" else "bin") / (
        f"codex-usage-tracker{suffix}"
    )


def _install(venv_root: Path, target: str) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_root)
    python = _python(venv_root)
    subprocess.run(
        [python, "-m", "pip", "install", "--quiet", "--no-deps", target],
        check=True,
    )
    return python


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def smoke_current(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="kernel-console-installed-") as name:
        root = Path(name)
        _install(root / "venv", str(wheel.resolve()))
        codex_home = root / "codex"
        shutil.copytree(_ORACLE / "logs" / "sessions", codex_home / "sessions")
        shutil.copytree(
            _ORACLE / "logs" / "archived_sessions",
            codex_home / "archived_sessions",
        )
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        environment["CODEX_USAGE_TRACKER_CACHE_ROOT"] = str(root / "cache")
        command = _command(root / "venv")
        subprocess.run(
            [command, "refresh", "--wait", "30"],
            check=True,
            capture_output=True,
            env=environment,
        )
        port = _free_port()
        server = subprocess.Popen(
            [command, "service", "serve", "--port", str(port)],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            html = _await(f"http://127.0.0.1:{port}/live")
            if b"data-console-shell" not in html:
                raise RuntimeError("installed Console shell is missing")
            javascript = _await(
                f"http://127.0.0.1:{port}/assets/kernel-console/app.js"
            )
            if len(javascript) < 1_000:
                raise RuntimeError("installed Console JavaScript is incomplete")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    print("Installed K7 Console smoke passed.")


def _await(url: str) -> bytes:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return response.read()
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"installed Console did not serve {url}")


def smoke_reference_0251() -> None:
    with tempfile.TemporaryDirectory(prefix="console-reference-0251-") as name:
        root = Path(name)
        python = _install(root / "venv", "codex-usage-tracking==0.25.1")
        code = """
from importlib import resources
base = resources.files("codex_usage_tracker.plugin_data")
paths = (
    "dashboard/react/index.html",
    "dashboard/react/assets/dashboard-react.js",
    "dashboard/react/assets/index.css",
)
for path in paths:
    resource = base.joinpath(*path.split("/"))
    assert resource.is_file() and len(resource.read_bytes()) > 0, path
print("Installed public 0.25.1 Console reference smoke passed.")
"""
        subprocess.run([python, "-c", code], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--reference-0251", action="store_true")
    arguments = parser.parse_args()
    if arguments.reference_0251:
        smoke_reference_0251()
    elif arguments.wheel is not None:
        smoke_current(arguments.wheel)
    else:
        parser.error("--wheel or --reference-0251 is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
