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

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from release_quality import (  # noqa: E402
    check_ci_workflow,
    check_compatibility_inventory,
    check_immutable_action_pins,
    check_publish_workflow,
    check_python_support_metadata,
    check_react_dashboard_privacy_artifacts,
    check_schema_inventory,
    check_skill_packaging,
    check_tracked_files_for_secrets,
    is_ancestor_when_available,
    tracked_files,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "codex-usage-tracking"
DIST_FILE_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
CONSOLE_SCRIPT = "codex-usage-tracker"
SUPPORTED_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]

SUPPORTED_SETUP_NODE_ACTIONS = (
    "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0",
)
OLD_PYPI_DISTRIBUTION_NAME = "codex-usage-tracker"
DASHBOARD_LOCALE_CODES = [
    "en",
    "vi",
    "es",
    "fr",
    "de",
    "pt",
    "ja",
    "zh-Hans",
    "ko",
    "ru",
    "it",
    "ar",
]
DASHBOARD_LOCALE_SOURCE_FILES = [
    f"src/codex_usage_tracker/plugin_data/dashboard/locales/{code}.json"
    for code in DASHBOARD_LOCALE_CODES
]
DASHBOARD_LOCALE_WHEEL_MEMBERS = {
    f"codex_usage_tracker/plugin_data/dashboard/locales/{code}.json"
    for code in DASHBOARD_LOCALE_CODES
}
PUBLIC_RELEASE_DOCS = [
    "docs/development.md",
]
PACKAGE_NAMING_DOCS = [
    "README.md",
    "docs/install.md",
    "docs/development.md",
]
PUBLIC_VERSION_PATTERNS = [
    re.compile(r"codex-usage-tracking==([0-9]+(?:\.[0-9]+){2})"),
    re.compile(r"--from-pypi --version ([0-9]+(?:\.[0-9]+){2})"),
    re.compile(r"visible as `([0-9]+(?:\.[0-9]+){2})`"),
]
SECRET_PATTERNS = {
    "OpenAI API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "Google API key": re.compile(r"\bAI" r"za[0-9A-Za-z_-]{20,}"),
}
REACT_DASHBOARD_PRIVACY_SCAN_ROOTS = [
    "frontend/dashboard/src",
    "src/codex_usage_tracker/plugin_data/dashboard/react",
    "docs/frontend-rewrite-roadmap.md",
    "docs/react-dashboard-0.14-release-roadmap.md",
]
REACT_DASHBOARD_PRIVACY_FILE_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ts",
    ".tsx",
}
REACT_DASHBOARD_PRIVACY_PATTERNS = {
    "raw context persisted in React dashboard artifact": re.compile(
        r"\braw_context_persisted\b[\"']?\s*[:=]\s*true",
        re.IGNORECASE,
    ),
    "raw context included in React dashboard artifact": re.compile(
        r"\braw_context_included\b[\"']?\s*[:=]\s*true",
        re.IGNORECASE,
    ),
    "local Codex session JSONL path in React dashboard artifact": re.compile(
        r"(?:^|[\"'\s])[^\"'\s]*\.codex/sessions/[^\"'\s]+\.jsonl",
    ),
    "patch transcript marker in React dashboard artifact": re.compile(r"\*\*\* Begin Patch"),
    "raw assistant message JSONL shape in React dashboard artifact": re.compile(
        r'"role"\s*:\s*"assistant"\s*,\s*"content"\s*:\s*\[',
    ),
    "raw user message JSONL shape in React dashboard artifact": re.compile(
        r'"role"\s*:\s*"user"\s*,\s*"content"\s*:\s*\[',
    ),
}
DASHBOARD_FORBIDDEN_DEPENDENCIES = {"three", "@types/three"}
DASHBOARD_REMOVED_VISUALIZATION_PATHS = (
    "frontend/dashboard/src/features/overview/usageConstellationModel.ts",
    "frontend/dashboard/src/features/overview/usageConstellationModel.test.ts",
    "frontend/dashboard/src/visualization/three",
    "tests/playwright/dashboard-constellation.spec.mjs",
)
DASHBOARD_THREE_IMPORT = re.compile(r"""(?:from\s+|import\s*\()\s*["']three(?:/|["'])""")
EVIDENCE_CONSOLE_SCREENSHOTS = (
    "evidence-console-home.png",
    "evidence-console-explore-calls.png",
    "evidence-console-explore-threads.png",
    "evidence-console-limits.png",
    "evidence-console-evidence-call.png",
    "evidence-console-settings.png",
    "evidence-console-legacy-reports.png",
    "evidence-console-home-tablet.png",
    "evidence-console-home-mobile.png",
    "evidence-console-home-zoom-200.png",
    "evidence-console-home-reduced-motion.png",
    "evidence-console-home-keyboard.png",
)
REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "MANIFEST.in",
    "AGENTS.md",
    "docs/architecture.md",
    "docs/release-checklist.md",
    "docs/dashboard-guide.md",
    "docs/cli-json-schemas.md",
    "docs/one-dot-oh-readiness.md",
    "docs/releases/0.22.0.md",
    "docs/upgrading-to-0.22.0.md",
    "docs/releases/0.23.0.md",
    "docs/upgrading-to-0.23.0.md",
    "docs/evidence-console-route-migration.md",
    "docs/assets/dashboard-insights.png",
    "docs/assets/dashboard-calls.png",
    "docs/assets/dashboard-calls-preview.png",
    "docs/assets/dashboard-threads.png",
    "docs/assets/dashboard-diagnostics.png",
    "docs/assets/dashboard-diagnostics-git-expanded.png",
    "docs/assets/dashboard-details.png",
    "docs/assets/dashboard-call-investigator.png",
    "docs/assets/dashboard-call-investigator-preview.png",
    "docs/assets/dashboard-call-investigator-evidence.png",
    *(f"docs/assets/{name}" for name in EVIDENCE_CONSOLE_SCREENSHOTS),
    "docs/assets/plugin-prompts.png",
    "docs/assets/plugin-thread-leaderboard.png",
    "scripts/check_release.py",
    "scripts/release_quality.py",
    "scripts/benchmark_synthetic_history.py",
    "scripts/smoke_installed_package.py",
    ".github/workflows/ci.yml",
    ".github/workflows/publish.yml",
    ".github/workflows/pricing-compat.yml",
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "skills/codex-usage-api/SKILL.md",
    "skills/codex-usage-tracker/SKILL.md",
    "skills/codex-usage-tracker/scripts/run_mcp.py",
    "src/codex_usage_tracker/plugin_data/assets/icon.svg",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_call.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_insights.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_layout.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_tables.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_detail.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_responsive.css",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_analysis.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_cells.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_details.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_insights.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_tables.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_filters.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_i18n.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_payload_cache.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_tooltips.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_status.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_events.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_diagnostics.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_call_diagnostics.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    *DASHBOARD_LOCALE_SOURCE_FILES,
    "src/codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "src/codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-calls-preview.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-diagnostics.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-diagnostics-git-expanded.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator-preview.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator-evidence.png",
    *(
        f"src/codex_usage_tracker/plugin_data/docs/assets/{name}"
        for name in EVIDENCE_CONSOLE_SCREENSHOTS
    ),
    "src/codex_usage_tracker/plugin_data/docs/assets/plugin-prompts.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/plugin-thread-leaderboard.png",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py",
]
WHEEL_REQUIRED_MEMBERS = {
    "codex_usage_tracker/plugin_data/assets/icon.svg",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_call.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_insights.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_layout.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_tables.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_detail.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_responsive.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_format.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_data.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_analysis.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_cells.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_details.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_insights.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_tables.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_filters.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_call_investigator.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_i18n.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_payload_cache.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_tooltips.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_status.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_events.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_diagnostics.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_call_diagnostics.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    *DASHBOARD_LOCALE_WHEEL_MEMBERS,
    "codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-calls-preview.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-diagnostics.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-diagnostics-git-expanded.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator-preview.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-call-investigator-evidence.png",
    *(
        f"codex_usage_tracker/plugin_data/docs/assets/{name}"
        for name in EVIDENCE_CONSOLE_SCREENSHOTS
    ),
    "codex_usage_tracker/plugin_data/docs/assets/plugin-prompts.png",
    "codex_usage_tracker/plugin_data/docs/assets/plugin-thread-leaderboard.png",
    "codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md",
    "codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
    "codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py",
}
SDIST_REQUIRED_MEMBERS = {
    "docs/cli-json-schemas.md",
    "docs/releases/0.22.0.md",
    "docs/upgrading-to-0.22.0.md",
    "docs/releases/0.23.0.md",
    "docs/upgrading-to-0.23.0.md",
    "docs/evidence-console-route-migration.md",
    "scripts/benchmark_synthetic_history.py",
    "skills/codex-usage-api/SKILL.md",
    "skills/codex-usage-tracker/SKILL.md",
    "skills/codex-usage-tracker/scripts/run_mcp.py",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist",
        action="store_true",
        help="Require and inspect the built wheel in dist/.",
    )
    parser.add_argument(
        "--dashboard-assets",
        action="store_true",
        help="Check only that generated React dashboard assets match Git.",
    )
    args = parser.parse_args()

    if args.dashboard_assets:
        failures = _check_dashboard_asset_sync()
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1
        print("Dashboard React assets are synchronized.")
        return 0

    failures: list[str] = []
    failures.extend(_check_required_files())
    failures.extend(_check_versions())
    failures.extend(_check_docs())
    failures.extend(_check_issue_templates())
    failures.extend(_check_packaging_metadata())
    failures.extend(_check_schema_inventory())
    failures.extend(_check_compatibility_inventory())
    failures.extend(_check_tracked_files_for_secrets())
    failures.extend(_check_react_dashboard_privacy_artifacts())
    failures.extend(_check_removed_dashboard_visualization())
    if args.dist:
        failures.extend(_check_sdist())
        failures.extend(_check_wheel())

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Release readiness checks passed.")
    return 0


