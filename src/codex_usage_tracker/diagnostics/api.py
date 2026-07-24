"""Read-only environment diagnostics for the local Codex usage tracker."""

from __future__ import annotations

import platform
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.core.version import __version__
from codex_usage_tracker.diagnostics.doctor_checks import (
    _check_codex_sessions,
    _check_dashboard_target,
    _check_database,
    _check_database_schema,
    _check_marketplace,
    _check_package_import,
    _check_parser_diagnostics,
    _check_plugin_link,
    _check_pricing,
    _check_project_root,
    _resolve_plugin_root,
)
from codex_usage_tracker.diagnostics.doctor_checks import (
    find_project_root as find_project_root,
)
from codex_usage_tracker.diagnostics.mcp import (
    check_mcp_config,
    check_mcp_import,
    check_mcp_runtime,
)
from codex_usage_tracker.diagnostics.types import DoctorCheck
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository
from codex_usage_tracker.store.integrity import check_database_integrity

DASHBOARD_REQUIRED_ASSETS = (
    "dashboard_data.js",
    "dashboard_live.js",
    "dashboard_tables.js",
    "dashboard_responsive.css",
    "locales/en.json",
)


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
    environment = _doctor_environment(
        codex_home=codex_home,
        db_path=db_path,
        dashboard_path=dashboard_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        root=root,
    )
    checks = _doctor_checks(
        codex_home=codex_home,
        db_path=db_path,
        dashboard_path=dashboard_path,
        pricing_path=pricing_path,
        plugin_link=plugin_link,
        marketplace_path=marketplace_path,
        root=root,
    )
    return _doctor_report(
        checks,
        suggest_repair=suggest_repair,
        environment=environment,
    )


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
        _check_database_integrity(db_path),
        _check_analysis_jobs(db_path),
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


def run_integrity_report(*, db_path: Path = DEFAULT_DB_PATH) -> dict[str, object]:
    """Return the read-only database-integrity contract."""
    return check_database_integrity(db_path)


def _check_analysis_jobs(db_path: Path) -> DoctorCheck:
    counts = AnalysisJobRepository(db_path).counts()
    detail = "; ".join(f"{name}={count}" for name, count in counts.items())
    status = "warn" if counts["interrupted"] or counts["failed"] else "pass"
    remediation = (
        "Restart failed analyses if their results are still needed." if status == "warn" else None
    )
    return DoctorCheck("Analysis jobs", status, detail, remediation)


def _check_database_integrity(db_path: Path) -> DoctorCheck:
    report = check_database_integrity(db_path)
    state = str(report["state"])
    if state == "pass":
        return DoctorCheck(
            "Database integrity",
            "pass",
            "integrity_check=ok; foreign_key_check=0",
        )
    if state == "fail":
        return DoctorCheck(
            "Database integrity",
            "fail",
            (
                f"integrity errors={report['integrity_error_count']}; "
                f"foreign-key violations={report['foreign_key_violation_count']}"
            ),
            "Inspect with `codex-usage-tracker admin integrity --json` before repair.",
        )
    status = "warn" if report["error"] == "database_missing" else "fail"
    return DoctorCheck(
        "Database integrity",
        status,
        str(report["error"]),
        "Run a refresh to create a database."
        if status == "warn"
        else "Restore a readable database.",
    )


def _doctor_report(
    checks: list[DoctorCheck],
    *,
    suggest_repair: bool,
    environment: dict[str, Any],
) -> dict[str, Any]:
    fail_count = _count_check_status(checks, "fail")
    warn_count = _count_check_status(checks, "warn")
    report: dict[str, Any] = {
        "schema": "codex-usage-tracker-doctor-v1",
        "status": _doctor_status(fail_count=fail_count, warn_count=warn_count),
        "failures": fail_count,
        "warnings": warn_count,
        "environment": environment,
        "checks": [check.to_dict() for check in checks],
    }
    if suggest_repair:
        report["repair_suggestions"] = _doctor_repair_suggestions(checks)
    return report


def _doctor_environment(
    *,
    codex_home: Path,
    db_path: Path,
    dashboard_path: Path,
    pricing_path: Path,
    plugin_link: Path,
    marketplace_path: Path,
    root: Path | None,
) -> dict[str, Any]:
    return {
        "package": {
            "name": "codex-usage-tracker",
            "version": __version__,
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "paths": {
            "codex_home": str(codex_home.expanduser()),
            "codex_sessions": str(codex_home.expanduser() / "sessions"),
            "db_path": str(db_path.expanduser()),
            "dashboard_path": str(dashboard_path.expanduser()),
            "pricing_path": str(pricing_path.expanduser()),
            "plugin_link": str(plugin_link.expanduser()),
            "marketplace_path": str(marketplace_path.expanduser()),
            "plugin_root": str(root) if root else None,
        },
        "codex_logs": _codex_log_environment(codex_home),
        "dashboard_assets": _dashboard_asset_environment(),
    }


def _codex_log_environment(codex_home: Path) -> dict[str, Any]:
    expanded_home = codex_home.expanduser()
    sessions_dir = expanded_home / "sessions"
    jsonl_count = 0
    latest_mtime: float | None = None
    if sessions_dir.is_dir():
        for log_path in sessions_dir.rglob("*.jsonl"):
            jsonl_count += 1
            try:
                mtime = log_path.stat().st_mtime
            except OSError:
                continue
            latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)
    return {
        "codex_home_exists": expanded_home.exists(),
        "sessions_dir": str(sessions_dir),
        "sessions_dir_exists": sessions_dir.is_dir(),
        "jsonl_files": jsonl_count,
        "latest_jsonl_mtime": latest_mtime,
    }


def _dashboard_asset_environment() -> dict[str, Any]:
    try:
        dashboard_root = files("codex_usage_tracker.plugin_data").joinpath("dashboard")
        missing = [
            asset
            for asset in DASHBOARD_REQUIRED_ASSETS
            if not dashboard_root.joinpath(asset).is_file()
        ]
    except (AttributeError, FileNotFoundError, ModuleNotFoundError, TypeError) as exc:
        return {
            "available": False,
            "checked": list(DASHBOARD_REQUIRED_ASSETS),
            "missing": list(DASHBOARD_REQUIRED_ASSETS),
            "error": str(exc),
        }
    return {
        "available": not missing,
        "checked": list(DASHBOARD_REQUIRED_ASSETS),
        "missing": missing,
    }


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
