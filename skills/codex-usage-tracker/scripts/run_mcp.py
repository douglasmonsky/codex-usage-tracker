#!/usr/bin/env python3
"""Bootstrap and run the Codex Usage Tracker MCP server.

Marketplace installs mirror only the plugin bundle, not a repo-local virtual
environment. This launcher creates a cached runtime on first use, installs the
package from GitHub, and then execs the real MCP server.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - fixed argv only; no shell is invoked.
import sys
from pathlib import Path

PACKAGE_SPEC = os.environ.get(
    "CODEX_USAGE_TRACKER_PACKAGE_SPEC",
    "codex-usage-tracking==0.24.0rc1",
)
RUNTIME_VERSION = "0.24.0rc1"
PACKAGE_SPEC_MARKER = ".codex-usage-tracker-package-spec"
MODULE_CHECK = (
    "import importlib.metadata; "
    "importlib.metadata.version('codex-usage-tracking'); "
    "importlib.metadata.version('mcp')"
)
MODULE_ARGS = ["-m", "codex_usage_tracker.interfaces.mcp.server"]
PROFILE_ENV = "CODEX_USAGE_TRACKER_MCP_PROFILE"
DEFAULT_PROFILE = "core"
VALID_PROFILES = ("core", "full", "developer")


def main() -> int:
    try:
        profile = _selected_profile()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    plugin_root = Path(__file__).resolve().parents[3]
    runtime_python = _runtime_python()

    for candidate in _local_candidate_pythons(plugin_root):
        if candidate.exists() and _can_import_server(candidate):
            _exec_server(candidate, profile)

    if _can_use_runtime(runtime_python):
        _exec_server(runtime_python, profile)

    _ensure_runtime(runtime_python)
    if not _can_import_server(runtime_python):
        print(
            "Codex Usage Tracker runtime installed, but the MCP server could not be imported.",
            file=sys.stderr,
        )
        return 1
    _exec_server(runtime_python, profile)
    return 1


def _selected_profile() -> str:
    profile = os.environ.get(PROFILE_ENV, DEFAULT_PROFILE)
    if profile not in VALID_PROFILES:
        choices = ", ".join(VALID_PROFILES)
        raise ValueError(f"Invalid {PROFILE_ENV}={profile!r}; expected one of: {choices}.")
    return profile


def _local_candidate_pythons(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("CODEX_USAGE_TRACKER_MCP_PYTHON")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(plugin_root / ".venv" / _python_bin())
    return candidates


def _runtime_python() -> Path:
    configured = os.environ.get("CODEX_USAGE_TRACKER_RUNTIME_DIR")
    runtime_dir = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "codex-usage-tracker" / "mcp-runtime" / RUNTIME_VERSION
    )
    return runtime_dir / _python_bin()


def _python_bin() -> Path:
    return Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")


def _venv_root(python_path: Path) -> Path:
    return python_path.parents[1]


def _package_spec_marker(python_path: Path) -> Path:
    return _venv_root(python_path) / PACKAGE_SPEC_MARKER


def _can_use_runtime(python_path: Path) -> bool:
    if not python_path.exists() or not _can_import_server(python_path):
        return False
    marker = _package_spec_marker(python_path)
    try:
        return marker.read_text(encoding="utf-8").strip() == PACKAGE_SPEC
    except OSError:
        return False


def _can_import_server(python_path: Path) -> bool:
    try:
        result = subprocess.run(  # nosec B603 - explicit Python path and fixed probe argv.
            [str(python_path), "-c", MODULE_CHECK],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _ensure_runtime(python_path: Path) -> None:
    venv_root = _venv_root(python_path)
    if not python_path.exists():
        print(f"Creating Codex Usage Tracker MCP runtime at {venv_root}", file=sys.stderr)
        subprocess.run(  # nosec B603 - current interpreter and fixed venv argv.
            [sys.executable, "-m", "venv", str(venv_root)],
            check=True,
        )
    print(f"Installing Codex Usage Tracker MCP runtime from {PACKAGE_SPEC}", file=sys.stderr)
    subprocess.run(  # nosec B603 - selected runtime Python; pip receives argv without a shell.
        [str(python_path), "-m", "pip", "install", "--upgrade", PACKAGE_SPEC],
        check=True,
    )
    _package_spec_marker(python_path).write_text(PACKAGE_SPEC + "\n", encoding="utf-8")


def _exec_server(python_path: Path, profile: str) -> None:
    env = os.environ.copy()
    env[PROFILE_ENV] = profile
    os.execve(  # nosec B606 - intentional process replacement with fixed module argv.
        str(python_path),
        [str(python_path), *MODULE_ARGS],
        env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