def _check_dashboard_asset_sync() -> list[str]:
    relative_path = "src/codex_usage_tracker/plugin_data/dashboard/react"
    failures: list[str] = []
    tracked = subprocess.run(
        ["git", "diff", "--exit-code", "--", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        failures.append("dashboard React assets differ from the Git index after rebuild")

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if untracked.returncode != 0:
        failures.append("could not inspect untracked dashboard React assets")
    else:
        paths = sorted(path for path in untracked.stdout.splitlines() if path)
        if paths:
            failures.append(
                "dashboard React assets include untracked generated files: " + ", ".join(paths)
            )
    return failures


def _check_removed_dashboard_visualization() -> list[str]:
    failures: list[str] = []
    dashboard_package = json.loads(
        (REPO_ROOT / "frontend/dashboard/package.json").read_text(encoding="utf-8")
    )
    declared = set(dashboard_package.get("dependencies", {})) | set(
        dashboard_package.get("devDependencies", {})
    )
    for dependency in sorted(declared & DASHBOARD_FORBIDDEN_DEPENDENCIES):
        failures.append(f"removed dashboard dependency remains declared: {dependency}")

    lock_packages = json.loads((REPO_ROOT / "package-lock.json").read_text(encoding="utf-8"))[
        "packages"
    ]
    for package in sorted(lock_packages):
        dependency = package.removeprefix("node_modules/")
        if dependency in DASHBOARD_FORBIDDEN_DEPENDENCIES:
            failures.append(f"removed dashboard dependency remains locked: {dependency}")

    for relative_path in DASHBOARD_REMOVED_VISUALIZATION_PATHS:
        if (REPO_ROOT / relative_path).exists():
            failures.append(f"removed dashboard visualization path remains: {relative_path}")

    source_root = REPO_ROOT / "frontend/dashboard/src"
    for path in sorted((*source_root.rglob("*.ts"), *source_root.rglob("*.tsx"))):
        if DASHBOARD_THREE_IMPORT.search(path.read_text(encoding="utf-8")):
            failures.append(
                "removed Three.js import remains: " + path.relative_to(REPO_ROOT).as_posix()
            )

    assets_root = REPO_ROOT / "src/codex_usage_tracker/plugin_data/dashboard/react"
    for path in sorted(assets_root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in {".html", ".js"}
            and (
                "UsageConstellation" in path.name
                or "UsageConstellation" in path.read_text(encoding="utf-8")
            )
        ):
            failures.append(
                "removed constellation reference remains in packaged asset: "
                + path.relative_to(REPO_ROOT).as_posix()
            )
    return failures


def _check_required_files() -> list[str]:
    failures: list[str] = []
    tracked_files = {path.relative_to(REPO_ROOT).as_posix() for path in _tracked_files()}
    for path in REQUIRED_FILES:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing required file: {path}")
        elif path not in tracked_files:
            failures.append(f"required file is not tracked by git: {path}")
    return failures


def _tracked_files() -> list[Path]:
    return tracked_files(REPO_ROOT)


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
    failures.extend(_check_public_release_doc_versions(package_version))
    return failures


def _check_docs() -> list[str]:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    failures: list[str] = []
    for required in [
        "pipx install",
        "codex-usage-tracking",
        "codex-usage-tracker install-plugin",
        "codex-usage-tracker doctor",
        "Data Privacy",
        "not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI",
    ]:
        if required not in readme:
            failures.append(f"README.md is missing required install/privacy text: {required}")
    failures.extend(_check_package_naming_docs())
    return failures


def _check_public_release_doc_versions(package_version: str) -> list[str]:
    failures: list[str] = []
    for relative_path in PUBLIC_RELEASE_DOCS:
        path = REPO_ROOT / relative_path
        text = path.read_text(encoding="utf-8")
        for pattern in PUBLIC_VERSION_PATTERNS:
            for match in pattern.finditer(text):
                if match.group(1) != package_version:
                    failures.append(
                        f"{relative_path} public release version {match.group(1)} "
                        f"does not match pyproject.toml {package_version}"
                    )
    return failures


def _check_package_naming_docs() -> list[str]:
    failures: list[str] = []
    old_name_warning = f"The `{OLD_PYPI_DISTRIBUTION_NAME}` PyPI name is not this project"
    for relative_path in PACKAGE_NAMING_DOCS:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if DISTRIBUTION_NAME not in text:
            failures.append(
                f"{relative_path} must name the public PyPI package {DISTRIBUTION_NAME}"
            )
        if relative_path in {"README.md", "docs/install.md"} and old_name_warning not in text:
            failures.append(
                f"{relative_path} must warn that {OLD_PYPI_DISTRIBUTION_NAME} "
                "is a different PyPI package"
            )
        failures.extend(_check_doc_install_lines(relative_path, text))
    return failures


def _check_doc_install_lines(relative_path: str, text: str) -> list[str]:
    failures: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized = line.strip().strip("`")
        if not normalized:
            continue
        if not re.search(r"\b(?:pipx|pip|python(?:3)? -m pip)\s+install\b", normalized):
            continue
        if OLD_PYPI_DISTRIBUTION_NAME not in normalized:
            continue
        if DISTRIBUTION_NAME in normalized or "git+" in normalized or "github.com" in normalized:
            continue
        failures.append(
            f"{relative_path}:{line_number} installs {OLD_PYPI_DISTRIBUTION_NAME}; "
            f"use {DISTRIBUTION_NAME}"
        )
    return failures


def _check_issue_templates() -> list[str]:
    failures: list[str] = []
    templates = {
        "bug_report.yml": [
            "Do not paste real Codex logs",
            "strict support bundle",
            "--privacy-mode strict support-bundle",
        ],
        "parser_log_compatibility.yml": [
            "Do not attach or paste raw Codex JSONL logs",
            "Synthetic log shape",
        ],
        "pricing_or_allowance.yml": [
            "Do not paste account screenshots with private details",
            "--privacy-mode strict pricing-coverage --json",
        ],
    }
    for filename, required_texts in templates.items():
        path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / filename
        if not path.exists():
            failures.append(f"missing issue template: {path.relative_to(REPO_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for required in required_texts:
            if required not in text:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)} is missing safe-reporting text: {required}"
                )
    return failures


