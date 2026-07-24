"""Transport adapters for running a composed MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def run_stdio(server: FastMCP) -> None:
    """Run one already-composed server on the default stdio transport."""
    server.run()
