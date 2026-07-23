"""Build one isolated MCP server for one selected tool profile."""

from __future__ import annotations

from inspect import getdoc

from codex_usage_tracker.application.container import ApplicationContainer
from codex_usage_tracker.interfaces.mcp.models import McpProfile, ToolSpec
from mcp.server.fastmcp import FastMCP

# Import compatibility only. Legacy decorators no longer write to this server.
compatibility_mcp = FastMCP("codex-usage-tracker")


def build_mcp_server(
    profile: McpProfile,
    *,
    container: ApplicationContainer | None = None,
) -> FastMCP:
    """Build an isolated server containing exactly the selected profile."""
    from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
    from codex_usage_tracker.interfaces.mcp.registry import (
        bound_core_handlers,
        handler_for_profile,
    )

    server = FastMCP("codex-usage-tracker")
    bound = (
        bound_core_handlers(container)
        if profile == "core" and container is not None
        else None
    )
    for spec in tools_for_profile(profile):
        handler = bound[spec.name] if bound is not None else handler_for_profile(spec, profile)
        server.tool(name=spec.name, description=_tool_description(spec, handler))(handler)
    return server


def _tool_description(spec: ToolSpec, handler: object) -> str:
    description = getdoc(handler) or f"Run {spec.name}."
    if spec.lifecycle != "deprecated":
        return description
    return (
        f"{description} Deprecated since {spec.deprecated_since}; use "
        f"{spec.replacement} instead. Supported through {spec.final_supported}; "
        f"earliest removal is {spec.remove_after}."
    )
