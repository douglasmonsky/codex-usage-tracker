"""Compatibility imports for the MCP server factory."""

from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.server import (
    build_mcp_server,
    create_mcp_server,
)

__all__ = ["build_mcp_server", "create_mcp_server"]
