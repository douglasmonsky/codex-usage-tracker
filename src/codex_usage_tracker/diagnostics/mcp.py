"""MCP-specific doctor checks."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

from codex_usage_tracker.diagnostics.types import DoctorCheck

# The doctor executes a selected local interpreter with a fixed import check and no shell.

PLUGIN_NAME = "codex-usage-tracker"


def check_mcp_config(repo_root: Path | None) -> DoctorCheck:
    if repo_root is None:
        return DoctorCheck(
            "MCP config",
            "warn",
            "Cannot check .mcp.json without a detected project root.",
            "Run from the codex-usage-tracker repo, or install with: codex-usage-tracker install-plugin",
        )
    config_path = repo_root / ".mcp.json"
    if not config_path.exists():
        return DoctorCheck(
            "MCP config",
            "fail",
            f"Missing MCP config: {config_path}",
            "Restore .mcp.json from the repo.",
        )
    data, data_check = _mcp_config_data(config_path)
    if data_check is not None:
        return data_check
    server, server_check = _mcp_config_server(data)
    if server_check is not None:
        return server_check
    command, command_check = _mcp_config_command(server)
    if command_check is not None:
        return command_check
    command_path = (repo_root / command).resolve() if command.startswith(".") else Path(command)
    if command.startswith(".") and not command_path.exists():
        return DoctorCheck(
            "MCP config",
            "warn",
            f"MCP command does not exist yet: {command_path}",
            "Create the venv and install the package.",
        )
    return DoctorCheck(
        "MCP config",
        "pass",
        f"MCP server command is configured: {command}{_mcp_config_env_detail(server)}.",
    )


def _mcp_config_data(config_path: Path) -> tuple[dict[str, object], DoctorCheck | None]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, DoctorCheck(
            "MCP config",
            "fail",
            f"MCP config is invalid JSON: {exc}",
            "Fix .mcp.json.",
        )
    return data if isinstance(data, dict) else {}, None


def _mcp_config_server(data: dict[str, object]) -> tuple[dict[str, object], DoctorCheck | None]:
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    server = servers.get(PLUGIN_NAME) if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        return {}, DoctorCheck(
            "MCP config",
            "fail",
            f"No {PLUGIN_NAME} MCP server entry found.",
            "Restore the server entry in .mcp.json.",
        )
    return dict(server), None


def _mcp_config_command(server: dict[str, object]) -> tuple[str, DoctorCheck | None]:
    command = server.get("command")
    if not isinstance(command, str) or not command:
        return "", DoctorCheck(
            "MCP config",
            "fail",
            "MCP server command is missing.",
            "Set the command to a Python executable that can import codex_usage_tracker.",
        )
    return command, None


def _mcp_config_env_detail(server: dict[str, object]) -> str:
    env = server.get("env")
    if isinstance(env, dict) and isinstance(env.get("PYTHONPATH"), str):
        return " with PYTHONPATH override"
    return ""


def check_mcp_runtime(repo_root: Path | None) -> DoctorCheck:
    if repo_root is None:
        return DoctorCheck(
            "MCP runtime",
            "warn",
            "Cannot validate the MCP runtime without a detected plugin root.",
            "Run from the codex-usage-tracker repo, or install with: codex-usage-tracker install-plugin",
        )
    server, server_check = _mcp_runtime_server(repo_root)
    if server_check is not None:
        return server_check
    args, args_check = _mcp_runtime_args(server)
    if args_check is not None:
        return args_check
    if _uses_bootstrap_launcher(args):
        return _check_mcp_launcher(repo_root, args)
    if not _uses_direct_mcp_module(args):
        return DoctorCheck(
            "MCP runtime",
            "warn",
            "MCP server does not use the expected module or launcher form, so import validation was skipped.",
            "Restore the generated plugin wrapper with: codex-usage-tracker install-plugin --force",
        )
    command = _resolve_mcp_command(server.get("command"), repo_root)
    if command is None:
        return _mcp_runtime_command_error(server)
    return _check_mcp_import_runtime(command, server, repo_root)


def _mcp_runtime_server(repo_root: Path) -> tuple[dict[str, object], DoctorCheck | None]:
    data, error = _read_mcp_json(repo_root / ".mcp.json")
    if error is not None:
        return {}, error
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    server = servers.get(PLUGIN_NAME) if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        return {}, DoctorCheck(
            "MCP runtime",
            "warn",
            "Cannot validate the MCP runtime until the codex-usage-tracker server is configured.",
            "Restore the server entry in .mcp.json.",
        )
    return dict(server), None


def _read_mcp_json(config_path: Path) -> tuple[dict[str, object], DoctorCheck | None]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, DoctorCheck(
            "MCP runtime",
            "warn",
            "Cannot validate the MCP runtime until .mcp.json is readable and valid.",
            "Fix .mcp.json, then rerun: codex-usage-tracker doctor --suggest-repair",
        )
    return data if isinstance(data, dict) else {}, None


def _mcp_runtime_args(server: dict[str, object]) -> tuple[list[str], DoctorCheck | None]:
    args = server.get("args")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return [], DoctorCheck(
            "MCP runtime",
            "warn",
            "MCP server args are missing or not a string list.",
            "Restore the generated plugin wrapper with: codex-usage-tracker install-plugin --force",
        )
    return args, None


def _mcp_runtime_command_error(server: dict[str, object]) -> DoctorCheck:
    return DoctorCheck(
        "MCP runtime",
        "fail",
        f"MCP server command is not executable: {server.get('command')!r}.",
        "Reinstall the plugin with a working Python: codex-usage-tracker install-plugin --force",
    )


def _check_mcp_import_runtime(
    command: str,
    server: dict[str, object],
    repo_root: Path,
) -> DoctorCheck:
    try:
        result = _run_mcp_import_check(command, server, repo_root)
    except subprocess.TimeoutExpired:
        return DoctorCheck(
            "MCP runtime",
            "fail",
            f"MCP Python timed out while importing the server: {command}",
            "Reinstall the plugin with a Python environment that can import codex_usage_tracker and mcp.",
        )
    except OSError as exc:
        return DoctorCheck(
            "MCP runtime",
            "fail",
            f"MCP Python could not be executed: {exc}",
            "Reinstall the plugin with a working Python: codex-usage-tracker install-plugin --force",
        )
    if result.returncode:
        return _mcp_import_failure(command, result)
    return DoctorCheck(
        "MCP runtime",
        "pass",
        f"MCP Python can import codex_usage_tracker.cli.mcp_server: {command}",
    )


def _run_mcp_import_check(
    command: str,
    server: dict[str, object],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    env = _mcp_runtime_env(server)
    cwd = _resolve_mcp_cwd(server.get("cwd"), repo_root)
    check = "import codex_usage_tracker.cli.mcp_server; import mcp.server.fastmcp"
    # The argument vector is fixed apart from the interpreter path selected by the user.
    return subprocess.run(
        [command, "-c", check],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _mcp_runtime_env(server: dict[str, object]) -> dict[str, str]:
    env = os.environ.copy()
    configured_env = server.get("env")
    if isinstance(configured_env, dict):
        env.update({str(key): str(value) for key, value in configured_env.items()})
    return env


def _mcp_import_failure(command: str, result: subprocess.CompletedProcess[str]) -> DoctorCheck:
    stderr = _first_error_line(result.stderr) or _first_error_line(result.stdout)
    detail = f"MCP Python cannot import the server: {command}"
    if stderr:
        detail += f" ({stderr})"
    return DoctorCheck(
        "MCP runtime",
        "fail",
        detail,
        (
            "If this is a source checkout, rerun: codex-usage-tracker install-plugin "
            "--python .venv/bin/python --force. Otherwise reinstall with pipx and rerun setup."
        ),
    )


def _uses_direct_mcp_module(args: list[str]) -> bool:
    return "-m" in args and "codex_usage_tracker.mcp_server" in args


def _uses_bootstrap_launcher(args: list[str]) -> bool:
    return any(arg.endswith("skills/codex-usage-tracker/scripts/run_mcp.py") for arg in args)


def _check_mcp_launcher(repo_root: Path, args: list[str]) -> DoctorCheck:
    script_args = [
        (repo_root / arg).resolve()
        for arg in args
        if arg.endswith("skills/codex-usage-tracker/scripts/run_mcp.py")
    ]
    if not script_args:
        return DoctorCheck(
            "MCP runtime",
            "warn",
            "MCP launcher script could not be resolved.",
            "Restore the bundled launcher path in .mcp.json.",
        )
    script_path = script_args[0]
    if not script_path.exists():
        return DoctorCheck(
            "MCP runtime",
            "fail",
            f"MCP launcher script is missing: {script_path}",
            "Restore skills/codex-usage-tracker/scripts/run_mcp.py.",
        )
    return DoctorCheck(
        "MCP runtime",
        "pass",
        "MCP bootstrap launcher is present; it validates or installs the runtime on startup.",
    )


def _resolve_mcp_command(command: object, repo_root: Path) -> str | None:
    if not isinstance(command, str) or not command:
        return None
    command_path = Path(command)
    if command_path.is_absolute():
        return str(command_path) if command_path.exists() else None
    if command.startswith("."):
        resolved = (repo_root / command_path).resolve()
        return str(resolved) if resolved.exists() else None
    return shutil.which(command)


def _resolve_mcp_cwd(cwd: object, repo_root: Path) -> Path:
    if not isinstance(cwd, str) or not cwd:
        return repo_root
    cwd_path = Path(cwd)
    return cwd_path if cwd_path.is_absolute() else (repo_root / cwd_path).resolve()


def _first_error_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def check_mcp_import() -> DoctorCheck:
    module_spec = importlib.util.find_spec("codex_usage_tracker.mcp_server")
    if module_spec is None:
        return DoctorCheck(
            "MCP module",
            "fail",
            "MCP server module could not be found.",
            'Install dependencies with: python -m pip install ".[dev]"',
        )
    sdk_spec = importlib.util.find_spec("mcp.server.fastmcp")
    if sdk_spec is None:
        return DoctorCheck(
            "MCP module",
            "fail",
            "FastMCP SDK dependency could not be found.",
            'Install dependencies with: python -m pip install ".[dev]"',
        )
    return DoctorCheck("MCP module", "pass", "MCP server module is discoverable.")
