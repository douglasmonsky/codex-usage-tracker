"""Read-only environment diagnostics for the local Codex usage tracker."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostics_mcp import (
    check_mcp_config,
    check_mcp_import,
    check_mcp_runtime,
)
from codex_usage_tracker.diagnostics_types import DoctorCheck
from codex_usage_tracker.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.pricing import load_pricing_config
from codex_usage_tracker.store import SchemaMigrationError, refresh_metadata, schema_state

PLUGIN_NAME = "codex-usage-tracker"


def run_doctor(
    *,
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    dashboard_path: Path = DEFAULT_DASHBOARD_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    plugin_link: Path = DEFAULT_PLUGIN_LINK,
    marketplace_path: Path = DEFAULT_MARKETPLACE_PATH,
    repo_root: Path | None = None,
    suggest_repair: bool = False,
) -> dict[str, Any]:
    """Run read-only checks and return a structured report."""
    root = repo_root or _resolve_plugin_root(plugin_link) or find_project_root()
    checks = _doctor_checks(
        codex_home=codex_home,
        db_path=db_path,
        dashboard_path=dashboard_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        root=root,
    )
    return _doctor_report(checks, suggest_repair=suggest_repair)


def _doctor_checks(
    *,
    codex_home: Path,
    db_path: Path,
    dashboard_path: Path,
    pricing_path: Path,
    plugin_link: Path,
    marketplace_path: Path,
    root: Path | None,
) -> list[DoctorCheck]:
    return [
        _check_package_import(),
        _check_codex_sessions(codex_home),
        _check_database(db_path),
        _check_database_schema(db_path),
        _check_parser_diagnostics(db_path),
        _check_dashboard_target(dashboard_path),
        _check_pricing(pricing_path),
        _check_project_root(root),
        _check_plugin_link(plugin_link, root),
        _check_marketplace(marketplace_path),
        check_mcp_config(root),
        check_mcp_runtime(root),
        check_mcp_import(),
    ]


def _doctor_report(checks: list[DoctorCheck], *, suggest_repair: bool) -> dict[str, Any]:
    fail_count = _count_check_status(checks, "fail")
    warn_count = _count_check_status(checks, "warn")
    report: dict[str, Any] = {
        "schema": "codex-usage-tracker-doctor-v1",
        "status": _doctor_status(fail_count=fail_count, warn_count=warn_count),
        "failures": fail_count,
        "warnings": warn_count,
        "checks": [check.to_dict() for check in checks],
    }
    if suggest_repair:
        report["repair_suggestions"] = _doctor_repair_suggestions(checks)
    return report


def _count_check_status(checks: list[DoctorCheck], status: str) -> int:
    return sum(1 for check in checks if check.status == status)


def _doctor_status(*, fail_count: int, warn_count: int) -> str:
    if fail_count:
        return "fail"
    if warn_count:
        return "warn"
    return "pass"


def _doctor_repair_suggestions(checks: list[DoctorCheck]) -> list[str]:
    return [
        check.remediation
        for check in checks
        if check.status in {"warn", "fail"} and check.remediation
    ]


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


def _check_database_schema(db_path: Path) -> DoctorCheck:
    try:
        state = schema_state(db_path)
    except SchemaMigrationError as exc:
        return DoctorCheck(
            "Database schema",
            "fail",
            str(exc),
            "Run: codex-usage-tracker rebuild-index after confirming your local aggregate index can be regenerated.",
        )
    if not state["exists"]:
        return DoctorCheck(
            "Database schema",
            "warn",
            "Database schema has not been initialized yet.",
            "Run: codex-usage-tracker refresh",
        )
    version = state["schema_version"]
    expected = state["expected_schema_version"]
    if version != expected:
        return DoctorCheck(
            "Database schema",
            "warn",
            f"Database schema is at version {version}; expected {expected}.",
            "Run: codex-usage-tracker rebuild-index if refresh does not migrate it cleanly.",
        )
    if not state["checksum_matches"]:
        return DoctorCheck(
            "Database schema",
            "warn",
            "usage_events schema checksum does not match the package schema.",
            "Run: codex-usage-tracker rebuild-index after confirming your local aggregate index can be regenerated.",
        )
    return DoctorCheck(
        "Database schema",
        "pass",
        f"Schema version {version} is current.",
    )


def _check_parser_diagnostics(db_path: Path) -> DoctorCheck:
    try:
        metadata = refresh_metadata(db_path)
    except SchemaMigrationError as exc:
        return DoctorCheck(
            "Parser diagnostics",
            "fail",
            f"Parser diagnostics are unavailable because database migration failed: {exc}",
            "Run: codex-usage-tracker rebuild-index after resolving the database schema warning.",
        )
    if not metadata:
        return DoctorCheck(
            "Parser diagnostics",
            "warn",
            "No parser diagnostics are available yet.",
            "Run: codex-usage-tracker refresh",
        )
    diagnostics = {
        key.removeprefix("parser_"): _safe_int(value)
        for key, value in metadata.items()
        if key.startswith("parser_")
    }
    drift_keys = [
        key
        for key in (
            "missing_last_token_usage",
            "missing_total_token_usage",
            "missing_cumulative_total",
            "unknown_event_shape",
            "partial_field_count",
            "invalid_integer",
        )
        if diagnostics.get(key, 0)
    ]
    skipped = _safe_int(metadata.get("skipped_events"))
    if skipped or drift_keys:
        parts = [f"skipped_events={skipped}"] if skipped else []
        parts.extend(f"{key}={diagnostics[key]}" for key in drift_keys)
        return DoctorCheck(
            "Parser diagnostics",
            "warn",
            "Schema drift detected in latest refresh: " + ", ".join(parts) + ".",
            "Run: codex-usage-tracker inspect-log <path> on a skipped log, then rebuild-index after updating parser support.",
        )
    parsed = metadata.get("parsed_events", "0")
    scanned = metadata.get("scanned_files", "0")
    return DoctorCheck(
        "Parser diagnostics",
        "pass",
        f"Latest refresh parsed {parsed} events from {scanned} files with no drift diagnostics.",
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




















def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
