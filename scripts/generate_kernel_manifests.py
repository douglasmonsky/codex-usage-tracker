#!/usr/bin/env python3
"""Generate the K1 retirement and full-tree disposition manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from argparse import _SubParsersAction
from pathlib import Path
from typing import Any

import tomllib

from codex_usage_tracker.interfaces.cli.parser import build_parser
from codex_usage_tracker.interfaces.mcp.registry import tool_specs
from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_DYNAMIC_ROUTE_METHODS,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
)
from codex_usage_tracker.store.schema import init_db

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RETIRED_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
_DISPOSITION_PATH = _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
_KERNEL_MCP_TOOLS = {
    "usage_status",
    "usage_refresh",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
}
_ALREADY_REMOVED_MCP_TOOLS = {"generate_usage_dashboard"}
_RETIRED_SOURCE_PREFIXES = (
    "src/codex_usage_tracker/analysis",
    "src/codex_usage_tracker/compression",
    "src/codex_usage_tracker/content",
    "src/codex_usage_tracker/diagnostic",
    "src/codex_usage_tracker/recommend",
    "src/codex_usage_tracker/usage_drain",
    "src/codex_usage_tracker/visualization",
)
_LEGACY_STORE_MARKERS = (
    "analysis_",
    "compression",
    "content_",
    "dashboard",
    "diagnostic",
    "home_",
    "investigation",
    "large_low_output",
    "recommendation",
    "repeated_files",
    "shell_churn",
)
_LEGACY_INTERFACE_MARKERS = (
    "compatibility",
    "compression",
    "dashboard",
    "dogfood",
    "investigation",
    "subagents",
    "visualization",
    "work_proof",
)
_LEGACY_APPLICATION_NAMES = {
    "analysis_protocols.py",
    "analyze.py",
    "context.py",
}
_HISTORICAL_MARKERS = (
    "/archive/",
    "/archive-",
    "docs/maintainability-roadmap.md",
    "docs/maintainability-scorecard.md",
    "docs/screenshots/",
    ".agent-maintainer/change-plans/archive/",
)
_KEEP_PREFIXES = (
    ".github/",
    ".agent-maintainer/change-plans/k1-oracle-baseline.md",
    "config/kernel-",
    "docs/roadmap/product-kernel-reset",
    "docs/superpowers/specs/2026-07-26-",
    "docs/superpowers/plans/2026-07-26-product-kernel-reset",
    "scripts/benchmark_kernel.py",
    "scripts/check_kernel_maintainability.py",
    "scripts/generate_kernel_manifests.py",
    "tests/kernel/",
)
_KEEP_EXACT = {
    ".gitignore",
    ".gitattributes",
    ".mcp.json",
    "AGENTS.md",
    "AGENTS.agent-maintainer.md",
    "CHANGELOG.md",
    "LICENSE",
    "MANIFEST.in",
    "README.md",
    "SECURITY.md",
    "justfile",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "tach.toml",
}


def build_retired_surface_manifest() -> dict[str, Any]:
    """Return the complete public/owned surface retirement inventory."""

    entries: list[dict[str, str]] = []
    for name in sorted(({spec.name for spec in tool_specs()} - _KERNEL_MCP_TOOLS) | _ALREADY_REMOVED_MCP_TOOLS):
        entries.append(_retired_entry("mcp_tool", name, "interfaces/mcp", "six-tool kernel MCP"))

    routes = {
        *(f"GET {path}" for path in GET_ROUTE_METHODS),
        *(f"GET {path}" for path in GET_DIAGNOSTIC_FACT_ROUTES),
        *(f"GET {path}" for path in GET_DYNAMIC_ROUTE_METHODS),
        *(f"POST {path}" for path in POST_ROUTE_METHODS),
    }
    for name in sorted(routes):
        entries.append(_retired_entry("http_route", name, "server/routes.py", "kernel HTTP API"))

    for name in _cli_command_paths():
        entries.append(_retired_entry("cli_command", name, "cli", "kernel operational CLI"))

    for name in sorted(_release_schema_ids()):
        entries.append(_retired_entry("schema_id", name, "release_catalog.py", "kernel fact schemas"))

    for name in _schema_tables():
        entries.append(_retired_entry("table", name, "store/schema.py", "kernel database schema"))

    for name in _console_routes():
        entries.append(_retired_entry("console_route", name, "frontend/dashboard", "kernel timeline"))

    for name in _frontend_assets():
        entries.append(
            _retired_entry("frontend_asset", name, "frontend/dashboard", "kernel timeline")
        )

    for name in _package_data_rules():
        entries.append(
            _retired_entry("package_data_rule", name, "pyproject.toml/MANIFEST.in", "lean kernel package")
        )

    for path in _git_lines("ls-files"):
        if (
            path.startswith("src/codex_usage_tracker/")
            and path.endswith(".py")
            and _classify_path(path)[0] == "retire"
        ):
            entries.append(_retired_entry("source_module", path, path, "none"))

    return {
        "schema": "codex-usage-tracker.kernel-retired-surfaces.v1",
        "source_ref": "v0.25.1",
        "replacement_release": "0.26.0",
        "entries": sorted(entries, key=lambda row: (row["surface_type"], row["public_name"])),
    }


def build_code_disposition_manifest() -> dict[str, Any]:
    """Classify every tracked path exactly once for the reset."""

    tracked = _git_lines("ls-files")
    tag_paths = set(_git_lines("ls-tree", "-r", "--name-only", "v0.25.1"))
    entries = [_disposition_entry(path, tag_paths=tag_paths) for path in tracked]
    return {
        "schema": "codex-usage-tracker.kernel-code-disposition.v1",
        "resolver": "git ls-files",
        "resolver_input_sha256": hashlib.sha256(
            ("\n".join(tracked) + "\n").encode("utf-8")
        ).hexdigest(),
        "source_ref": "62726189c05d423f08abdec6ad1454434188d734",
        "terminal_status": "verified",
        "state_machines": {
            "keep": ["classified", "verified"],
            "transplant": ["classified", "removed", "implemented", "verified"],
            "retire": ["classified", "removed", "verified"],
            "historical": ["classified", ["removed", "archived"], "verified"],
        },
        "entries": entries,
    }


def write_manifests(*, check: bool = False) -> bool:
    """Write or compare both manifests; return whether they already matched."""

    payloads = (
        (_RETIRED_PATH, build_retired_surface_manifest()),
        (_DISPOSITION_PATH, build_code_disposition_manifest()),
    )
    matched = True
    for path, payload in payloads:
        encoded = _compact_manifest(payload)
        if path.is_file() and path.read_text(encoding="utf-8") == encoded:
            continue
        matched = False
        if not check:
            path.write_text(encoded, encoding="utf-8")
    return matched


def _retired_entry(
    surface_type: str,
    public_name: str,
    current_owner: str,
    replacement: str,
) -> dict[str, str]:
    return {
        "surface_type": surface_type,
        "public_name": public_name,
        "current_owner": current_owner,
        "replacement": replacement,
        "final_supported_release": "0.25.x",
        "removal_release": "0.26.0",
        "absence_or_migration_test": "tests/kernel/test_retired_surface_manifest.py",
    }


def _schema_tables() -> list[str]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        names = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
    finally:
        conn.close()
    return names


def _cli_command_paths() -> list[str]:
    paths: set[str] = set()

    def walk(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> None:
        for action in parser._actions:
            if not isinstance(action, _SubParsersAction):
                continue
            for name, child in action.choices.items():
                command = (*prefix, name)
                paths.add(" ".join(command))
                walk(child, command)

    walk(build_parser())
    return sorted(paths)


def _console_routes() -> list[str]:
    route_files = (
        _REPO_ROOT / "frontend/dashboard/src/routes/evidenceConsoleRoutes.ts",
        _REPO_ROOT / "frontend/dashboard/src/app/routeCatalog.ts",
        _REPO_ROOT / "frontend/dashboard/src/routes/legacyRouteAliases.ts",
    )
    routes: set[str] = set()
    for path in route_files:
        source = path.read_text(encoding="utf-8")
        routes.update(re.findall(r"\bid:\s*'([^']+)'", source))
        routes.update(
            match.group(1) or match.group(2)
            for match in re.finditer(
                r"^\s*(?:'([^']+)'|([a-z][a-z0-9-]*)):\s*(?:\{|null)",
                source,
                flags=re.MULTILINE,
            )
        )
    routes.add("insights")
    return sorted(routes)


def _frontend_assets() -> list[str]:
    return sorted(
        path
        for path in _git_lines("ls-files")
        if path.startswith("frontend/dashboard/")
        or path.startswith("src/codex_usage_tracker/plugin_data/dashboard/")
    )


def _package_data_rules() -> list[str]:
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"]["package-data"]
    rules = {
        f"setuptools:{package}:{pattern}"
        for package, patterns in package_data.items()
        for pattern in patterns
    }
    rules.update(
        f"manifest:{line.strip()}"
        for line in (_REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return sorted(rules)


def _release_schema_ids() -> set[str]:
    source = (_REPO_ROOT / "tests" / "release_catalog.py").read_text(encoding="utf-8")
    return set(re.findall(r'"(codex-usage-tracker-[a-z0-9-]+-v[0-9]+)"', source))


def _disposition_entry(path: str, *, tag_paths: set[str]) -> dict[str, Any]:
    disposition, owner_task, reason, target = _classify_path(path)
    return {
        "path": path,
        "disposition": disposition,
        "reason": reason,
        "owner_task": owner_task,
        "source_ref": f"v0.25.1:{path}" if path in tag_paths else f"K1:{path}",
        "target_path": target,
        "public_surfaces": _public_surfaces(path),
        "required_oracle_tests": _required_tests(
            path,
            disposition=disposition,
            owner_task=owner_task,
        ),
        "removal_or_absence_test": _removal_test(path, disposition=disposition),
        "status": "classified",
    }


def _classify_path(path: str) -> tuple[str, str, str, str]:
    if any(marker in path for marker in _HISTORICAL_MARKERS):
        return ("historical", "K1A", "Archived planning or presentation evidence.", "")
    if path in _KEEP_EXACT or path.startswith(_KEEP_PREFIXES):
        owner = "K10" if path.startswith(".github/") or path in {
            "MANIFEST.in",
            "package.json",
            "package-lock.json",
            "pyproject.toml",
        } else "K1"
        return ("keep", owner, "Reset governance, release safety, or K1 oracle evidence.", path)
    if path.startswith(("src/codex_usage_tracker/release/", "tests/release/")):
        return ("keep", "K10", "Exact-byte release and promotion safety remains authoritative.", path)
    if path.startswith("scripts/") and any(
        marker in path for marker in ("release", "publish", "smoke_installed", "install_local_plugin")
    ):
        return ("keep", "K10", "Release, installation, or promotion safety remains authoritative.", path)
    if path.startswith(("src/codex_usage_tracker/pricing/", "tests/pricing/")):
        return ("transplant", "K8", "Pricing provenance and allowance costing must survive.", _kernel_target(path, "allowance"))
    if path == "src/codex_usage_tracker/plugin_installer.py":
        return ("transplant", "K6", "Plugin installation behavior must survive the adapter reset.", _kernel_target(path, "interfaces"))
    if path.startswith(_RETIRED_SOURCE_PREFIXES):
        return ("retire", "K1A", "Legacy analysis, content, diagnostic, or visualization subsystem.", "")
    if path.startswith(("frontend/", "src/codex_usage_tracker/plugin_data/dashboard/")):
        return ("retire", "K1A", "Legacy Evidence Console implementation or bundled asset.", "")
    if path.startswith("src/codex_usage_tracker/store/"):
        name = Path(path).name
        if any(marker in name for marker in _LEGACY_STORE_MARKERS):
            return ("retire", "K1A", "Legacy derived analysis or diagnostic persistence.", "")
        owner = _store_owner(name)
        return ("transplant", owner, "Bounded kernel persistence behavior must survive.", _kernel_target(path, "store"))
    if path.startswith(("src/codex_usage_tracker/parser/", "src/codex_usage_tracker/ingest/")):
        return ("transplant", "K3", "Incremental parser and source-cursor behavior must survive.", _kernel_target(path, "ingest"))
    if path.startswith("src/codex_usage_tracker/core/"):
        return ("transplant", "K2", "Accounting identity and normalized fact behavior must survive.", _kernel_target(path, "core"))
    if path.startswith("src/codex_usage_tracker/interfaces/"):
        name = Path(path).name
        if any(marker in name for marker in _LEGACY_INTERFACE_MARKERS):
            return ("retire", "K1A", "Legacy compatibility or automated-diagnosis interface.", "")
        return ("transplant", "K6", "Public adapter behavior must be rebuilt on the kernel.", _kernel_target(path, "interfaces"))
    if path.startswith("src/codex_usage_tracker/application/"):
        name = Path(path).name
        if name in _LEGACY_APPLICATION_NAMES:
            return ("retire", "K1A", "Legacy analysis or raw-context application orchestration.", "")
        owner = _application_owner(name)
        return ("transplant", owner, "Kernel use-case contract must survive without legacy orchestration.", _kernel_target(path, "application"))
    if path.startswith("tests/") and any(
        marker in path for marker in ("parser", "store", "query", "allowance", "dedup", "refresh")
    ):
        owner = _test_owner(path)
        return ("transplant", owner, "Behavioral coverage for a kernel candidate.", _kernel_target(path, "tests"))
    if path.startswith(("docs/", "skills/", ".agent-maintainer/")):
        return ("historical", "K1A", "Legacy documentation, skill, or implementation-plan evidence.", "")
    if path.startswith(("src/", "tests/", "scripts/", "config/")):
        return ("retire", "K1A", "Not selected for the minimal kernel contract.", "")
    return ("keep", "K10", "Repository governance or build metadata remains release-owned.", path)


def _store_owner(name: str) -> str:
    if "allowance" in name or "service_tier" in name:
        return "K8"
    if any(marker in name for marker in ("query", "summary", "export", "timing")):
        return "K4"
    if any(marker in name for marker in ("source", "refresh")):
        return "K3"
    return "K2"


def _application_owner(name: str) -> str:
    if "allowance" in name:
        return "K8"
    if name in {"evidence.py"}:
        return "K5"
    if name in {"query.py", "query_models.py", "query_validation.py"}:
        return "K4"
    if "refresh" in name or name in {"status.py", "job_status.py"}:
        return "K3"
    return "K6"


def _test_owner(path: str) -> str:
    if "allowance" in path:
        return "K8"
    if "query" in path:
        return "K4"
    if any(marker in path for marker in ("parser", "refresh", "source")):
        return "K3"
    return "K2"


def _kernel_target(path: str, domain: str) -> str:
    name = Path(path).name
    if path.startswith("tests/"):
        return f"tests/kernel/{domain}/{name}"
    return f"src/codex_usage_tracker/kernel/{domain}/{name}"


def _required_tests(
    path: str,
    *,
    disposition: str,
    owner_task: str,
) -> list[str]:
    if disposition == "historical":
        return ["tests/kernel/test_code_disposition_manifest.py"]
    if owner_task == "K10":
        return ["tests/release/test_artifact_manifest.py"]
    if owner_task == "K8":
        return ["tests/kernel/test_oracle_equivalence.py"]
    if owner_task == "K6":
        return ["tests/kernel/test_retired_surface_manifest.py"]
    if owner_task == "K5":
        return ["tests/kernel/test_oracle_equivalence.py"]
    if owner_task == "K4":
        return ["tests/kernel/test_oracle_equivalence.py"]
    if owner_task == "K3":
        return ["tests/kernel/test_source_lifecycle_oracle.py"]
    if owner_task == "K2":
        return ["tests/kernel/test_oracle_equivalence.py"]
    if path in {"AGENTS.md", "AGENTS.agent-maintainer.md", "justfile"}:
        return ["tests/kernel/test_repository_quality_policy.py"]
    return ["tests/kernel/test_code_disposition_manifest.py"]


def _removal_test(path: str, *, disposition: str) -> str:
    if disposition == "retire" and _public_surfaces(path):
        return "tests/kernel/test_retired_surface_manifest.py"
    return "tests/kernel/test_code_disposition_manifest.py"


def _public_surfaces(path: str) -> list[str]:
    surfaces = []
    if "interfaces/mcp" in path:
        surfaces.append("mcp")
    if "server" in path:
        surfaces.append("http")
    if "/cli" in path:
        surfaces.append("cli")
    if path.startswith("frontend/") or "plugin_data/dashboard" in path:
        surfaces.append("console")
    if path in {"pyproject.toml", "MANIFEST.in"} or "plugin_data" in path:
        surfaces.append("package")
    return surfaces


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _compact_manifest(payload: dict[str, Any]) -> str:
    entries = payload["entries"]
    header = {key: value for key, value in payload.items() if key != "entries"}
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True)},")
    lines.append('  "entries": [')
    for index, entry in enumerate(entries):
        suffix = "," if index + 1 < len(entries) else ""
        lines.append(f"    {json.dumps(entry, sort_keys=True, separators=(',', ':'))}{suffix}")
    lines.extend(["  ]", "}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    matched = write_manifests(check=args.check)
    if args.check and not matched:
        print("kernel manifests differ from deterministic generator", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
