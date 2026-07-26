from __future__ import annotations

import asyncio
import json
from pathlib import Path

from codex_usage_tracker.interfaces.mcp.compatibility_tools import compatibility_handler
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.registry import CORE_TOOL_NAMES, tool_specs
from codex_usage_tracker.interfaces.mcp.runtime import build_mcp_server

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = Path(__file__).with_name("fixtures") / "tool_names_021.json"
_CORE_NAMES = (
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)
_DEVELOPER_ONLY_NAMES = {
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_visualization_suggest",
    "usage_visualization_render",
}
_REMOVED_025_NAMES = {"generate_usage_dashboard"}


def _baseline_names() -> set[str]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return set(payload["tool_names"])


def test_profiles_preserve_every_021_pr290_public_name() -> None:
    full_names = {spec.name for spec in tools_for_profile("full")}
    developer_names = {spec.name for spec in tools_for_profile("developer")}

    assert _baseline_names() - _DEVELOPER_ONLY_NAMES - _REMOVED_025_NAMES <= full_names
    assert _baseline_names() - _REMOVED_025_NAMES <= developer_names


def test_exact_ordered_core_surface_is_unchanged() -> None:
    assert CORE_TOOL_NAMES == _CORE_NAMES
    assert tuple(spec.name for spec in tools_for_profile("core")) == _CORE_NAMES


def test_every_registered_legacy_callable_has_a_catalog_disposition() -> None:
    registered = {tool.name for tool in asyncio.run(build_mcp_server("developer").list_tools())}
    cataloged = {spec.name for spec in tool_specs()}

    assert registered
    assert registered == cataloged


def test_full_profile_registers_exact_legacy_callables_without_schema_wrappers() -> None:
    registered = build_mcp_server("full")._tool_manager._tools

    for name in _baseline_names() - _DEVELOPER_ONLY_NAMES - _REMOVED_025_NAMES:
        assert registered[name].fn is compatibility_handler(name)


def test_deprecated_specs_expose_complete_release_metadata() -> None:
    deprecated = [spec for spec in tool_specs() if spec.lifecycle == "deprecated"]

    assert deprecated
    for spec in deprecated:
        assert spec.replacement
        assert spec.deprecated_since
        assert getattr(spec, "final_supported", None)
        assert spec.remove_after


def test_every_non_core_spec_has_an_explicit_disposition() -> None:
    allowed = {"compatibility", "advanced", "developer", "deprecated"}

    for spec in tool_specs()[len(_CORE_NAMES) :]:
        assert getattr(spec, "disposition", None) in allowed


def test_deprecated_tool_descriptions_name_replacement_and_removal_release() -> None:
    registered = {tool.name: tool for tool in asyncio.run(build_mcp_server("full").list_tools())}

    for spec in tool_specs():
        if spec.lifecycle != "deprecated" or spec.minimum_profile == "developer":
            continue
        description = registered[spec.name].description or ""
        assert spec.replacement in description
        assert spec.remove_after in description


def test_profile_and_deprecation_docs_name_the_beta_kernel_cutover() -> None:
    mcp_docs = (_ROOT / "docs" / "mcp.md").read_text(encoding="utf-8")
    deprecations = (_ROOT / "docs" / "deprecations.md").read_text(encoding="utf-8")

    assert "one selected profile" in mcp_docs
    assert "does not ship runtime adapters for retired tools" in deprecations
    assert "Exactly six default tools" in deprecations
    assert "## Exact Retired MCP Inventory" in deprecations
    inventory = deprecations.split("## Exact Retired MCP Inventory", maxsplit=1)[
        1
    ].split("\n## ", maxsplit=1)[0]
    documented_names = {
        line.removeprefix("- `").removesuffix("`")
        for line in inventory.splitlines()
        if line.startswith("- `") and line.endswith("`")
    }
    kernel_names = set(_CORE_NAMES) - {"usage_analyze"}

    assert documented_names == (
        {spec.name for spec in tool_specs()} - kernel_names
    ) | _REMOVED_025_NAMES
