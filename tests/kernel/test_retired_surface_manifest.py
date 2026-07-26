from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.interfaces.mcp.registry import tool_specs
from scripts.generate_kernel_manifests import (
    _cli_command_paths,
    _console_routes,
    _frontend_assets,
    _package_data_rules,
    _release_schema_ids,
    _schema_tables,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
_KERNEL_MCP_TOOLS = {
    "usage_status",
    "usage_refresh",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
}
_ALREADY_REMOVED_MCP_TOOLS = {"generate_usage_dashboard"}
_SURFACE_TYPES = {
    "mcp_tool",
    "http_route",
    "cli_command",
    "schema_id",
    "table",
    "console_route",
    "frontend_asset",
    "package_data_rule",
    "source_module",
}


def _manifest() -> dict[str, object]:
    assert _MANIFEST_PATH.is_file(), "K1 retired-surface manifest is missing"
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_retired_surface_manifest_has_complete_versioned_entries() -> None:
    manifest = _manifest()
    entries = manifest["entries"]

    assert manifest["schema"] == "codex-usage-tracker.kernel-retired-surfaces.v1"
    assert manifest["source_ref"] == "v0.25.1"
    assert {entry["surface_type"] for entry in entries} == _SURFACE_TYPES
    keys = [(entry["surface_type"], entry["public_name"]) for entry in entries]
    assert len(keys) == len(set(keys))
    for entry in entries:
        assert entry.keys() >= {
            "surface_type",
            "public_name",
            "current_owner",
            "replacement",
            "final_supported_release",
            "removal_release",
            "absence_or_migration_test",
        }
        assert entry["final_supported_release"] == "0.25.x"
        assert entry["removal_release"] == "0.26.0"
        assert entry["absence_or_migration_test"]


def test_retired_mcp_inventory_is_exact() -> None:
    manifest = _manifest()
    documented = {
        entry["public_name"]
        for entry in manifest["entries"]
        if entry["surface_type"] == "mcp_tool"
    }
    expected = (
        {spec.name for spec in tool_specs()} - _KERNEL_MCP_TOOLS
    ) | _ALREADY_REMOVED_MCP_TOOLS

    assert documented == expected


def test_retired_non_mcp_inventories_are_exact() -> None:
    entries = _manifest()["entries"]
    expected_by_type = {
        "cli_command": set(_cli_command_paths()),
        "schema_id": _release_schema_ids(),
        "table": set(_schema_tables()),
        "console_route": set(_console_routes()),
        "frontend_asset": set(_frontend_assets()),
        "package_data_rule": set(_package_data_rules()),
    }
    for surface_type, expected in expected_by_type.items():
        observed = {
            entry["public_name"]
            for entry in entries
            if entry["surface_type"] == surface_type
        }
        assert observed == expected


def test_retired_surface_manifest_matches_generator() -> None:
    from scripts.generate_kernel_manifests import build_retired_surface_manifest

    assert _manifest() == build_retired_surface_manifest()
