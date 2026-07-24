from __future__ import annotations

import asyncio
from inspect import getdoc

from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.registry import handler_for_profile, tool_specs
from codex_usage_tracker.interfaces.mcp.server import create_mcp_server


def _tool_names(server: object) -> list[str]:
    return [
        tool.name
        for tool in asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    ]


def test_server_factory_builds_isolated_profile_inventories() -> None:
    core = create_mcp_server(profile="core")
    full = create_mcp_server(profile="full")

    assert core is not full
    assert _tool_names(core) == [tool.name for tool in tools_for_profile("core")]
    assert _tool_names(full) == [tool.name for tool in tools_for_profile("full")]

    core.tool(name="_factory_isolation_probe")(lambda: None)

    assert "_factory_isolation_probe" in _tool_names(core)
    assert "_factory_isolation_probe" not in _tool_names(full)


def test_two_servers_with_the_same_profile_do_not_share_registries() -> None:
    first = create_mcp_server(profile="core")
    second = create_mcp_server(profile="core")

    first.tool(name="_first_only")(lambda: None)

    assert "_first_only" in _tool_names(first)
    assert "_first_only" not in _tool_names(second)


def test_server_preserves_exact_tool_descriptions() -> None:
    server = create_mcp_server(profile="developer")
    registered = server._tool_manager._tools

    for spec in tool_specs():
        handler = handler_for_profile(spec, "developer")
        expected = getdoc(handler) or f"Run {spec.name}."
        if spec.lifecycle == "deprecated":
            expected = (
                f"{expected} Deprecated since {spec.deprecated_since}; use "
                f"{spec.replacement} instead. Supported through "
                f"{spec.final_supported}; earliest removal is {spec.remove_after}."
            )
        assert registered[spec.name].description == expected
