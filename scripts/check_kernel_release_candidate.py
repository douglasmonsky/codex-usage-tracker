#!/usr/bin/env python3
"""Fail closed on K9 release-candidate composition or budget drift."""

from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path
from typing import Any

from codex_usage_tracker.kernel.interfaces.cli.main import COMMANDS
from codex_usage_tracker.kernel.interfaces.http.app import ROUTES
from codex_usage_tracker.kernel.interfaces.http.console import CONSOLE_AREAS
from codex_usage_tracker.kernel.interfaces.mcp.catalog import TOOL_SPECS
from codex_usage_tracker.kernel.schema import (
    ANALYTICAL_TABLES,
    MAX_INDEX_COUNT,
    REQUIRED_SCHEMA_OBJECTS,
)

try:
    from scripts.generate_kernel_manifests import k9_disposition_proof_failures
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from generate_kernel_manifests import (  # type: ignore[import-not-found,no-redef]
        k9_disposition_proof_failures,
    )

_ROOT = Path(__file__).resolve().parents[1]
_BUDGET_PATH = _ROOT / "config/kernel-release-candidate-budget.json"
_DISPOSITION_PATH = _ROOT / "config/kernel-code-disposition-v1.json"
_RETIRED_PATH = _ROOT / "config/kernel-retired-surfaces-v1.json"
_PLUGIN_PATHS = (
    _ROOT / ".codex-plugin/plugin.json",
    _ROOT / ".mcp.json",
    _ROOT / "skills/usage-kernel/SKILL.md",
)
_FORBIDDEN_MODULE_PARTS = frozenset(
    {
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
)
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
    "repair",
    "package",
)
_CLI_PATHS = frozenset((*_CLI, "service serve"))
_SURFACE_REPLACEMENTS = {
    "mcp_tool": "six-tool kernel MCP",
    "http_route": "kernel HTTP API",
    "cli_command": "kernel operational CLI",
    "schema_id": "kernel fact schemas",
    "table": "kernel database schema",
    "console_route": "kernel timeline",
    "frontend_asset": "kernel timeline",
    "package_data_rule": "lean kernel package",
    "source_module": "none",
}
_BYTE_BUDGETS = frozenset(
    {
        "kernel_source_bytes",
        "console_asset_bytes",
        "plugin_bundle_bytes",
        "wheel_bytes",
        "sdist_bytes",
    }
)


def release_candidate_failures(*, dist: bool = False) -> list[str]:
    """Return deterministic final-absence, catalog, and size failures."""

    failures: list[str] = []
    budget = _load(_BUDGET_PATH)
    disposition = _load(_DISPOSITION_PATH)
    if {entry["status"] for entry in disposition["entries"]} != {"verified"}:
        failures.append("not every frozen disposition is verified")
    failures.extend(k9_disposition_proof_failures(disposition))
    failures.extend(retired_surface_failures())
    failures.extend(_runtime_import_failures())
    if tuple(spec.name for spec in TOOL_SPECS) != _TOOLS:
        failures.append("MCP catalog is not the exact six-tool catalog")
    if COMMANDS != _CLI:
        failures.append("CLI catalog differs from the retained operational catalog")
    measurements = {
        "kernel_source_bytes": _tree_bytes(
            _ROOT / "src/codex_usage_tracker/kernel"
        ),
        "console_asset_bytes": _tree_bytes(
            _ROOT
            / "src/codex_usage_tracker/kernel/interfaces/http/console_assets"
        ),
        "plugin_bundle_bytes": sum(path.stat().st_size for path in _PLUGIN_PATHS),
        "analytical_tables": len(ANALYTICAL_TABLES),
        "analytical_indexes": MAX_INDEX_COUNT,
        "required_schema_objects": len(REQUIRED_SCHEMA_OBJECTS),
        "mcp_tools": len(TOOL_SPECS),
        "http_routes": len(ROUTES),
        "cli_commands": len(COMMANDS),
    }
    failures.extend(_measurement_failures(budget, measurements))
    if dist:
        failures.extend(_distribution_budget_failures(budget))
    return failures


