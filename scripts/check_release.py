#!/usr/bin/env python3
"""Release-safety checks for the qualified kernel package."""

from __future__ import annotations

import argparse
import json
import subprocess
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

try:
    from scripts.check_kernel_release_candidate import (
        release_candidate_failures,
    )
    from scripts.check_kernel_scope import (
        load_disposition_manifest,
        scope_failures,
    )
    from scripts.generate_kernel_manifests import manifest_failures
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from check_kernel_release_candidate import release_candidate_failures
    from check_kernel_scope import (
        load_disposition_manifest,
        scope_failures,
    )
    from generate_kernel_manifests import manifest_failures

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERSION = "0.26.0"
_PLUGIN_VERSION = "0.26.0"
_K1_MERGE = "d8da9bccdb6674e7dca4c0872c36a1346949dc13"
_FROZEN_RELEASE_PATHS = (
    "scripts/release_quality.py",
    "src/codex_usage_tracker/release/__init__.py",
    "src/codex_usage_tracker/release/artifact_normalization.py",
    "src/codex_usage_tracker/release/promotion_evidence.py",
    "src/codex_usage_tracker/release/tach.domain.toml",
    "tests/release/__init__.py",
    "tests/release/test_artifact_manifest.py",
    "tests/release/test_promotion_evidence.py",
    "tests/release/test_promotion_evidence_fail_closed.py",
)


