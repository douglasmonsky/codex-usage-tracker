#!/usr/bin/env python3
"""Smoke-test installed Codex Usage Tracker package behavior.

The default mode builds this checkout into a temporary dist directory, installs
the wheel into a clean virtual environment, and verifies the installed CLI,
package data, and plugin installer. Use ``--artifact-dir`` to smoke an already
built or downloaded wheel, ``--from-pypi`` to verify the public package, or
``--docker`` to run the same smoke in a clean Linux image.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import venv
from pathlib import Path

try:
    from scripts.smoke_dashboard_server import smoke_served_dashboard
    from scripts.smoke_installed_catalog import CLI_HELP_SUBCOMMANDS, RESOURCE_PATHS
except ModuleNotFoundError:  # Direct execution puts scripts/ on sys.path.
    from smoke_dashboard_server import smoke_served_dashboard
    from smoke_installed_catalog import CLI_HELP_SUBCOMMANDS, RESOURCE_PATHS

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "codex-usage-tracking"
WHEEL_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
CONSOLE_SCRIPT = "codex-usage-tracker"
DEFAULT_DOCKER_IMAGE = (
    "python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6"
)
REACT_ASSET_PATTERN = re.compile(
    r"""(?:src|href)=["'](?P<path>/codex-usage-tracker-assets/react/[^"']+)["']"""
)
EXPECTED_CORE_MCP_TOOLS = [
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
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
        help="Install this exact version with --from-pypi or --artifact-dir.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Install the sole matching wheel from an existing artifact directory.",
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
    if args.from_pypi and args.artifact_dir is not None:
        parser.error("--from-pypi and --artifact-dir cannot be used together")

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
        _smoke_cli_lifecycle(command, temp_dir)

        print("Installed package smoke passed.")
        return 0


def _run_in_docker(args: argparse.Namespace) -> int:
    inner_args = ["scripts/smoke_installed_package.py"]
    if args.from_pypi:
        inner_args.append("--from-pypi")
    if args.version:
        inner_args.extend(["--version", args.version])
    docker_mounts = ["-v", f"{REPO_ROOT}:/work"]
    if args.artifact_dir is not None:
        artifact_dir = args.artifact_dir.resolve()
        inner_args.extend(["--artifact-dir", "/release-dist"])
        docker_mounts.extend(["-v", f"{artifact_dir}:/release-dist:ro"])
    setup_commands = ["python -m pip install --upgrade pip >/dev/null"]
    if not args.from_pypi and args.artifact_dir is None:
        setup_commands.append("python -m pip install build >/dev/null")
    inner_command = " && ".join(
        setup_commands + ["python " + " ".join(shlex.quote(part) for part in inner_args)]
    )
    return _run(
        [
            "docker",
            "run",
            "--rm",
            *docker_mounts,
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
    if args.artifact_dir is not None:
        artifact_dir = args.artifact_dir.resolve()
        if not artifact_dir.is_dir():
            raise FileNotFoundError(f"artifact directory does not exist: {artifact_dir}")
        version_pattern = args.version or "*"
        wheels = sorted(artifact_dir.glob(f"{WHEEL_STEM}-{version_pattern}-*.whl"))
        if len(wheels) != 1:
            raise FileNotFoundError(
                "expected exactly one matching wheel in artifact directory; "
                f"found {[path.name for path in wheels]}"
            )
        return str(wheels[0])

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
        import asyncio
        import {IMPORT_PACKAGE}
        from {IMPORT_PACKAGE}.interfaces.mcp.runtime import build_mcp_server

        actual = [tool.name for tool in asyncio.run(build_mcp_server("core").list_tools())]
        expected = {EXPECTED_CORE_MCP_TOOLS!r}
        if actual != expected:
            raise SystemExit(f"installed core MCP profile mismatch: {{actual}}")
        print({IMPORT_PACKAGE}.__version__)
        print(f"validated {{len(actual)}} installed core MCP tools")
        """
    )


