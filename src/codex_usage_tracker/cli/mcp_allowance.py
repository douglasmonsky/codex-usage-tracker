"""Allowance intelligence MCP tools."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_diagnostics_report,
    build_allowance_export_report,
    build_allowance_history_report,
)
from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_RATE_CARD_PATH,
)


@mcp.tool()
def usage_allowance_history(
    window_kind: str | None = None,
    limit: int = 1000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Return normalized observed allowance history aggregate JSON."""
    return build_allowance_history_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_allowance_diagnostics(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Diagnose allowance movement against local credit estimates."""
    return build_allowance_diagnostics_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_allowance_export(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return strict-privacy allowance evidence bundle for manual sharing."""
    return build_allowance_export_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_report_limit(limit),
    ).payload


def _report_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit
