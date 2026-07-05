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
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
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
    "diagnostics",
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
    "dashboard/dashboard_call.css",
    "dashboard/dashboard_insights.css",
    "dashboard/dashboard_layout.css",
    "dashboard/dashboard_tables.css",
    "dashboard/dashboard_detail.css",
    "dashboard/dashboard_responsive.css",
    "dashboard/dashboard_format.js",
    "dashboard/dashboard_data.js",
    "dashboard/dashboard_analysis.js",
    "dashboard/dashboard_cells.js",
    "dashboard/dashboard_details.js",
    "dashboard/dashboard_insights.js",
    "dashboard/dashboard_tables.js",
    "dashboard/dashboard_filters.js",
    "dashboard/dashboard_status.js",
    "dashboard/dashboard_events.js",
    "dashboard/dashboard_actions.js",
    "dashboard/dashboard_live.js",
    "dashboard/dashboard_diagnostics.js",
    "dashboard/dashboard_call_diagnostics.js",
    "dashboard/dashboard.js",
    "dashboard/dashboard_state.js",
    "dashboard/dashboard_template.html",
    "dashboard/react/index.html",
    "dashboard/react/assets/dashboard-react.js",
    "dashboard/react/assets/index.css",
    "dashboard/locales/en.json",
    "dashboard/locales/vi.json",
    "dashboard/locales/es.json",
    "dashboard/locales/fr.json",
    "dashboard/locales/de.json",
    "dashboard/locales/pt.json",
    "dashboard/locales/ja.json",
    "dashboard/locales/zh-Hans.json",
    "dashboard/locales/ko.json",
    "dashboard/locales/ru.json",
    "dashboard/locales/it.json",
    "dashboard/locales/ar.json",
    "docs/dashboard-guide.html",
    "docs/examples/token-waste-conversation.md",
    "docs/examples/remediation-conversation.md",
    "docs/assets/dashboard-insights.png",
    "docs/assets/dashboard-calls.png",
    "docs/assets/dashboard-calls-preview.png",
    "docs/assets/dashboard-threads.png",
    "docs/assets/dashboard-diagnostics.png",
    "docs/assets/dashboard-diagnostics-git-expanded.png",
    "docs/assets/dashboard-details.png",
    "docs/assets/dashboard-call-investigator.png",
    "docs/assets/dashboard-call-investigator-preview.png",
    "docs/assets/dashboard-call-investigator-evidence.png",
    "docs/assets/plugin-prompts.png",
    "docs/assets/plugin-thread-leaderboard.png",
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
        _smoke_cli_lifecycle(command, temp_dir)

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
            "0",
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
    _smoke_served_dashboard(command, global_args, codex_home, dashboard_path, env)

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


def _smoke_served_dashboard(
    command: Path,
    global_args: list[str],
    codex_home: Path,
    dashboard_path: Path,
    env: dict[str, str],
) -> None:
    port = _unused_loopback_port()
    root_url = f"http://127.0.0.1:{port}"
    react_url = f"{root_url}/react-dashboard.html"
    legacy_url = f"{root_url}/{dashboard_path.name}"
    process_env = dict(env)
    process_env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [
            str(command),
            *global_args,
            "serve-dashboard",
            "--codex-home",
            str(codex_home),
            "--output",
            str(dashboard_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-refresh",
            "--context-api",
            "explicit",
        ],
        cwd=REPO_ROOT,
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process_output = ""
    try:
        react_html = _read_url_when_ready(react_url, process)
        legacy_html = _read_url(legacy_url)
        react_js = _read_url(f"{root_url}/codex-usage-tracker-assets/react/assets/dashboard-react.js")
        react_css = _read_url(f"{root_url}/codex-usage-tracker-assets/react/assets/index.css")
    finally:
        process_output = _stop_process(process)

    if react_url not in process_output:
        raise SystemExit("serve-dashboard output did not include React dashboard URL")
    if legacy_url not in process_output:
        raise SystemExit("serve-dashboard output did not include legacy dashboard URL")
    if 'id="usage-data"' not in react_html or '"api_token"' not in react_html:
        raise SystemExit("served React dashboard did not include live boot payload")
    if '"rows": []' not in react_html and '"rows":[]' not in react_html:
        raise SystemExit("served React dashboard boot payload should not embed aggregate rows")
    if '"limit_label": "All"' in react_html:
        raise SystemExit("served React dashboard should not default to an uncapped row request")
    if "dashboard" not in legacy_html.lower():
        raise SystemExit("served legacy dashboard route did not return dashboard HTML")
    if len(react_js) < 1000:
        raise SystemExit("served React JavaScript asset looked unexpectedly small")
    if "app-shell" not in react_css:
        raise SystemExit("served React CSS asset did not include dashboard shell styles")


def _read_url_when_ready(url: str, process: subprocess.Popen[str], timeout_seconds: float = 15.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"serve-dashboard exited before {url} became available")
        try:
            return _read_url(url)
        except Exception as exc:  # noqa: BLE001 - retry startup connection failures.
            last_error = exc
            time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {url}: {last_error}")


def _read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read().decode("utf-8")


def _stop_process(process: subprocess.Popen[str]) -> str:
    if process.poll() is None:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
    else:
        output, _ = process.communicate(timeout=5)
    return output or ""


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