def _resource_check_code() -> str:
    return textwrap.dedent(
        f"""
        import json
        import re
        from importlib import resources

        resource_paths = {RESOURCE_PATHS!r}
        base = resources.files("{IMPORT_PACKAGE}.plugin_data")
        react_index = base.joinpath("dashboard", "react", "index.html").read_text()
        referenced_assets = {REACT_ASSET_PATTERN.pattern!r}
        for match in re.finditer(referenced_assets, react_index):
            resource_paths.append(match.group("path").replace("/codex-usage-tracker-assets/react/", "dashboard/react/", 1))
        resource_paths = sorted(set(resource_paths))
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
        plugin_dir / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py",
        marketplace,
    ]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        raise SystemExit(
            "plugin install missing files: " + ", ".join(str(path) for path in missing)
        )
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
    if server.get("args") != ["-m", "codex_usage_tracker.interfaces.mcp.server"]:
        raise SystemExit("plugin MCP config args do not launch the installed MCP server")
    server_env = server.get("env", {})
    if server_env.get("CODEX_USAGE_TRACKER_MCP_PROFILE") != "core":
        raise SystemExit("installed-wheel plugin MCP config does not select the core profile")
    if server_env.get("PYTHONPATH"):
        raise SystemExit("installed-wheel plugin MCP config should not require PYTHONPATH")


def _smoke_cli_lifecycle(command: Path, temp_dir: Path) -> None:
    home_dir = temp_dir / "home"
    codex_home = home_dir / ".codex"
    app_dir = home_dir / ".codex-usage-tracker"
    project_dir = temp_dir / "synthetic-project"
    plugin_dir = temp_dir / "setup-plugin"
    marketplace = temp_dir / "setup-marketplace.json"
    dashboard_path = temp_dir / "dashboard.html"
    support_path = temp_dir / "support-bundle.json"
    db_path = app_dir / "usage.sqlite3"
    pricing_path = app_dir / "pricing.json"
    allowance_path = app_dir / "allowance.json"
    rate_card_path = app_dir / "rate-card.json"
    thresholds_path = app_dir / "thresholds.json"
    projects_path = app_dir / "projects.json"
    home_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)
    project_dir.mkdir()
    _write_synthetic_codex_log(codex_home, project_dir)
    env = _isolated_home_env(home_dir)
    global_args = [
        "--db",
        str(db_path),
        "--pricing",
        str(pricing_path),
        "--allowance",
        str(allowance_path),
        "--rate-card",
        str(rate_card_path),
        "--thresholds",
        str(thresholds_path),
        "--projects",
        str(projects_path),
    ]

    setup_result = _run(
        [
            str(command),
            *global_args,
            "setup",
            "--codex-home",
            str(codex_home),
            "--plugin-dir",
            str(plugin_dir),
            "--marketplace",
            str(marketplace),
            "--skip-pricing",
            "--json",
        ],
        capture_output=True,
        env=env,
    )
    setup_payload = json.loads(setup_result.stdout)
    if setup_payload.get("schema") != "codex-usage-tracker-setup-v1":
        raise SystemExit("setup JSON schema mismatch")
    refresh = setup_payload.get("refresh", {})
    if int(refresh.get("parsed_events", 0)) < 1:
        raise SystemExit("setup did not parse synthetic usage event")
    if not db_path.exists():
        raise SystemExit("setup did not create tracker database")

    doctor_result = _run(
        [str(command), *global_args, "doctor", "--json"],
        capture_output=True,
        env=env,
    )
    doctor_payload = json.loads(doctor_result.stdout)
    if doctor_payload.get("schema") != "codex-usage-tracker-doctor-v1":
        raise SystemExit("doctor JSON schema mismatch")
    environment = doctor_payload.get("environment", {})
    package = environment.get("package", {})
    if package.get("version") != _installed_version(command):
        raise SystemExit("doctor environment did not report installed package version")
    if "dashboard_assets" not in environment:
        raise SystemExit("doctor environment did not report dashboard asset health")

    dashboard_result = _run(
        [
            str(command),
            *global_args,
            "dashboard",
            "--output",
            str(dashboard_path),
            "--limit",
            "5000",
            "--json",
        ],
        capture_output=True,
        env=env,
    )
    dashboard_payload = json.loads(dashboard_result.stdout)
    if dashboard_payload.get("schema") != "codex-usage-tracker-dashboard-v1":
        raise SystemExit("dashboard JSON schema mismatch")
    if not dashboard_path.exists():
        raise SystemExit("dashboard command did not write dashboard HTML")
    dashboard_html = dashboard_path.read_text(encoding="utf-8")
    if "<html" not in dashboard_html.lower() or "dashboard" not in dashboard_html.lower():
        raise SystemExit("dashboard HTML does not look like installed dashboard")
    smoke_served_dashboard(
        command,
        global_args,
        codex_home,
        dashboard_path,
        env,
        repo_root=REPO_ROOT,
    )

    support_result = _run(
        [
            str(command),
            *global_args,
            "--privacy-mode",
            "strict",
            "support-bundle",
            "--codex-home",
            str(codex_home),
            "--output",
            str(support_path),
            "--json",
        ],
        capture_output=True,
        env=env,
    )
    support_cli_payload = json.loads(support_result.stdout)
    if support_cli_payload.get("schema") != "codex-usage-tracker-support-bundle-v1":
        raise SystemExit("support-bundle CLI JSON schema mismatch")
    support_bundle = json.loads(support_path.read_text(encoding="utf-8"))
    if not support_bundle.get("issue_report", {}).get("safe_to_paste_after_review"):
        raise SystemExit("strict support bundle did not mark issue report as paste-safe")
    support_text = json.dumps(support_bundle)
    if str(temp_dir) in support_text or str(home_dir) in support_text:
        raise SystemExit("strict support bundle leaked local temp paths")


def _isolated_home_env(home_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)
    return env


def _write_synthetic_codex_log(codex_home: Path, project_dir: Path) -> None:
    session_id = "019f0000-0000-7000-8000-000000000001"
    session_path = codex_home / "sessions" / "2026" / "06" / "30" / f"{session_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "timestamp": "2026-06-30T12:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-06-30T12:00:00.000Z",
                "cwd": str(project_dir),
            },
        },
        {
            "timestamp": "2026-06-30T12:00:01.000Z",
            "type": "turn_context",
            "payload": {
                "cwd": str(project_dir),
                "model": "gpt-5.5-codex",
                "effort": "medium",
                "approval_policy": "never",
                "sandbox_policy": "danger-full-access",
            },
        },
        {
            "timestamp": "2026-06-30T12:00:02.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 200,
                        "cached_input_tokens": 50,
                        "output_tokens": 40,
                        "reasoning_output_tokens": 10,
                        "total_tokens": 300,
                    },
                    "last_token_usage": {
                        "input_tokens": 120,
                        "cached_input_tokens": 20,
                        "output_tokens": 35,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 180,
                    },
                    "model_context_window": 258400,
                },
            },
        },
    ]
    session_path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _installed_version(command: Path) -> str:
    result = _run([str(command), "--version"], capture_output=True)
    return result.stdout.strip().split()[-1]


def _run(
    command: list[str],
    *,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(shlex.quote(part) for part in command), flush=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
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
