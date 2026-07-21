"""MCP adapter for aggregate observed-subagent usage."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.reports.subagent_usage import build_subagent_usage_report


@mcp.tool()
def subagent_usage(
    since: str | None = None,
    parent_thread: str | None = None,
    agent_role: str | None = None,
    subagent_type: str | None = None,
    include_archived: bool = False,
    limit: int = 10,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Analyze distinct observed subagent sessions and their aggregate usage."""
    if response_format not in {"markdown", "json"}:
        raise ValueError("response_format must be markdown or json")
    report = build_subagent_usage_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        since=since,
        parent_thread=parent_thread,
        agent_role=agent_role,
        subagent_type=subagent_type,
        include_archived=include_archived,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    return report.payload() if response_format == "json" else report.render()
