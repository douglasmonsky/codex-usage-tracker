"""MCP server construction and legacy registration compatibility."""

from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.models import McpProfile
from mcp.server.fastmcp import FastMCP

compatibility_mcp = FastMCP("codex-usage-tracker")


def build_mcp_server(profile: McpProfile) -> FastMCP:
    """Build an isolated server containing exactly the selected profile."""
    from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
    from codex_usage_tracker.interfaces.mcp.registry import handler_for_profile

    server = FastMCP("codex-usage-tracker")
    for spec in tools_for_profile(profile):
        server.tool(name=spec.name)(handler_for_profile(spec, profile))
    return server
