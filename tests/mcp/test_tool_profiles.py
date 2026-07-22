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


def test_core_binds_stable_adapters_once() -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import (
        usage_allowance,
        usage_analyze,
        usage_evidence,
        usage_job_status,
        usage_query,
        usage_refresh,
        usage_status,
    )

    server = build_mcp_server("core")
    registered = server._tool_manager._tools
    status_spec = next(tool for tool in tools_for_profile("core") if tool.name == "usage_status")

    assert registered["usage_status"].fn is usage_status
    assert registered["usage_refresh"].fn is usage_refresh
    assert registered["usage_analyze"].fn is usage_analyze
    assert registered["usage_allowance"].fn is usage_allowance
    assert registered["usage_evidence"].fn is usage_evidence
    assert registered["usage_query"].fn is usage_query
    assert registered["usage_job_status"].fn is usage_job_status
    assert list(registered).count("usage_analyze") == list(registered).count("usage_query") == 1
    assert list(registered).count("usage_evidence") == 1
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


def test_core_job_status_returns_bounded_administrative_envelope(tmp_path: Path) -> None:
    from codex_usage_tracker.core.contracts import serialized_size
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_job_status
    from codex_usage_tracker.jobs.service import JobService

    payload = build_usage_job_status(
        job_id="missing-job",
        db_path=tmp_path / "missing.sqlite3",
        pricing_path=tmp_path / "missing-pricing.json",
        job_service=JobService(),
    )

    assert payload["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert payload["result_schema"] == "codex-usage-tracker.job.v1"
    assert payload["data_class"] == "administrative"
    assert serialized_size(payload) <= 16 * 1024


def test_core_job_result_budget_includes_envelope_overhead(tmp_path: Path) -> None:
    from codex_usage_tracker.core.contracts import serialized_size
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_job_status
    from codex_usage_tracker.jobs.adapters import AnalysisJobAdapter, request_hash
    from codex_usage_tracker.jobs.service import JobService

    raw = {
        "status": "completed",
        "stage": "completed",
        "created_at": "2026-07-22T12:00:00Z",
        "updated_at": "2026-07-22T12:01:00Z",
        "result": {"aggregate": "x" * 40_000},
    }
    service = JobService()
    adapter = AnalysisJobAdapter(
        lambda _job_id, include_result=False: raw,
        kind="analysis",
        request_hash=request_hash("bounded-result"),
        result_budget=48 * 1024,
    )
    service.register(kind="analysis", job_id="bounded-result", adapter=adapter)
    payload = build_usage_job_status(
        job_id="bounded-result",
        include_result=True,
        db_path=tmp_path / "missing.sqlite3",
        pricing_path=tmp_path / "missing-pricing.json",
        job_service=service,
    )

    assert payload["result"]["result"] is not None  # type: ignore[index]
    assert serialized_size(payload) <= 64 * 1024


@pytest.mark.parametrize("profile", ["full", "developer"])
def test_permissive_profiles_bind_historical_overlapping_handlers(profile: str) -> None:
    from codex_usage_tracker.cli.mcp_server import (
        refresh_usage_index,
        usage_query,
        usage_refresh_start,
        usage_refresh_status,
        usage_status,
    )

    server = build_mcp_server(profile)  # type: ignore[arg-type]
    registered = server._tool_manager._tools

    assert registered["usage_status"].fn is usage_status
    assert registered["usage_query"].fn is usage_query
    assert registered["refresh_usage_index"].fn is refresh_usage_index
    assert registered["usage_refresh_start"].fn is usage_refresh_start
    assert registered["usage_refresh_status"].fn is usage_refresh_status