def retired_surface_failures() -> list[str]:
    """Reconcile every retired public entry with the live K9 inventory."""

    failures: list[str] = []
    entries = _load(_RETIRED_PATH)["entries"]
    active_tools = {spec.name for spec in TOOL_SPECS}
    active_routes = {f"{method} {path}" for method, path in ROUTES}
    active_console = set(CONSOLE_AREAS)
    active_tables = set(ANALYTICAL_TABLES) | {"allowance_intervals"}
    runtime_text = _runtime_text()
    package_text = "\n".join(
        (_ROOT / path).read_text(encoding="utf-8")
        for path in ("MANIFEST.in", "pyproject.toml")
    )
    for entry in entries:
        name = entry["public_name"]
        surface_type = entry["surface_type"]
        expected_replacement = _SURFACE_REPLACEMENTS[surface_type]
        if entry["replacement"] != expected_replacement:
            failures.append(
                f"{surface_type} {name}: replacement is not "
                f"{expected_replacement}"
            )
        proof = _ROOT / entry["absence_or_migration_test"]
        if not proof.is_file():
            failures.append(
                f"{surface_type} {name}: absence or migration proof is absent"
            )
        if surface_type in {"source_module", "frontend_asset"}:
            if (_ROOT / name).exists() or (_ROOT / name).is_symlink():
                failures.append(f"{surface_type} {name}: retired path remains")
        elif surface_type == "mcp_tool" and name in active_tools:
            failures.append(f"mcp_tool {name}: retired tool remains active")
        elif surface_type == "http_route" and name in active_routes:
            failures.append(f"http_route {name}: retired route remains active")
        elif surface_type == "schema_id" and name in runtime_text:
            failures.append(f"schema_id {name}: retired schema remains active")
        elif surface_type == "package_data_rule" and name in package_text:
            failures.append(
                f"package_data_rule {name}: retired package rule remains active"
            )
        elif surface_type == "cli_command" and name in _CLI_PATHS:
            if entry["replacement"] != "kernel operational CLI":
                failures.append(f"cli_command {name}: migration is undocumented")
        elif surface_type == "console_route" and name in active_console:
            if entry["replacement"] != "kernel timeline":
                failures.append(f"console_route {name}: migration is undocumented")
        elif (
            surface_type == "table"
            and name in active_tables
            and entry["replacement"] != "kernel database schema"
        ):
            failures.append(f"table {name}: migration is undocumented")
    return failures


def _runtime_import_failures() -> list[str]:
    failures: list[str] = []
    runtime = _ROOT / "src/codex_usage_tracker/kernel"
    for path in runtime.rglob("*.py"):
        relative_parts = set(path.relative_to(runtime).with_suffix("").parts)
        if not relative_parts.isdisjoint(_FORBIDDEN_MODULE_PARTS):
            failures.append(f"retired runtime module remains: {path.relative_to(_ROOT)}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for name in imported:
                if not set(name.split(".")).isdisjoint(_FORBIDDEN_MODULE_PARTS):
                    failures.append(
                        f"{path.relative_to(_ROOT)} imports retired owner {name}"
                    )
    return failures


def _runtime_text() -> str:
    runtime = _ROOT / "src/codex_usage_tracker/kernel"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in runtime.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".html", ".js", ".json", ".py"}
    )


def _distribution_budget_failures(budget: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    wheels = sorted((_ROOT / "dist").glob("*.whl"))
    sdists = sorted((_ROOT / "dist").glob("*.tar.gz"))
    for label, artifacts, key in (
        ("wheel", wheels, "wheel_bytes"),
        ("sdist", sdists, "sdist_bytes"),
    ):
        if len(artifacts) != 1:
            failures.append(f"expected exactly one release-candidate {label}")
            continue
        measured = artifacts[0].stat().st_size
        failures.extend(_measurement_failures(budget, {key: measured}))
    return failures


def _measurement_failures(
    budget: dict[str, Any],
    measurements: dict[str, int],
) -> list[str]:
    failures: list[str] = []
    headroom = budget.get("headroom_percent")
    if (
        isinstance(headroom, bool)
        or not isinstance(headroom, (int, float))
        or not 0 <= headroom <= 3
    ):
        return [f"invalid release-candidate headroom_percent {headroom}"]
    for name, measured in measurements.items():
        ceiling = budget.get(name)
        if not isinstance(ceiling, int):
            failures.append(f"{name} release-candidate ceiling is not an integer")
            continue
        if name not in _BYTE_BUDGETS:
            if ceiling != measured:
                failures.append(
                    f"{name} catalog ceiling {ceiling} must equal measured {measured}"
                )
            continue
        maximum = math.ceil(measured * (1 + headroom / 100))
        if measured > ceiling:
            failures.append(
                f"{name} measured {measured} exceeds release-candidate ceiling "
                f"{ceiling}"
            )
        elif ceiling > maximum:
            failures.append(
                f"{name} ceiling {ceiling} exceeds {headroom}% maximum {maximum}"
            )
    return failures


def _tree_bytes(root: Path) -> int:
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", action="store_true")
    args = parser.parse_args()
    failures = release_candidate_failures(dist=args.dist)
    if failures:
        print("\n".join(failures))
        return 1
    print("Kernel release-candidate absence and budgets passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
