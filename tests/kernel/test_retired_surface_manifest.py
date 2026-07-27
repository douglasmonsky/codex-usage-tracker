from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
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


def test_retired_inventory_preserves_k1_counts() -> None:
    entries = _manifest()["entries"]
    expected_counts = {
        "mcp_tool": 58,
        "http_route": 69,
        "cli_command": 91,
        "schema_id": 87,
        "table": 38,
        "console_route": 17,
        "frontend_asset": 508,
        "package_data_rule": 28,
        "source_module": 298,
    }
    assert {
        surface_type: sum(
            entry["surface_type"] == surface_type for entry in entries
        )
        for surface_type in _SURFACE_TYPES
    } == expected_counts


def test_retired_source_and_frontend_paths_are_absent() -> None:
    for entry in _manifest()["entries"]:
        if entry["surface_type"] not in {"source_module", "frontend_asset"}:
            continue
        assert not (_REPO_ROOT / entry["public_name"]).exists(), entry["public_name"]


def test_retired_surface_manifest_matches_generator() -> None:
    from scripts.generate_kernel_manifests import build_retired_surface_manifest

    assert _manifest() == build_retired_surface_manifest()


def test_k6_public_adapters_do_not_reactivate_retired_mcp_or_http_names() -> None:
    from codex_usage_tracker.kernel.interfaces.http.app import ROUTES
    from codex_usage_tracker.kernel.interfaces.mcp.catalog import TOOL_SPECS

    entries = _manifest()["entries"]
    retired_tools = {
        entry["public_name"]
        for entry in entries
        if entry["surface_type"] == "mcp_tool"
    }
    retired_routes = {
        entry["public_name"]
        for entry in entries
        if entry["surface_type"] == "http_route"
    }
    active_tools = {spec.name for spec in TOOL_SPECS}
    active_routes = {f"{method} {path}" for method, path in ROUTES}

    assert active_tools.isdisjoint(retired_tools)
    assert active_routes.isdisjoint(retired_routes)