def release_failures(*, dist: bool = False) -> list[str]:
    """Return deterministic integration metadata and package failures."""

    failures = manifest_failures()
    failures.extend(release_candidate_failures(dist=dist))
    failures.extend(_frozen_release_failures())
    manifest = load_disposition_manifest(
        _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
    )
    failures.extend(scope_failures(_REPO_ROOT, manifest))

    project = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    metadata = project["project"]
    if metadata["version"] != _VERSION:
        failures.append(f"release package version must be {_VERSION}")
    if metadata.get("dependencies") != []:
        failures.append("kernel release must have no runtime dependencies")
    if metadata.get("scripts") != {
        "codex-usage-tracker": (
            "codex_usage_tracker.kernel.interfaces.cli.main:main"
        )
    }:
        failures.append("kernel release must expose only its retained CLI")

    plugin = json.loads(
        (_REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if plugin.get("version") != _PLUGIN_VERSION:
        failures.append(f"release plugin version must be {_PLUGIN_VERSION}")
    if plugin.get("skills") != "./skills/":
        failures.append("integration plugin must declare its kernel skill")
    if plugin.get("mcpServers") != "./.mcp.json":
        failures.append("integration plugin must declare its MCP server")
    bundle = plugin.get("bundle")
    if (
        not isinstance(bundle, dict)
        or bundle.get("schema")
        != "codex-usage-tracker.kernel-plugin-bundle.v1"
        or bundle.get("runtime_version") != _VERSION
        or bundle.get("publishable") is not True
    ):
        failures.append("release plugin bundle identity is invalid")

    mcp = json.loads((_REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if not isinstance(servers, dict) or set(servers) != {"codex-usage-tracker"}:
        failures.append("integration MCP catalog must contain exactly one server")
    else:
        server = servers["codex-usage-tracker"]
        if (
            server.get("command") != "codex-usage-tracker"
            or server.get("args") != ["_mcp"]
            or "cwd" in server
        ):
            failures.append(
                "release MCP server must use the installed CLI interpreter"
            )

    workflow = (_REPO_ROOT / ".github/workflows/publish.yml").read_text(
        encoding="utf-8"
    )
    if "scripts/check_kernel_scope.py" not in workflow:
        failures.append("publish workflow is missing the kernel ref guard")

    if dist:
        failures.extend(_distribution_failures(_REPO_ROOT / "dist"))
    return failures


def _distribution_failures(dist_dir: Path) -> list[str]:
    failures: list[str] = []
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return ["expected exactly one integration wheel and one sdist"]

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = set(archive.namelist())
        wheel_metadata = archive.read(
            f"codex_usage_tracking-{_VERSION}.dist-info/METADATA"
        ).decode("utf-8")
    dist_info = f"codex_usage_tracking-{_VERSION}.dist-info"
    expected_wheel_names = {
        f"{dist_info}/licenses/LICENSE",
        f"{dist_info}/METADATA",
        f"{dist_info}/RECORD",
        f"{dist_info}/WHEEL",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/top_level.txt",
    }
    expected_wheel_names.update(
        path.relative_to(_REPO_ROOT / "src").as_posix()
        for root in (
            _REPO_ROOT / "src" / "codex_usage_tracker" / "kernel",
            _REPO_ROOT / "src" / "codex_usage_tracker" / "release",
        )
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".json", ".css", ".html", ".js"}
    )
    if wheel_names != expected_wheel_names:
        failures.append(
            "integration wheel member set differs from the exact kernel package"
        )
    failures.extend(
        _metadata_failures(
            wheel_metadata,
            artifact="wheel",
        )
    )

    with tarfile.open(sdists[0], "r:gz") as archive:
        files = {
            name
            for member in archive.getmembers()
            if member.isfile()
            for name in [member.name]
        }
        root = f"codex_usage_tracking-{_VERSION}/"
        sdist_names = {
            name.removeprefix(root)
            for name in files
            if name.startswith(root)
        }
        sdist_metadata = archive.extractfile(f"{root}PKG-INFO")
        if sdist_metadata is None:
            failures.append("integration sdist is missing PKG-INFO")
            metadata_text = ""
        else:
            metadata_text = sdist_metadata.read().decode("utf-8")
    expected_sdist_names = _expected_sdist_names()
    if sdist_names != expected_sdist_names:
        missing = sorted(expected_sdist_names - sdist_names)
        unexpected = sorted(sdist_names - expected_sdist_names)
        failures.append(
            "integration sdist member set differs from the exact kernel package: "
            f"missing={missing}, unexpected={unexpected}"
        )
    failures.extend(_metadata_failures(metadata_text, artifact="sdist"))
    return failures


def _expected_sdist_names() -> set[str]:
    names = {
        "AGENTS.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "MANIFEST.in",
        "PKG-INFO",
        "README.md",
        "SECURITY.md",
        "package-lock.json",
        "package.json",
        "playwright.config.mjs",
        "pyproject.toml",
        "setup.cfg",
        "src/codex_usage_tracking.egg-info/PKG-INFO",
        "src/codex_usage_tracking.egg-info/SOURCES.txt",
        "src/codex_usage_tracking.egg-info/dependency_links.txt",
        "src/codex_usage_tracking.egg-info/entry_points.txt",
        "src/codex_usage_tracking.egg-info/requires.txt",
        "src/codex_usage_tracking.egg-info/top_level.txt",
    }
    names.update(
        path.relative_to(_REPO_ROOT).as_posix()
        for root, patterns in (
            (_REPO_ROOT / "config", ("kernel-*.json",)),
            (_REPO_ROOT / "docs", ("**/*.md",)),
            (_REPO_ROOT / "scripts", (
                "benchmark_kernel.py",
                "check_kernel_maintainability.py",
                "check_kernel_release_candidate.py",
                "check_kernel_scope.py",
                "check_release.py",
                "generate_kernel_interfaces.py",
                "generate_kernel_manifests.py",
                "build_kernel_console.mjs",
                "check_kernel_console.mjs",
                "smoke_installed_console.py",
            )),
            (_REPO_ROOT / "frontend" / "kernel-console", ("*",)),
            (
                _REPO_ROOT / "src" / "codex_usage_tracker" / "kernel",
                ("**/*.py", "**/*.json", "**/*.css", "**/*.html", "**/*.js"),
            ),
            (_REPO_ROOT / "src" / "codex_usage_tracker" / "release", ("*.py",)),
            (_REPO_ROOT / "tests" / "kernel", ("**/*.py", "**/*.json", "**/*.jsonl")),
            (_REPO_ROOT / "tests" / "frontend", ("*.mjs",)),
            (_REPO_ROOT / "tests" / "e2e", ("*.mjs",)),
        )
        for pattern in patterns
        for path in root.glob(pattern)
        if path.is_file()
    )
    return names


def _metadata_failures(payload: str, *, artifact: str) -> list[str]:
    metadata = Parser().parsestr(payload)
    requirements = metadata.get_all("Requires-Dist", [])
    runtime = [
        requirement
        for requirement in requirements
        if 'extra == "dev"' not in requirement
        and "extra == 'dev'" not in requirement
    ]
    failures: list[str] = []
    if metadata.get("Version") != _VERSION:
        failures.append(f"{artifact} metadata version is not {_VERSION}")
    if runtime:
        failures.append(f"{artifact} metadata exposes runtime dependencies: {runtime}")
    return failures


def _frozen_release_failures() -> list[str]:
    failures: list[str] = []
    for path in _FROZEN_RELEASE_PATHS:
        expected = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "show", f"{_K1_MERGE}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
        current = _REPO_ROOT / path
        if not current.is_file() or current.read_bytes() != expected:
            failures.append(f"retained release primitive differs from merged K1: {path}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", action="store_true")
    args = parser.parse_args()
    failures = release_failures(dist=args.dist)
    if failures:
        print("\n".join(failures))
        return 1
    print("Kernel integration release-safety checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
