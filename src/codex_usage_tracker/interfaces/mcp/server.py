"""Selected-profile MCP process entrypoint."""

from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.models import McpProfile
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server


def main(profile: McpProfile = "full") -> None:
    """Run exactly one MCP profile; the installed launcher selects core in Task 16."""
    build_mcp_server(profile).run()


if __name__ == "__main__":
    main()