def _check_packaging_metadata() -> list[str]:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from codex_usage_tracker.cli.plugin_installer import plugin_manifest

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    failures: list[str] = []
    manifest = json.loads((REPO_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if manifest != plugin_manifest():
        failures.append(
            ".codex-plugin/plugin.json does not match plugin_installer.plugin_manifest()"
        )
    if project.get("license") != "MIT":
        failures.append('pyproject.toml should use SPDX license = "MIT"')
    if "license-files" not in project:
        failures.append("pyproject.toml should include license-files")
    if "urls" not in project:
        failures.append("pyproject.toml should include project.urls")
    if project.get("name") != DISTRIBUTION_NAME:
        failures.append(f"pyproject.toml project.name must be {DISTRIBUTION_NAME!r}")
    scripts = project.get("scripts", {})
    if scripts.get(CONSOLE_SCRIPT) != f"{IMPORT_PACKAGE}.cli:main":
        failures.append("pyproject.toml is missing the codex-usage-tracker console script")
    if "codex-usage-tracker" in project.get("name", ""):
        failures.append("pyproject.toml project.name must not use the old PyPI distribution name")
    mcp_config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    mcp_server = mcp_config.get("mcpServers", {}).get("codex-usage-tracker", {})
    if mcp_server.get("command") != "python3":
        failures.append(".mcp.json should use the system python3 bootstrap launcher")
    if mcp_server.get("args") != ["./skills/codex-usage-tracker/scripts/run_mcp.py"]:
        failures.append(".mcp.json should point at the bundled MCP bootstrap launcher")
    if mcp_server.get("startup_timeout_sec") != 120:
        failures.append(
            ".mcp.json should allow enough startup time for first-run runtime bootstrap"
        )
    if mcp_server.get("env") != {"CODEX_USAGE_TRACKER_MCP_PROFILE": "core"}:
        failures.append(".mcp.json should configure the core MCP profile")
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    if "recursive-include skills *.md *.py" not in manifest:
        failures.append("MANIFEST.in should include Codex skill scripts in the source distribution")
    failures.extend(_check_skill_packaging())
    launcher = (REPO_ROOT / "skills/codex-usage-tracker/scripts/run_mcp.py").read_text(
        encoding="utf-8"
    )
    packaged_launcher = REPO_ROOT / (
        "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py"
    )
    if launcher.encode() != packaged_launcher.read_bytes():
        failures.append("source and packaged MCP runtime launchers must be byte-identical")
    if "codex-usage-tracker.git@main" in launcher:
        failures.append("MCP runtime launcher must pin the package spec instead of tracking main")
    git_package_spec = re.search(r"codex-usage-tracker\.git@([0-9a-f]{40})", launcher)
    pypi_package_spec = re.search(r"codex-usage-tracking==([0-9]+(?:\.[0-9]+){2})", launcher)
    if pypi_package_spec:
        if pypi_package_spec.group(1) != str(project.get("version")):
            failures.append("MCP runtime launcher PyPI pin does not match project.version")
    elif git_package_spec:
        if not _is_ancestor_when_available(git_package_spec.group(1), "HEAD"):
            failures.append("MCP runtime launcher package pin is not reachable from HEAD")
    else:
        failures.append(
            "MCP runtime launcher must pin an exact codex-usage-tracking version or a "
            "40-character GitHub commit SHA"
        )
    runtime_version = re.search(r'^RUNTIME_VERSION = "([0-9]+(?:\.[0-9]+){2})"$', launcher, re.M)
    if runtime_version is None or runtime_version.group(1) != str(project.get("version")):
        failures.append("MCP runtime launcher cache version does not match project.version")
    if "importlib.metadata.version('codex-usage-tracking')" not in launcher:
        failures.append("MCP runtime launcher must check the codex-usage-tracking distribution")
    if "PACKAGE_SPEC_MARKER" not in launcher:
        failures.append(
            "MCP runtime launcher should invalidate cached runtimes when package spec changes"
        )
    failures.extend(_check_python_support_metadata(project))
    failures.extend(check_immutable_action_pins(REPO_ROOT))
    failures.extend(_check_ci_workflow())
    failures.extend(_check_publish_workflow())
    return failures


def _check_python_support_metadata(project: dict[str, object]) -> list[str]:
    return check_python_support_metadata(REPO_ROOT, project, SUPPORTED_PYTHON_VERSIONS)


def _check_publish_workflow() -> list[str]:
    return check_publish_workflow(REPO_ROOT)


def _check_ci_workflow() -> list[str]:
    return check_ci_workflow(REPO_ROOT, SUPPORTED_SETUP_NODE_ACTIONS)


def _check_schema_inventory() -> list[str]:
    return check_schema_inventory(REPO_ROOT, IMPORT_PACKAGE)


def _check_compatibility_inventory() -> list[str]:
    return check_compatibility_inventory(REPO_ROOT)


def _check_skill_packaging() -> list[str]:
    return check_skill_packaging(REPO_ROOT)


def _check_tracked_files_for_secrets() -> list[str]:
    return check_tracked_files_for_secrets(REPO_ROOT, SECRET_PATTERNS)


def _check_react_dashboard_privacy_artifacts() -> list[str]:
    return check_react_dashboard_privacy_artifacts(
        REPO_ROOT,
        REACT_DASHBOARD_PRIVACY_SCAN_ROOTS,
        REACT_DASHBOARD_PRIVACY_FILE_SUFFIXES,
        REACT_DASHBOARD_PRIVACY_PATTERNS,
    )


def _is_ancestor_when_available(commit: str, ref: str) -> bool:
    return is_ancestor_when_available(REPO_ROOT, commit, ref)


def _check_sdist() -> list[str]:
    version = _package_version()
    sdist_path = REPO_ROOT / "dist" / f"{DIST_FILE_STEM}-{version}.tar.gz"
    if not sdist_path.exists():
        return [f"dist/ does not contain expected source distribution: {sdist_path.name}"]
    with tarfile.open(sdist_path) as sdist:
        names = set(sdist.getnames())
    return [
        f"sdist is missing required member: {member}"
        for member in sorted(SDIST_REQUIRED_MEMBERS)
        if not any(name.endswith(f"/{member}") for name in names)
    ]


def _check_wheel() -> list[str]:
    version = _package_version()
    wheel_path = REPO_ROOT / "dist" / f"{DIST_FILE_STEM}-{version}-py3-none-any.whl"
    if not wheel_path.exists():
        return [f"dist/ does not contain expected wheel: {wheel_path.name}"]
    with zipfile.ZipFile(wheel_path) as wheel:
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


def _package_version() -> str:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


if __name__ == "__main__":
    raise SystemExit(main())
