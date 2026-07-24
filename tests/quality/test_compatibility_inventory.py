from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.interfaces.mcp.registry import tool_specs
from tests.release_catalog import DEPRECATED_MCP_TOOL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_deprecated_tools_match_release_inventory() -> None:
    deprecated = {spec.name for spec in tool_specs() if spec.lifecycle == "deprecated"}

    assert deprecated == DEPRECATED_MCP_TOOL_NAMES


def test_every_deprecated_tool_is_named_in_normative_ledger() -> None:
    ledger = (REPO_ROOT / "docs" / "deprecations.md").read_text(encoding="utf-8")

    for name in sorted(DEPRECATED_MCP_TOOL_NAMES):
        assert f"`{name}`" in ledger


def test_every_deprecated_tool_has_complete_tested_migration_metadata() -> None:
    specs = {spec.name: spec for spec in tool_specs()}

    for name in DEPRECATED_MCP_TOOL_NAMES:
        spec = specs[name]
        assert spec.replacement
        assert spec.deprecated_since == "0.22.0"
        assert spec.final_supported == "0.24.x"
        assert spec.remove_after == "0.25.0"
