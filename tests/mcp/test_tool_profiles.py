from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.interfaces.mcp import registry
from codex_usage_tracker.interfaces.mcp.core_tools import MAX_STATUS_PAYLOAD_BYTES
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server
from tests.release_catalog import (
    ADVANCED_MCP_TOOL_NAMES,
    ALL_MCP_TOOL_NAMES,
    CORE_MCP_TOOL_NAMES,
    FULL_MCP_TOOL_NAMES,
)

PLUGIN_NAME = "codex-usage-tracker"


def _write_status_wrapper(codex_home: Path, server: dict[str, object]) -> Path:
    root = codex_home.parent / "plugins" / PLUGIN_NAME
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": PLUGIN_NAME}), encoding="utf-8"
    )
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {PLUGIN_NAME: server}}), encoding="utf-8"
    )
    return root


def test_core_profile_has_exact_names_and_order() -> None:
    assert [tool.name for tool in tools_for_profile("core")] == list(CORE_MCP_TOOL_NAMES)


def test_core_timing_metadata_cannot_exceed_payload_budget() -> None:
    payload = {"padding": ""}
    payload["padding"] = "x" * (
        MAX_STATUS_PAYLOAD_BYTES - serialized_size(payload)
    )
    assert serialized_size(payload) == MAX_STATUS_PAYLOAD_BYTES
    handler = registry._timed_core_handler("usage_status", lambda: payload)

    with pytest.raises(ValueError, match="payload budget"):
        handler()


def test_core_timing_adapter_preserves_non_envelope_results() -> None:
    handler = registry._timed_core_handler("usage_status", lambda: "synthetic")

    assert handler() == "synthetic"


@pytest.mark.parametrize(
    ("name", "result", "args", "kwargs", "expected"),
    [
        ("usage_status", {}, (), {}, registry.MAX_STATUS_PAYLOAD_BYTES),
        ("usage_refresh", {}, (), {}, registry.MAX_REFRESH_PAYLOAD_BYTES),
        ("usage_analyze", {}, (), {}, registry.MAX_ANALYSIS_PAYLOAD_BYTES),
        (
            "usage_analyze",
            {"result_schema": registry.ANALYSIS_JOB_SCHEMA},
            (),
            {},
            registry.MAX_ANALYSIS_JOB_PAYLOAD_BYTES,
        ),
        ("usage_query", {}, (), {}, registry.MAX_QUERY_PAYLOAD_BYTES),
        ("usage_evidence", {}, (), {}, registry.MAX_EVIDENCE_PAYLOAD_BYTES),
        ("usage_allowance", {}, (), {}, registry.MAX_ALLOWANCE_PAYLOAD_BYTES),
        (
            "usage_job_status",
            {},
            ("synthetic-job", True),
            {},
            registry.MAX_REFRESH_PAYLOAD_BYTES,
        ),
        (
            "usage_job_status",
            {},
            ("synthetic-job",),
            {"include_result": False},
            registry.MAX_STATUS_PAYLOAD_BYTES,
        ),
    ],
)
def test_core_payload_budget_matches_each_core_tool_contract(
    name: str,
    result: dict[str, object],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    expected: int,
) -> None:
    assert (
        registry._core_payload_budget(
            name,
            result,
            args=args,
            kwargs=kwargs,
        )
        == expected
    )


def test_core_payload_budget_rejects_unknown_tools() -> None:
    with pytest.raises(registry.ToolCatalogError, match="unknown core tool"):
        registry._core_payload_budget("unknown", {}, args=(), kwargs={})


def test_profiles_are_strict_ordered_supersets() -> None:
    core = {tool.name for tool in tools_for_profile("core")}
    full = {tool.name for tool in tools_for_profile("full")}
    developer = {tool.name for tool in tools_for_profile("developer")}

    assert core < full < developer
    assert full == FULL_MCP_TOOL_NAMES
    assert developer == ALL_MCP_TOOL_NAMES


def test_advanced_full_profile_tools_are_explicit_and_active() -> None:
    advanced = {tool.name for tool in tools_for_profile("full") if tool.disposition == "advanced"}

    assert advanced == ADVANCED_MCP_TOOL_NAMES
    assert all(
        tool.lifecycle == "active" for tool in tools_for_profile("full") if tool.name in advanced
    )


def test_built_servers_expose_only_the_selected_profile() -> None:
    for profile in ("core", "full", "developer"):
        server = build_mcp_server(profile)
        actual = [tool.name for tool in asyncio.run(server.list_tools())]
        expected = [tool.name for tool in tools_for_profile(profile)]
        assert actual == expected


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, "core"), ("core", "core"), ("full", "full"), ("developer", "developer")],
)
def test_selected_profile_server_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, configured: str | None, expected: str
) -> None:
    from codex_usage_tracker.interfaces.mcp import server

    selected: list[str] = []
    if configured is None:
        monkeypatch.delenv(server.PROFILE_ENV, raising=False)
    else:
        monkeypatch.setenv(server.PROFILE_ENV, configured)

    def build(*, profile: str, container: object) -> SimpleNamespace:
        assert container is not None
        return SimpleNamespace(run=lambda: selected.append(profile))

    monkeypatch.setattr(
        server,
        "create_mcp_server",
        build,
    )

    server.main()

    assert selected == [expected]


def test_selected_profile_server_rejects_invalid_environment_before_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.interfaces.mcp import server

    monkeypatch.setenv(server.PROFILE_ENV, "unreviewed")
    monkeypatch.setattr(
        server,
        "create_mcp_server",
        lambda **_kwargs: pytest.fail("FastMCP server built for an invalid profile"),
    )

    with pytest.raises(SystemExit, match="expected one of: core, full, developer"):
        server.main()


