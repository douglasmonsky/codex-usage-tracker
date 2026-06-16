"""Stable JSON payload builders shared by CLI and MCP surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def error_code(exc: BaseException) -> str:
    """Return a stable CLI error code for a user-facing exception."""

    if isinstance(exc, ValueError):
        return "invalid_value"
    if isinstance(exc, FileExistsError):
        return "file_exists"
    if isinstance(exc, FileNotFoundError):
        return "file_not_found"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, RuntimeError):
        return "runtime_error"
    if isinstance(exc, OSError):
        return "os_error"
    return "error"


def path_payload(path: Path) -> str:
    """Return a user-facing path string with home expansion applied."""

    return str(path.expanduser())


def refresh_result_payload(result: Any, *, schema: str) -> dict[str, Any]:
    """Return the stable JSON shape for refresh-like operations."""

    return {
        "schema": schema,
        "scanned_files": result.scanned_files,
        "parsed_events": result.parsed_events,
        "skipped_events": result.skipped_events,
        "inserted_or_updated_events": result.inserted_or_updated_events,
        "changed_source_files": result.changed_source_files,
        "append_source_files": result.append_source_files,
        "full_reparse_source_files": result.full_reparse_source_files,
        "inserted_records": result.inserted_records,
        "deleted_records": result.deleted_records,
        "affected_threads": result.affected_threads,
        "skipped_downstream_work": result.skipped_downstream_work,
        "db_path": result.db_path,
        "parser_diagnostics": result.parser_diagnostics,
    }


def plugin_install_payload(result: Any, *, schema: str) -> dict[str, Any]:
    """Return the stable JSON shape for install or upgrade plugin operations."""

    return {
        "schema": schema,
        "plugin_dir": path_payload(result.plugin_dir),
        "marketplace_path": path_payload(result.marketplace_path),
        "python_executable": path_payload(result.python_executable),
        "replaced_existing": result.replaced_existing,
        "restart_required": True,
    }


def plugin_uninstall_payload(result: Any) -> dict[str, Any]:
    """Return the stable JSON shape for plugin uninstall operations."""

    return {
        "schema": "codex-usage-tracker-plugin-uninstall-v1",
        "plugin_dir": path_payload(result.plugin_dir),
        "marketplace_path": path_payload(result.marketplace_path),
        "removed_plugin_path": result.removed_plugin_path,
        "removed_marketplace_entry": result.removed_marketplace_entry,
        "restart_required": True,
    }


def session_payload(
    rows: list[dict[str, Any]],
    *,
    requested_session_id: str | None,
    limit: int,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return the stable JSON shape for session usage rows."""

    return {
        "schema": "codex-usage-tracker-session-v1",
        "requested_session_id": requested_session_id,
        "resolved_session_id": rows[0].get("session_id") if rows else requested_session_id,
        "limit": limit,
        "privacy_mode": privacy_mode,
        "row_count": len(rows),
        "rows": rows,
    }
