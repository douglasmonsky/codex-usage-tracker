from __future__ import annotations

import asyncio

from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server
from tests.release_catalog import CORE_MCP_TOOL_NAMES, DEVELOPER_MCP_TOOL_NAMES, MCP_TOOL_NAMES


def test_core_profile_has_exact_names_and_order() -> None:
    assert [tool.name for tool in tools_for_profile("core")] == list(CORE_MCP_TOOL_NAMES)


def test_profiles_are_strict_ordered_supersets() -> None:
    core = {tool.name for tool in tools_for_profile("core")}
    full = {tool.name for tool in tools_for_profile("full")}
    developer = {tool.name for tool in tools_for_profile("developer")}

    assert core < full < developer
    assert full == (MCP_TOOL_NAMES - DEVELOPER_MCP_TOOL_NAMES) | set(CORE_MCP_TOOL_NAMES)
    assert developer == full | DEVELOPER_MCP_TOOL_NAMES


def test_built_servers_expose_only_the_selected_profile() -> None:
    for profile in ("core", "full", "developer"):
        server = build_mcp_server(profile)
        actual = [tool.name for tool in asyncio.run(server.list_tools())]
        expected = [tool.name for tool in tools_for_profile(profile)]
        assert actual == expected
