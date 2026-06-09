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
DISTRIBUTION_NAME = "codex-usage-tracking"
DIST_FILE_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
CONSOLE_SCRIPT = "codex-usage-tracker"
SUPPORTED_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
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
    "docs/architecture.md",
    "docs/dashboard-guide.md",
    "docs/cli-json-schemas.md",
    "docs/one-dot-oh-readiness.md",
    "docs/assets/dashboard-insights.png",
    "docs/assets/dashboard-calls.png",
    "docs/assets/dashboard-threads.png",
    "docs/assets/dashboard-details.png",
    "scripts/check_release.py",
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
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_format.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "src/codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    "src/codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "src/codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "src/codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md",
    "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
]
WHEEL_REQUIRED_MEMBERS = {
    "codex_usage_tracker/plugin_data/assets/icon.svg",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.css",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_format.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_data.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_state.js",
    "codex_usage_tracker/plugin_data/dashboard/dashboard_template.html",
    "codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
    "codex_usage_tracker/plugin_data/rate_cards/codex-credit-rates.json",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-insights.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-calls.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png",
    "codex_usage_tracker/plugin_data/docs/assets/dashboard-details.png",
    "codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md",
    "codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md",
}
SDIST_REQUIRED_MEMBERS = {
    "docs/cli-json-schemas.md",
    "scripts/benchmark_synthetic_history.py",
    "skills/codex-usage-api/SKILL.md",
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
    failures.extend(_check_issue_templates())
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
        failures.append(".mcp.json should allow enough startup time for first-run runtime bootstrap")
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    if "recursive-include skills *.md *.py" not in manifest:
        failures.append("MANIFEST.in should include Codex skill scripts in the source distribution")
    failures.extend(_check_skill_packaging())
    launcher = (REPO_ROOT / "skills/codex-usage-tracker/scripts/run_mcp.py").read_text(
        encoding="utf-8"
    )
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
    if "importlib.metadata.version('codex-usage-tracking')" not in launcher:
        failures.append("MCP runtime launcher must check the codex-usage-tracking distribution")
    if "PACKAGE_SPEC_MARKER" not in launcher:
        failures.append("MCP runtime launcher should invalidate cached runtimes when package spec changes")
    failures.extend(_check_python_support_metadata(project))
    failures.extend(_check_ci_workflow())
    failures.extend(_check_publish_workflow())
    return failures


def _check_python_support_metadata(project: dict[str, object]) -> list[str]:
    failures: list[str] = []
    classifiers = set(project.get("classifiers", []))
    for version in SUPPORTED_PYTHON_VERSIONS:
        classifier = f"Programming Language :: Python :: {version}"
        if classifier not in classifiers:
            failures.append(f"pyproject.toml is missing Python classifier: {classifier}")

    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for version in SUPPORTED_PYTHON_VERSIONS:
        if f'"{version}"' not in ci_workflow:
            failures.append(f"CI workflow test matrix is missing Python {version}")

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    if "python-3.10--3.14" not in readme:
        failures.append("README.md Python badge should advertise Python 3.10-3.14")
    if "Python 3.10-3.14" not in readme:
        failures.append("README.md platform support should document Python 3.10-3.14")

    install_doc = (REPO_ROOT / "docs" / "install.md").read_text(encoding="utf-8")
    if "Python 3.10, 3.11, 3.12, 3.13, and 3.14" not in install_doc:
        failures.append("docs/install.md should document CI support through Python 3.14")

    smoke_script = (REPO_ROOT / "scripts" / "smoke_installed_package.py").read_text(
        encoding="utf-8"
    )
    if 'DEFAULT_DOCKER_IMAGE = "python:3.14-slim"' not in smoke_script:
        failures.append("installed-package Docker smoke default should use python:3.14-slim")
    return failures


def _check_publish_workflow() -> list[str]:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "publish.yml"
    if not workflow_path.exists():
        return ["missing publish workflow: .github/workflows/publish.yml"]
    workflow = workflow_path.read_text(encoding="utf-8")
    failures: list[str] = []
    for required in [
        "workflow_dispatch:",
        "release:",
        "pypa/gh-action-pypi-publish@release/v1",
        "id-token: write",
        "repository-url: https://test.pypi.org/legacy/",
        "python -m twine check dist/*",
        "if: github.event_name == 'workflow_dispatch' && inputs.target == 'testpypi'",
        "if: github.event_name == 'release' || (github.event_name == 'workflow_dispatch' && inputs.target == 'pypi')",
        "echo \"ref=$GITHUB_REF\"",
        "echo \"sha=$GITHUB_SHA\"",
        "refs/heads/main|refs/tags/*",
        "Manual PyPI publishing must run from main or a tag ref.",
        "name: testpypi",
        "name: pypi",
        "https://test.pypi.org/project/codex-usage-tracking/",
        "https://pypi.org/project/codex-usage-tracking/",
        "steps.package-version.outputs.exists != 'true'",
        "codex-usage-tracking {version} already exists on {index_name}; skipping upload.",
    ]:
        if required not in workflow:
            failures.append(f"publish workflow is missing required Trusted Publishing text: {required}")
    if re.search(r"(?m)^\s*push\s*:", workflow):
        failures.append("publish workflow must not publish on ordinary pushes")
    if re.search(r"(?m)^\s*pull_request\s*:", workflow):
        failures.append("publish workflow must not publish on pull requests")
    if "secrets." in workflow or "api-token" in workflow or "password:" in workflow:
        failures.append("publish workflow must not use token secrets or password-based publishing")
    for job_name in ["publish-testpypi", "publish-pypi"]:
        job_block = _workflow_job_block(workflow, job_name)
        if job_block is None:
            failures.append(f"publish workflow is missing job: {job_name}")
            continue
        for required in [
            "Verify PyPI publish ref",
            "echo \"event=$GITHUB_EVENT_NAME\"",
            "echo \"ref=$GITHUB_REF\"",
            "echo \"sha=$GITHUB_SHA\"",
            "refs/heads/main|refs/tags/*",
            "Manual PyPI publishing must run from main or a tag ref.",
            "Check target package version",
            "id: package-version",
            "PACKAGE_INDEX_JSON_URL",
            "PACKAGE_INDEX_NAME",
            "steps.package-version.outputs.exists != 'true'",
        ]:
            if required not in job_block:
                failures.append(f"publish workflow {job_name} job is missing preflight: {required}")
    return failures


def _workflow_job_block(workflow: str, job_name: str) -> str | None:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    if not match:
        return None
    return match.group("body")


def _check_ci_workflow() -> list[str]:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow_path.exists():
        return ["missing CI workflow: .github/workflows/ci.yml"]
    workflow = workflow_path.read_text(encoding="utf-8")
    failures: list[str] = []
    for required in [
        "name: Build package",
        "python -m build",
        "python -m twine check dist/*",
        "python scripts/check_release.py --dist",
    ]:
        if required not in workflow:
            failures.append(f"CI package job is missing required build check: {required}")
    return failures


def _check_ci_workflow() -> list[str]:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow_path.exists():
        return ["missing CI workflow: .github/workflows/ci.yml"]
    workflow = workflow_path.read_text(encoding="utf-8")
    failures: list[str] = []
    for required in [
        "name: Build package",
        "python -m build",
        "python -m twine check dist/*",
        "python scripts/check_release.py --dist",
    ]:
        if required not in workflow:
            failures.append(f"CI package job is missing required build check: {required}")
    return failures


def _check_skill_packaging() -> list[str]:
    failures: list[str] = []
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = set(pyproject["tool"]["setuptools"]["package-data"]["codex_usage_tracker.plugin_data"])
    for source_skill in sorted((REPO_ROOT / "skills").glob("*/SKILL.md")):
        skill_name = source_skill.parent.name
        package_skill = (
            REPO_ROOT
            / "src"
            / "codex_usage_tracker"
            / "plugin_data"
            / "skills"
            / skill_name
            / "SKILL.md"
        )
        if not package_skill.exists():
            failures.append(f"missing packaged Codex skill copy: {skill_name}")
            continue
        if source_skill.read_text(encoding="utf-8") != package_skill.read_text(encoding="utf-8"):
            failures.append(f"source-tree Codex skill must match packaged copy: {skill_name}")
        if f"skills/{skill_name}/*" not in package_data:
            failures.append(f"pyproject.toml package data is missing skill: {skill_name}")
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
