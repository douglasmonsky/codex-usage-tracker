from __future__ import annotations

import asyncio
from pathlib import Path

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


def test_core_status_binds_stable_administrative_adapter() -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import usage_status

    server = build_mcp_server("core")
    registered = server._tool_manager._tools
    status_spec = next(tool for tool in tools_for_profile("core") if tool.name == "usage_status")

    assert registered["usage_status"].fn is usage_status
    assert status_spec.data_class == "administrative"


def test_core_status_returns_bounded_v2_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codex_usage_tracker.application import status
    from codex_usage_tracker.core.contracts import serialized_size
    from codex_usage_tracker.dashboard_service import DashboardServiceStatus
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_status

    monkeypatch.setattr(
        status,
        "conversational_readiness",
        lambda **_kwargs: {
            "schema": "codex-usage-tracker-conversational-readiness-v1",
            "state": "unavailable",
            "summary": "Not configured; current task tool exposure is not verified.",
            "next_action": "Configure the plugin.",
            "evidence": [],
        },
    )
    monkeypatch.setattr(
        status,
        "dashboard_service_status",
        lambda **_kwargs: DashboardServiceStatus(False, False, False, 47821, "not installed"),
    )

    payload = build_usage_status(
        db_path=tmp_path / "missing.sqlite3",
        pricing_path=tmp_path / "missing-pricing.json",
        codex_home=tmp_path / ".codex",
        home=tmp_path,
    )

    assert payload["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert payload["result_schema"] == "codex-usage-tracker.status.v2"
    assert payload["data_class"] == "administrative"
    assert payload["result"]["mcp"]["core_tools"] == list(CORE_MCP_TOOL_NAMES)  # type: ignore[index]
    assert serialized_size(payload) <= 16 * 1024


@pytest.mark.parametrize("profile", ["full", "developer"])
def test_permissive_profiles_bind_historical_overlapping_handlers(profile: str) -> None:
    from codex_usage_tracker.cli.mcp_server import usage_query, usage_status

    server = build_mcp_server(profile)  # type: ignore[arg-type]
    registered = server._tool_manager._tools

    assert registered["usage_status"].fn is usage_status
    assert registered["usage_query"].fn is usage_query
