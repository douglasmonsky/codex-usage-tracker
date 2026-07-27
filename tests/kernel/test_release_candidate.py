from __future__ import annotations

import ast
import json
from pathlib import Path

from codex_usage_tracker.kernel.interfaces.cli.main import COMMANDS
from codex_usage_tracker.kernel.interfaces.http.app import API_PREFIX, ROUTES
from codex_usage_tracker.kernel.interfaces.mcp.catalog import TOOL_SPECS
from codex_usage_tracker.kernel.schema import (
    ANALYTICAL_TABLES,
    MAX_INDEX_COUNT,
    REQUIRED_SCHEMA_OBJECTS,
)
from scripts.check_kernel_release_candidate import _measurement_failures
from scripts.generate_kernel_manifests import k9_disposition_proof_failures

_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_MODULE_PARTS = {
    "analysis",
    "compression",
    "compatibility",
    "content_index",
    "diagnostics",
    "otel",
    "recommendations",
    "telemetry",
    "usage_drain",
}
_TOOLS = (
    "usage_status",
    "usage_refresh",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)
_CLI = (
    "setup",
    "status",
    "refresh",
    "query",
    "export",
    "open",
    "service",
    "config",
    "content",
    "repair",
    "package",
)


def test_every_frozen_disposition_is_terminally_verified() -> None:
    manifest = json.loads(
        (_ROOT / "config/kernel-code-disposition-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert {entry["status"] for entry in manifest["entries"]} == {"verified"}
    assert k9_disposition_proof_failures(manifest) == []


def test_terminal_disposition_rejects_a_missing_target() -> None:
    manifest = json.loads(
        (_ROOT / "config/kernel-code-disposition-v1.json").read_text(
            encoding="utf-8"
        )
    )
    entry = next(
        item for item in manifest["entries"] if item["disposition"] == "transplant"
    )
    entry["target_path"] = "missing-k9-target.py"

    assert any(
        "verified target is absent" in failure
        for failure in k9_disposition_proof_failures(manifest)
    )


def test_release_catalogs_are_exact_and_publishable() -> None:
    plugin = json.loads(
        (_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    project = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert tuple(spec.name for spec in TOOL_SPECS) == _TOOLS
    assert COMMANDS == _CLI
    assert API_PREFIX == "/api/kernel/v1"
    assert len(ROUTES) == 7
    assert plugin["bundle"]["publishable"] is True
    assert plugin["version"] == "0.27.0"
    assert "exact, local-first codex usage facts" in plugin["description"].lower()
    assert 'version = "0.27.0"' in project
    assert "non-publishable" not in project.lower()


def test_runtime_tree_has_no_retired_module_or_import_owner() -> None:
    runtime = _ROOT / "src/codex_usage_tracker/kernel"
    for path in runtime.rglob("*.py"):
        relative_parts = set(path.relative_to(runtime).with_suffix("").parts)
        assert relative_parts.isdisjoint(_FORBIDDEN_MODULE_PARTS), path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            else:
                continue
            for name in imported:
                parts = set(name.split("."))
                assert parts.isdisjoint(_FORBIDDEN_MODULE_PARTS), (path, name)


def test_release_candidate_budget_is_measured_and_bounded() -> None:
    budget = json.loads(
        (_ROOT / "config/kernel-release-candidate-budget.json").read_text(
            encoding="utf-8"
        )
    )
    runtime_files = [
        path
        for path in (_ROOT / "src/codex_usage_tracker/kernel").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    console_files = [
        path
        for path in (
            _ROOT / "src/codex_usage_tracker/kernel/interfaces/http/console_assets"
        ).iterdir()
        if path.is_file()
    ]

    assert budget["schema"] == "codex-usage-tracker.kernel-rc-budget.v1"
    assert budget["headroom_percent"] <= 3
    assert _measurement_failures(
        budget,
        {
            "kernel_source_bytes": sum(
                path.stat().st_size for path in runtime_files
            ),
            "console_asset_bytes": sum(
                path.stat().st_size for path in console_files
            ),
            "analytical_tables": len(ANALYTICAL_TABLES),
            "analytical_indexes": MAX_INDEX_COUNT,
            "required_schema_objects": len(REQUIRED_SCHEMA_OBJECTS),
            "mcp_tools": len(TOOL_SPECS),
            "http_routes": len(ROUTES),
            "cli_commands": len(COMMANDS),
        },
    ) == []


def test_release_candidate_budget_rejects_excess_headroom_and_count_drift() -> None:
    budget = {
        "headroom_percent": 3,
        "kernel_source_bytes": 104,
        "mcp_tools": 7,
    }

    failures = _measurement_failures(
        budget,
        {"kernel_source_bytes": 100, "mcp_tools": 6},
    )

    assert "kernel_source_bytes ceiling 104 exceeds 3% maximum 103" in failures
    assert "mcp_tools catalog ceiling 7 must equal measured 6" in failures


def test_upgrade_guide_maps_every_retired_surface_category() -> None:
    manifest = json.loads(
        (_ROOT / "config/kernel-retired-surfaces-v1.json").read_text(
            encoding="utf-8"
        )
    )
    guide = (_ROOT / "docs/upgrade-0.26.md").read_text(encoding="utf-8")

    assert "config/kernel-retired-surfaces-v1.json" in guide
    for replacement in {entry["replacement"] for entry in manifest["entries"]}:
        assert f"`{replacement}`" in guide
    for surface_type in {entry["surface_type"] for entry in manifest["entries"]}:
        assert f"`{surface_type}`" in guide
