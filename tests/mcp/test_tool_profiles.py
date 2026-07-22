from __future__ import annotations

import asyncio

import pytest

from codex_usage_tracker.interfaces.mcp import registry
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server, compatibility_mcp
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


def test_building_core_does_not_resolve_or_mutate_legacy_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compatibility_tools = compatibility_mcp._tool_manager._tools
    before = dict(compatibility_tools)

    def fail_legacy_resolution() -> dict[str, object]:
        raise AssertionError("core construction resolved legacy handlers")

    registry.tool_specs.cache_clear()
    monkeypatch.setattr(registry, "_legacy_handlers", fail_legacy_resolution)

    server = build_mcp_server("core")

    assert [tool.name for tool in asyncio.run(server.list_tools())] == list(CORE_MCP_TOOL_NAMES)
    assert compatibility_tools == before


@pytest.mark.parametrize("profile", ["full", "developer"])
def test_permissive_profiles_bind_historical_overlapping_handlers(profile: str) -> None:
    from codex_usage_tracker.cli.mcp_server import usage_query, usage_status

    server = build_mcp_server(profile)  # type: ignore[arg-type]
    registered = server._tool_manager._tools

    assert registered["usage_status"].fn is usage_status
    assert registered["usage_query"].fn is usage_query
