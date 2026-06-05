#!/usr/bin/env python3
"""Release-readiness checks for Codex Usage Tracker."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10.
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "OpenAI API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "Google API key": re.compile(r"\bAI" r"za[0-9A-Za-z_-]{20,}"),
}
REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "MANIFEST.in",
    "AGENTS.md",
    "docs/dashboard-guide.md",
    "docs/cli-json-schemas.md",
    "docs/assets/dashboard-insights.png",
    "docs/assets/dashboard-calls.png",
    "docs/assets/dashboard-threads.png",
    "docs/assets/dashboard-details.png",
    "scripts/check_release.py",
    ".github/workflows/ci.yml",
    ".github/workflows/pricing-compat.yml",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "skills/codex-usage-tracker/SKILL.md",
    "skills/codex-usage-tracker/scripts/run_mcp.py",
    "src/codex_usage_tracker/plugin_data/assets/icon.svg",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    "src/codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "src/codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
]
WHEEL_REQUIRED_MEMBERS = {
    "codex_usage_tracker/plugin_data/assets/icon.svg",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    "codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
}
SDIST_REQUIRED_MEMBERS = {
    "docs/cli-json-schemas.md",
    "skills/codex-usage-tracker/SKILL.md",
    "skills/codex-usage-tracker/scripts/run_mcp.py",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist",
        action="store_true",
        help="Require and inspect the built wheel in dist/.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    failures.extend(_check_required_files())
    failures.extend(_check_versions())
    failures.extend(_check_docs())
    failures.extend(_check_packaging_metadata())
    failures.extend(_check_tracked_files_for_secrets())
    if args.dist:
        failures.extend(_check_sdist())
        failures.extend(_check_wheel())

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Release readiness checks passed.")
    return 0


def _check_required_files() -> list[str]:
    failures: list[str] = []
    tracked_files = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in _tracked_files()
    }
    for path in REQUIRED_FILES:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing required file: {path}")
        elif path not in tracked_files:
            failures.append(f"required file is not tracked by git: {path}")
    return failures


def _check_versions() -> list[str]:
    failures: list[str] = []
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = pyproject["project"]["version"]
    init_text = (REPO_ROOT / "src/codex_usage_tracker/__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    manifest = json.loads((REPO_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    if not init_match:
        failures.append("src/codex_usage_tracker/__init__.py does not define __version__")
    elif init_match.group(1) != package_version:
        failures.append("__version__ does not match pyproject.toml project.version")
    if manifest.get("version") != package_version:
        failures.append(".codex-plugin/plugin.json version does not match pyproject.toml")
    if f"## {package_version}" not in changelog:
        failures.append("CHANGELOG.md does not contain an entry for the package version")
    return failures


def _check_docs() -> list[str]:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    failures: list[str] = []
    for required in [
        "pipx install",
        "codex-usage-tracker install-plugin",
        "codex-usage-tracker doctor",
        "Data Privacy",
        "not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI",
    ]:
        if required not in readme:
            failures.append(f"README.md is missing required install/privacy text: {required}")
    return failures


def _check_packaging_metadata() -> list[str]:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from codex_usage_tracker.plugin_installer import plugin_manifest

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    failures: list[str] = []
    manifest = json.loads((REPO_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if manifest != plugin_manifest():
        failures.append(".codex-plugin/plugin.json does not match plugin_installer.plugin_manifest()")
    if project.get("license") != "MIT":
        failures.append("pyproject.toml should use SPDX license = \"MIT\"")
    if "license-files" not in project:
        failures.append("pyproject.toml should include license-files")
    if "urls" not in project:
        failures.append("pyproject.toml should include project.urls")
    scripts = project.get("scripts", {})
    if scripts.get("codex-usage-tracker") != "codex_usage_tracker.cli:main":
        failures.append("pyproject.toml is missing the codex-usage-tracker console script")
    mcp_config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    mcp_server = mcp_config.get("mcpServers", {}).get("codex-usage-tracker", {})
    if mcp_server.get("command") != "python3":
        failures.append(".mcp.json should use the system python3 bootstrap launcher")
    if mcp_server.get("args") != ["./skills/codex-usage-tracker/scripts/run_mcp.py"]:
        failures.append(".mcp.json should point at the bundled MCP bootstrap launcher")
    if mcp_server.get("startup_timeout_sec") != 120:
        failures.append(".mcp.json should allow enough startup time for first-run runtime bootstrap")
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    if "recursive-include skills *.md *.py" not in manifest:
        failures.append("MANIFEST.in should include Codex skill scripts in the source distribution")
    source_skill = (REPO_ROOT / "skills/codex-usage-tracker/SKILL.md").read_text(
        encoding="utf-8"
    )
    package_skill = (
        REPO_ROOT / "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md"
    ).read_text(encoding="utf-8")
    if source_skill != package_skill:
        failures.append("source-tree Codex skill must match packaged plugin_data skill")
    launcher = (REPO_ROOT / "skills/codex-usage-tracker/scripts/run_mcp.py").read_text(
        encoding="utf-8"
    )
    if "codex-usage-tracker.git@main" in launcher:
        failures.append("MCP runtime launcher must pin the package spec instead of tracking main")
    package_spec = re.search(r"codex-usage-tracker\.git@([0-9a-f]{40})", launcher)
    if not package_spec:
        failures.append("MCP runtime launcher must pin a 40-character GitHub commit SHA")
    elif not _is_ancestor_when_available(package_spec.group(1), "HEAD"):
        failures.append("MCP runtime launcher package pin is not reachable from HEAD")
    if "PACKAGE_SPEC_MARKER" not in launcher:
        failures.append("MCP runtime launcher should invalidate cached runtimes when package spec changes")
    return failures


def _check_tracked_files_for_secrets() -> list[str]:
    failures: list[str] = []
    for path in _tracked_files():
        if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".sqlite", ".db"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"possible {label} in tracked file: {path.relative_to(REPO_ROOT)}")
    return failures


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def _is_ancestor_when_available(commit: str, ref: str) -> bool:
    exists = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if not exists:
        return True
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, ref],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _check_sdist() -> list[str]:
    sdists = sorted((REPO_ROOT / "dist").glob("codex_usage_tracker-*.tar.gz"))
    if not sdists:
        return ["dist/ does not contain a codex_usage_tracker source distribution"]
    with tarfile.open(sdists[-1]) as sdist:
        names = set(sdist.getnames())
    return [
        f"sdist is missing required member: {member}"
        for member in sorted(SDIST_REQUIRED_MEMBERS)
        if not any(name.endswith(f"/{member}") for name in names)
    ]


def _check_wheel() -> list[str]:
    wheels = sorted((REPO_ROOT / "dist").glob("codex_usage_tracker-*.whl"))
    if not wheels:
        return ["dist/ does not contain a codex_usage_tracker wheel"]
    with zipfile.ZipFile(wheels[-1]) as wheel:
        names = set(wheel.namelist())
    failures = [
        f"wheel is missing required member: {member}"
        for member in sorted(WHEEL_REQUIRED_MEMBERS)
        if member not in names
    ]
    failures.extend(
        f"wheel contains generated cache bytecode: {member}"
        for member in sorted(names)
        if "__pycache__" in member or member.endswith(".pyc")
    )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