def test_building_core_does_not_resolve_legacy_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_legacy_resolution(_name: str) -> object:
        raise AssertionError("core construction resolved legacy handlers")

    registry.tool_specs.cache_clear()
    monkeypatch.setattr(registry, "compatibility_handler", fail_legacy_resolution)
    monkeypatch.setattr(registry, "developer_handler", fail_legacy_resolution)

    server = build_mcp_server("core")

    assert [tool.name for tool in asyncio.run(server.list_tools())] == list(CORE_MCP_TOOL_NAMES)


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


def test_core_can_bind_one_explicit_application_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.application import status
    from codex_usage_tracker.application.container import build_application_container
    from codex_usage_tracker.application.paths import ApplicationPaths
    from codex_usage_tracker.dashboard_service import DashboardServiceStatus
    from codex_usage_tracker.interfaces.mcp.core_tools import usage_status

    monkeypatch.setattr(
        status,
        "dashboard_service_status",
        lambda *, home: DashboardServiceStatus(False, False, False, 47821, str(home)),
    )
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda _cls: (_ for _ in ()).throw(AssertionError("default home accessed"))),
    )
    container = build_application_container(
        ApplicationPaths(
            codex_home=tmp_path / ".codex",
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            rate_card_path=tmp_path / "rate-card.json",
            thresholds_path=tmp_path / "thresholds.json",
            projects_path=tmp_path / "projects.json",
        )
    )

    server = build_mcp_server("core", container=container)
    registered = server._tool_manager._tools
    payload = registered["usage_status"].fn()

    assert registered["usage_status"].fn is not usage_status
    assert payload["result"]["sources"]["canonical_rows"] == 0
    assert isinstance(payload["server_elapsed_ms"], float)
    assert payload["server_elapsed_ms"] >= 0
    assert list(payload) == sorted(payload)
    assert container.repositories.jobs is container.jobs


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


def test_core_status_reports_configured_runtime_readiness(tmp_path: Path) -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_status

    codex_home = tmp_path / ".codex"
    _write_status_wrapper(
        codex_home,
        {
            "command": sys.executable,
            "args": ["-m", "codex_usage_tracker.interfaces.mcp.server"],
            "env": {"CODEX_USAGE_TRACKER_MCP_PROFILE": "core"},
        },
    )

    payload = build_usage_status(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        codex_home=codex_home,
        home=tmp_path,
    )
    readiness = payload["result"]["conversational_readiness"]  # type: ignore[index]

    assert isinstance(readiness, dict)
    assert readiness["state"] == "ready"
    assert readiness["configured_profile"] == "core"
    assert readiness["runtime_version_matches"] is True


def test_core_status_reports_malformed_runtime_wrapper(tmp_path: Path) -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_status

    codex_home = tmp_path / ".codex"
    root = _write_status_wrapper(codex_home, {})
    (root / ".mcp.json").write_text("{broken", encoding="utf-8")

    payload = build_usage_status(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        codex_home=codex_home,
        home=tmp_path,
    )
    readiness = payload["result"]["conversational_readiness"]  # type: ignore[index]

    assert isinstance(readiness, dict)
    assert readiness["state"] == "unavailable"
    assert "doctor" in readiness["next_action"]


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


def test_core_job_status_exposes_bounded_durable_refresh_progress(tmp_path: Path) -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_job_status
    from codex_usage_tracker.jobs.adapters import request_hash
    from codex_usage_tracker.jobs.service import JobService
    from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository

    repository = AnalysisJobRepository(
        tmp_path / "usage.jobs.sqlite3",
        owner_id="mcp-progress-test",
    )
    semantic_key = request_hash("synthetic-refresh")
    repository.create_or_reuse(
        job_id="refresh-progress",
        job_kind="refresh",
        semantic_key=semantic_key,
        source_revision=request_hash("synthetic-source"),
        request_schema="refresh.request.v1",
        request={"history": "active", "aggregate_only": True, "execution": "async"},
        result_schema="codex-usage-tracker.refresh.v2",
    )
    repository.update_status(
        "refresh-progress",
        state="running",
        progress={
            "percent": 67,
            "stage": "derived_state",
            "completed": 4,
            "total": 6,
            "parsed_events": 120,
            "inserted_or_updated_events": 18,
            "elapsed_seconds": 42,
            "heartbeat_at": "2026-07-25T12:00:00Z",
            "input_generation": request_hash("synthetic-source"),
            "fixed_source_boundary": {
                "changed_source_files": 2,
                "added_bytes": 4_096,
                "newline_aligned": True,
                "exclusive_end": True,
            },
            "tail_pending": True,
            "tail_pending_files": 1,
            "tail_pending_bytes": 128,
        },
    )

    payload = build_usage_job_status(
        job_id="refresh-progress",
        db_path=tmp_path / "missing-usage.sqlite3",
        pricing_path=tmp_path / "missing-pricing.json",
        job_service=JobService(repository=repository),
    )

    result = payload["result"]
    assert isinstance(result, dict)
    assert result["state"] == "running"
    assert result["poll_after_ms"] == 1_000
    assert result["progress"] == {
        "completed": 4,
        "elapsed_seconds": 42,
        "fixed_source_boundary": {
            "added_bytes": 4_096,
            "changed_source_files": 2,
            "exclusive_end": True,
            "newline_aligned": True,
        },
        "heartbeat_at": "2026-07-25T12:00:00Z",
        "input_generation": request_hash("synthetic-source"),
        "inserted_or_updated_events": 18,
        "parsed_events": 120,
        "percent": 67,
        "stage": "derived_state",
        "tail_pending": True,
        "tail_pending_bytes": 128,
        "tail_pending_files": 1,
        "total": 6,
    }
    assert "synthetic-refresh" not in json.dumps(payload)


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
