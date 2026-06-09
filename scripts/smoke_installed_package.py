#!/usr/bin/env python3
"""Smoke-test installed Codex Usage Tracker package behavior.

The default mode builds this checkout into a temporary dist directory, installs
the wheel into a clean virtual environment, and verifies the installed CLI,
package data, and plugin installer. Use ``--from-pypi`` to verify the public
package instead, or ``--docker`` to run the same smoke in a clean Linux image.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import venv
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "codex-usage-tracking"
WHEEL_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
CONSOLE_SCRIPT = "codex-usage-tracker"
DEFAULT_DOCKER_IMAGE = "python:3.14-slim"
CLI_HELP_SUBCOMMANDS = [
    "setup",
    "doctor",
    "install-plugin",
    "upgrade-plugin",
    "uninstall-plugin",
    "refresh",
    "inspect-log",
    "rebuild-index",
    "reset-db",
    "summary",
    "query",
    "recommendations",
    "session",
    "context",
    "dashboard",
    "open-dashboard",
    "serve-dashboard",
    "expensive",
    "pricing-coverage",
    "export",
    "init-pricing",
    "update-pricing",
    "pin-pricing",
    "init-allowance",
    "parse-allowance",
    "update-rate-card",
    "init-thresholds",
    "init-projects",
    "support-bundle",
]

RESOURCE_PATHS = [
    "assets/icon.svg",
    "dashboard/dashboard.css",
    "dashboard/dashboard_format.js",
    "dashboard/dashboard_data.js",
    "dashboard/dashboard.js",
    "dashboard/dashboard_state.js",
    "dashboard/dashboard_template.html",
    "docs/dashboard-guide.html",
    "docs/assets/dashboard-insights.png",
    "docs/assets/dashboard-calls.png",
    "docs/assets/dashboard-threads.png",
    "docs/assets/dashboard-details.png",
    "rate_cards/codex-credit-rates.json",
    "skills/codex-usage-api/SKILL.md",
    "skills/codex-usage-tracker/SKILL.md",
]
BUILD_ARTIFACT_PATHS = [
    REPO_ROOT / "build",
    REPO_ROOT / "codex_usage_tracking.egg-info",
    REPO_ROOT / "src" / "codex_usage_tracking.egg-info",
    REPO_ROOT / "src" / "codex_usage_tracker.egg-info",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-pypi",
        action="store_true",
        help="Install codex-usage-tracking from PyPI instead of a locally built wheel.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="When used with --from-pypi, install this exact package version.",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Run this smoke test inside a clean Docker Python image.",
    )
    parser.add_argument(
        "--docker-image",
        default=DEFAULT_DOCKER_IMAGE,
        help=f"Docker image for --docker mode. Default: {DEFAULT_DOCKER_IMAGE}",
    )
    args = parser.parse_args(argv)

    if args.docker:
        return _run_in_docker(args)

    with tempfile.TemporaryDirectory(prefix="codex-usage-installed-smoke-") as temp_name:
        temp_dir = Path(temp_name)
        install_target = _resolve_install_target(args, temp_dir)
        venv_dir = temp_dir / "venv"
        _create_venv(venv_dir)
        python = _venv_python(venv_dir)
        command = _venv_console_script(venv_dir)

        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], capture_output=True)
        _run(
            [str(python), "-m", "pip", "install", "--no-cache-dir", install_target],
            capture_output=True,
        )

        _run([str(command), "--version"])
        _run([str(command), "--help"], capture_output=True)
        for subcommand in CLI_HELP_SUBCOMMANDS:
            _run([str(command), subcommand, "--help"], capture_output=True)
        _run([str(python), "-c", _import_check_code()])
        _run([str(python), "-c", _resource_check_code()])
        _smoke_plugin_install(command, temp_dir)

    print("Installed package smoke passed.")
    return 0


def _run_in_docker(args: argparse.Namespace) -> int:
    inner_args = ["scripts/smoke_installed_package.py"]
    if args.from_pypi:
        inner_args.append("--from-pypi")
    if args.version:
        inner_args.extend(["--version", args.version])
    setup_commands = ["python -m pip install --upgrade pip >/dev/null"]
    if not args.from_pypi:
        setup_commands.append("python -m pip install build >/dev/null")
    inner_command = " && ".join(
        setup_commands + ["python " + " ".join(shlex.quote(part) for part in inner_args)]
    )
    return _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/work",
            "-w",
            "/work",
            args.docker_image,
            "sh",
            "-lc",
            inner_command,
        ]
    ).returncode


def _resolve_install_target(args: argparse.Namespace, temp_dir: Path) -> str:
    if args.from_pypi:
        return f"{DISTRIBUTION_NAME}=={args.version}" if args.version else DISTRIBUTION_NAME

    version = _project_version()
    dist_dir = temp_dir / "dist"
    _clean_build_artifacts()
    try:
        _run([sys.executable, "-m", "build", "--outdir", str(dist_dir)], capture_output=True)
    finally:
        _clean_build_artifacts()
    wheel = dist_dir / f"{WHEEL_STEM}-{version}-py3-none-any.whl"
    if not wheel.exists():
        raise FileNotFoundError(f"expected built wheel was not created: {wheel}")
    return str(wheel)


def _clean_build_artifacts() -> None:
    for path in BUILD_ARTIFACT_PATHS:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _project_version() -> str:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _create_venv(venv_dir: Path) -> None:
    builder = venv.EnvBuilder(with_pip=True, clear=True)
    builder.create(venv_dir)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_console_script(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{CONSOLE_SCRIPT}.exe"
    return venv_dir / "bin" / CONSOLE_SCRIPT


def _import_check_code() -> str:
    return textwrap.dedent(
        f"""
        import {IMPORT_PACKAGE}
        print({IMPORT_PACKAGE}.__version__)
        """
    )


def _resource_check_code() -> str:
    return textwrap.dedent(
        f"""
        import json
        from importlib import resources

        resource_paths = {RESOURCE_PATHS!r}
        base = resources.files("{IMPORT_PACKAGE}.plugin_data")
        for resource_path in resource_paths:
            resource = base.joinpath(*resource_path.split("/"))
            if not resource.is_file():
                raise SystemExit(f"missing package resource: {{resource_path}}")
            size = len(resource.read_bytes())
            if size <= 0:
                raise SystemExit(f"empty package resource: {{resource_path}}")
        rate_card = json.loads(base.joinpath("rate_cards", "codex-credit-rates.json").read_text())
        if rate_card.get("schema") != "codex-usage-tracker-codex-rate-card-v1":
            raise SystemExit("bundled rate card schema mismatch")
        print(f"validated {{len(resource_paths)}} package resources")
        """
    )


def _smoke_plugin_install(command: Path, temp_dir: Path) -> None:
    plugin_dir = temp_dir / "plugin"
    marketplace = temp_dir / "marketplace.json"
    result = _run(
        [
            str(command),
            "install-plugin",
            "--plugin-dir",
            str(plugin_dir),
            "--marketplace",
            str(marketplace),
            "--force",
            "--json",
        ],
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    if payload.get("plugin_dir") != str(plugin_dir):
        raise SystemExit("install-plugin JSON reported an unexpected plugin_dir")
    required_files = [
        plugin_dir / ".codex-plugin" / "plugin.json",
        plugin_dir / ".mcp.json",
        plugin_dir / "assets" / "icon.svg",
        plugin_dir / "skills" / "codex-usage-api" / "SKILL.md",
        plugin_dir / "skills" / "codex-usage-tracker" / "SKILL.md",
        marketplace,
    ]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        raise SystemExit("plugin install missing files: " + ", ".join(str(path) for path in missing))
    manifest = json.loads((plugin_dir / ".codex-plugin" / "plugin.json").read_text())
    if manifest.get("name") != "codex-usage-tracker":
        raise SystemExit("plugin manifest name mismatch")
    if manifest.get("version") != _installed_version(command):
        raise SystemExit("plugin manifest version does not match installed CLI")
    mcp_config = json.loads((plugin_dir / ".mcp.json").read_text())
    server = mcp_config.get("mcpServers", {}).get("codex-usage-tracker", {})
    actual_python = Path(str(server.get("command", ""))).resolve()
    expected_python = _venv_python(command.parents[1]).resolve()
    reported_python = Path(str(payload.get("python_executable", ""))).resolve()
    if actual_python != expected_python:
        raise SystemExit("plugin MCP config command does not point at installed wheel Python")
    if reported_python != actual_python:
        raise SystemExit("install-plugin JSON and MCP config report different Python executables")
    if server.get("args") != ["-m", "codex_usage_tracker.mcp_server"]:
        raise SystemExit("plugin MCP config args do not launch the installed MCP server")
    if server.get("env", {}).get("PYTHONPATH"):
        raise SystemExit("installed-wheel plugin MCP config should not require PYTHONPATH")


def _installed_version(command: Path) -> str:
    result = _run([str(command), "--version"], capture_output=True)
    return result.stdout.strip().split()[-1]


def _run(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(shlex.quote(part) for part in command), flush=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture_output,
    )
    if result.returncode != 0:
        if capture_output:
            if result.stdout:
                print(result.stdout, file=sys.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, command)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
