"""Read-only environment diagnostics for the local Codex usage tracker."""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.pricing import load_pricing_config

PLUGIN_NAME = "codex-usage-tracker"


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def run_doctor(
    *,
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    dashboard_path: Path = DEFAULT_DASHBOARD_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    plugin_link: Path = DEFAULT_PLUGIN_LINK,
    marketplace_path: Path = DEFAULT_MARKETPLACE_PATH,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run read-only setup checks and return a structured report."""

    root = repo_root or find_project_root() or _resolve_plugin_root(plugin_link)
    checks = [
        _check_package_import(),
        _check_codex_sessions(codex_home),
        _check_database(db_path),
        _check_dashboard_target(dashboard_path),
        _check_pricing(pricing_path),
        _check_project_root(root),
        _check_plugin_link(plugin_link, root),
        _check_marketplace(marketplace_path),
        _check_mcp_config(root),
        _check_mcp_import(),
    ]
    fail_count = sum(1 for check in checks if check.status == "fail")
    warn_count = sum(1 for check in checks if check.status == "warn")
    return {
        "status": "fail" if fail_count else "warn" if warn_count else "pass",
        "failures": fail_count,
        "warnings": warn_count,
        "checks": [check.to_dict() for check in checks],
    }


def find_project_root() -> Path | None:
    """Find a checkout root when running from source, installed package, or plugin cwd."""

    candidates = [Path.cwd()]
    module_path = Path(__file__).resolve()
    candidates.extend(module_path.parents)
    for candidate in candidates:
        if (candidate / ".codex-plugin" / "plugin.json").exists() and (
            candidate / ".mcp.json"
        ).exists():
            return candidate
    return None


def _looks_like_plugin_root(path: Path) -> bool:
    return (path / ".codex-plugin" / "plugin.json").exists() and (path / ".mcp.json").exists()


def _resolve_plugin_root(plugin_link: Path) -> Path | None:
    if not plugin_link.exists() and not plugin_link.is_symlink():
        return None
    target = plugin_link.resolve() if plugin_link.is_symlink() else plugin_link
    return target if _looks_like_plugin_root(target) else None


def _check_package_import() -> DoctorCheck:
    spec = importlib.util.find_spec("codex_usage_tracker")
    if spec is None:
        return DoctorCheck(
            "Python package",
            "fail",
            "codex_usage_tracker is not importable.",
            'Install from the repo with: python -m pip install ".[dev]"',
        )
    return DoctorCheck("Python package", "pass", "codex_usage_tracker is importable.")


def _check_codex_sessions(codex_home: Path) -> DoctorCheck:
    sessions = codex_home / "sessions"
    if sessions.is_dir():
        return DoctorCheck("Codex sessions", "pass", f"Found sessions at {sessions}.")
    if codex_home.exists():
        return DoctorCheck(
            "Codex sessions",
            "warn",
            f"Codex home exists, but sessions directory was not found: {sessions}",
            "Open Codex and run at least one session, or pass --codex-home to refresh.",
        )
    return DoctorCheck(
        "Codex sessions",
        "warn",
        f"Codex home was not found: {codex_home}",
        "Start Codex once before refreshing usage data.",
    )


def _check_database(db_path: Path) -> DoctorCheck:
    if db_path.exists():
        if os.access(db_path, os.R_OK):
            return DoctorCheck("SQLite database", "pass", f"Database is readable: {db_path}")
        return DoctorCheck(
            "SQLite database",
            "fail",
            f"Database exists but is not readable: {db_path}",
            "Check file permissions.",
        )
    if db_path.parent.exists():
        return DoctorCheck(
            "SQLite database",
            "warn",
            f"Database has not been created yet: {db_path}",
            "Run: codex-usage-tracker refresh",
        )
    return DoctorCheck(
        "SQLite database",
        "warn",
        f"Database directory has not been created yet: {db_path.parent}",
        "Run: codex-usage-tracker refresh",
    )


def _check_dashboard_target(dashboard_path: Path) -> DoctorCheck:
    if dashboard_path.exists():
        return DoctorCheck("Dashboard", "pass", f"Dashboard exists: {dashboard_path}")
    return DoctorCheck(
        "Dashboard",
        "warn",
        f"Dashboard has not been generated yet: {dashboard_path}",
        "Run: codex-usage-tracker dashboard",
    )


def _check_pricing(pricing_path: Path) -> DoctorCheck:
    config = load_pricing_config(pricing_path)
    if config.error:
        return DoctorCheck(
            "Pricing config",
            "fail",
            f"Pricing config is invalid: {config.error}",
            f"Fix or recreate {pricing_path}.",
        )
    if not config.loaded:
        return DoctorCheck(
            "Pricing config",
            "warn",
            f"No local pricing config found: {pricing_path}",
            "Cost estimates are disabled until you run: codex-usage-tracker update-pricing",
        )
    source = config.source or {}
    source_url = source.get("url")
    tier = source.get("tier")
    source_detail = f" Source: {source_url} ({tier})." if source_url and tier else ""
    return DoctorCheck(
        "Pricing config",
        "pass",
        f"Loaded {len(config.models)} local model pricing entries from {pricing_path}.{source_detail}",
    )


def _check_project_root(repo_root: Path | None) -> DoctorCheck:
    if repo_root is None:
        return DoctorCheck(
            "Plugin root",
            "warn",
            "Could not find .codex-plugin/plugin.json and .mcp.json from current paths.",
            "Run from the codex-usage-tracker repo, or install with: codex-usage-tracker install-plugin",
        )
    return DoctorCheck("Plugin root", "pass", f"Detected plugin root: {repo_root}")


def _check_plugin_link(plugin_link: Path, repo_root: Path | None) -> DoctorCheck:
    if not plugin_link.exists() and not plugin_link.is_symlink():
        return DoctorCheck(
            "Plugin registration",
            "warn",
            f"Plugin path is missing: {plugin_link}",
            "Run: codex-usage-tracker install-plugin",
        )
    if plugin_link.is_symlink():
        target = plugin_link.resolve()
        if _looks_like_plugin_root(target):
            kind = "source checkout" if repo_root and target == repo_root.resolve() else "plugin wrapper"
            return DoctorCheck(
                "Plugin registration",
                "pass",
                f"Plugin symlink points to a {kind}: {target}.",
            )
        return DoctorCheck(
            "Plugin registration",
            "fail",
            f"Plugin symlink points to {target}, but no plugin manifest and MCP config were found there.",
            "Replace it with: codex-usage-tracker install-plugin --force",
        )
    if plugin_link.is_dir() and _looks_like_plugin_root(plugin_link):
        return DoctorCheck(
            "Plugin registration",
            "pass",
            f"Plugin directory exists: {plugin_link}.",
        )
    if not plugin_link.is_symlink():
        return DoctorCheck(
            "Plugin registration",
            "fail",
            f"Plugin path exists but is not a generated plugin directory or symlink: {plugin_link}",
            "Move the existing path or install with: codex-usage-tracker install-plugin --force",
        )
    return DoctorCheck("Plugin registration", "pass", f"Plugin path exists: {plugin_link}.")


def _check_marketplace(marketplace_path: Path) -> DoctorCheck:
    if not marketplace_path.exists():
        return DoctorCheck(
            "Marketplace entry",
            "warn",
            f"Marketplace file is missing: {marketplace_path}",
            "Run: codex-usage-tracker install-plugin",
        )
    try:
        data = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DoctorCheck(
            "Marketplace entry",
            "fail",
            f"Marketplace file is invalid: {exc}",
            "Fix JSON or restore from backup before reinstalling.",
        )
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        return DoctorCheck(
            "Marketplace entry",
            "fail",
            "Marketplace JSON does not contain a plugins list.",
            "Fix marketplace structure before reinstalling.",
        )
    for entry in plugins:
        if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME:
            return DoctorCheck(
                "Marketplace entry",
                "pass",
                f"Found {PLUGIN_NAME} in {marketplace_path}.",
            )
    return DoctorCheck(
        "Marketplace entry",
        "warn",
        f"No {PLUGIN_NAME} entry found in {marketplace_path}.",
        "Run: codex-usage-tracker install-plugin",
    )


def _check_mcp_config(repo_root: Path | None) -> DoctorCheck:
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
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DoctorCheck(
            "MCP config",
            "fail",
            f"MCP config is invalid JSON: {exc}",
            "Fix .mcp.json.",
        )
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    server = servers.get(PLUGIN_NAME) if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        return DoctorCheck(
            "MCP config",
            "fail",
            f"No {PLUGIN_NAME} MCP server entry found.",
            "Restore the server entry in .mcp.json.",
        )
    command = server.get("command")
    if not isinstance(command, str) or not command:
        return DoctorCheck(
            "MCP config",
            "fail",
            "MCP server command is missing.",
            "Set the command to a Python executable that can import codex_usage_tracker.",
        )
    command_path = (repo_root / command).resolve() if command.startswith(".") else Path(command)
    if command.startswith(".") and not command_path.exists():
        return DoctorCheck(
            "MCP config",
            "warn",
            f"MCP command does not exist yet: {command_path}",
            "Create the venv and install the package.",
        )
    return DoctorCheck("MCP config", "pass", f"MCP server command is configured: {command}")


def _check_mcp_import() -> DoctorCheck:
    try:
        import codex_usage_tracker.mcp_server  # noqa: F401
    except Exception as exc:  # pragma: no cover - exact SDK import errors vary.
        return DoctorCheck(
            "MCP module",
            "fail",
            f"MCP server module could not be imported: {type(exc).__name__}: {exc}",
            'Install dependencies with: python -m pip install ".[dev]"',
        )
    return DoctorCheck("MCP module", "pass", "MCP server module imports successfully.")
