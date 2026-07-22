"""MCP tool-profile selection."""

from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.models import McpProfile, ToolSpec
from codex_usage_tracker.interfaces.mcp.registry import PROFILE_ORDER, ToolCatalogError, tool_specs


def tools_for_profile(profile: McpProfile) -> tuple[ToolSpec, ...]:
    """Return tools available in a profile, preserving catalog order."""
    rank = PROFILE_ORDER.get(profile)
    if rank is None:
        raise ToolCatalogError(f"unknown MCP profile: {profile}")
    return tuple(spec for spec in tool_specs() if PROFILE_ORDER[spec.minimum_profile] <= rank)
