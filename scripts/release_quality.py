"""Focused quality, inventory, and workflow checks for release readiness."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from re import Pattern

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10.
    import tomli as tomllib


def check_python_support_metadata(
    repo_root: Path,
    project: dict[str, object],
    supported_versions: list[str],
) -> list[str]:
    failures: list[str] = []
    classifiers = set(project.get("classifiers", []))
    for version in supported_versions:
        classifier = f"Programming Language :: Python :: {version}"
        if classifier not in classifiers:
            failures.append(f"pyproject.toml is missing Python classifier: {classifier}")

    ci_workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for version in supported_versions:
        if f'"{version}"' not in ci_workflow:
            failures.append(f"CI workflow test matrix is missing Python {version}")

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    if "python-3.10--3.14" not in readme:
        failures.append("README.md Python badge should advertise Python 3.10-3.14")
    if "Python 3.10-3.14" not in readme:
        failures.append("README.md platform support should document Python 3.10-3.14")

    install_doc = (repo_root / "docs" / "install.md").read_text(encoding="utf-8")
    if "Python 3.10, 3.11, 3.12, 3.13, and 3.14" not in install_doc:
        failures.append("docs/install.md should document CI support through Python 3.14")

    smoke_script = (repo_root / "scripts" / "smoke_installed_package.py").read_text(
        encoding="utf-8"
    )
    if 'DEFAULT_DOCKER_IMAGE = "python:3.14-slim"' not in smoke_script:
        failures.append("installed-package Docker smoke default should use python:3.14-slim")
    return failures


def check_publish_workflow(repo_root: Path) -> list[str]:
    workflow_path = repo_root / ".github" / "workflows" / "publish.yml"
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
        'echo "ref=$GITHUB_REF"',
        'echo "sha=$GITHUB_SHA"',
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
            failures.append(
                f"publish workflow is missing required Trusted Publishing text: {required}"
            )
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
            'echo "event=$GITHUB_EVENT_NAME"',
            'echo "ref=$GITHUB_REF"',
            'echo "sha=$GITHUB_SHA"',
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


def check_ci_workflow(
    repo_root: Path,
    supported_setup_node_actions: tuple[str, ...],
) -> list[str]:
    workflow_path = repo_root / ".github" / "workflows" / "ci.yml"
    if not workflow_path.exists():
        return ["missing CI workflow: .github/workflows/ci.yml"]
    workflow = workflow_path.read_text(encoding="utf-8")
    package_job = _workflow_job_block(workflow, "package")
    if package_job is None:
        return ["CI workflow is missing package job"]
    required_in_order: list[str | tuple[str, ...]] = [
        "name: Build package",
        supported_setup_node_actions,
        'node-version: "22"',
        "run: npm ci",
        "run: npm run dashboard:assets:check",
        "run: python -m build",
        "run: python -m twine check dist/*",
        "run: python scripts/check_release.py --dist",
        "run: python scripts/smoke_installed_package.py",
    ]
    failures: list[str] = []
    positions: list[int] = []
    for required in required_in_order:
        alternatives = (required,) if isinstance(required, str) else required
        matched = next(
            (candidate for candidate in alternatives if candidate in package_job),
            None,
        )
        if matched is None:
            label = required if isinstance(required, str) else "one of " + ", ".join(required)
            failures.append(f"CI package job is missing required build check: {label}")
        else:
            positions.append(package_job.find(matched))
    if len(positions) == len(required_in_order) and positions != sorted(positions):
        failures.append(
            "CI package job must build React assets before Python distributions and smoke the installed wheel last"
        )

    package = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
    expected_asset_check = (
        "npm run dashboard:build && python3 scripts/check_release.py --dashboard-assets"
    )
    if package.get("scripts", {}).get("dashboard:assets:check") != expected_asset_check:
        failures.append("package.json must define deterministic dashboard:assets:check")
    test_job = _workflow_job_block(workflow, "test")
    if test_job is None:
        failures.append("CI workflow is missing test job")
    else:
        for required in [
            "fetch-depth: 0",
            "--cov-report=xml",
        ]:
            if required not in test_job:
                failures.append(f"CI test job is missing blocking coverage check: {required}")
        coverage_step = _workflow_step_block(test_job, "Changed-line coverage")
        if coverage_step is None:
            failures.append("CI test job is missing named Changed-line coverage step")
        else:
            for required in [
                "if: matrix.python-version == '3.14' && github.event_name == 'pull_request'",
                "BASE_REF: ${{ github.base_ref }}",
                'run: diff-cover coverage.xml --compare-branch="origin/$BASE_REF" --fail-under=90',
            ]:
                if required not in coverage_step:
                    failures.append(
                        f"CI changed-line coverage step is not blocking as required: {required}"
                    )
            if "continue-on-error:" in coverage_step:
                failures.append("CI changed-line coverage step must not use continue-on-error")

    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    coverage = pyproject.get("tool", {}).get("coverage", {}).get("report", {})
    maintainer = pyproject.get("tool", {}).get("agent_maintainer", {})
    if coverage.get("fail_under") != 85:
        failures.append("coverage.report.fail_under must be 85")
    if maintainer.get("coverage_fail_under") != 85:
        failures.append("agent_maintainer.coverage_fail_under must be 85")
    if maintainer.get("diff_cover_fail_under") != 90:
        failures.append("agent_maintainer.diff_cover_fail_under must be 90")
    return failures


def check_schema_inventory(repo_root: Path, import_package: str) -> list[str]:
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "src"))
    from codex_usage_tracker.core.json_contracts import known_json_schemas
    from tests.release_catalog import RELEASE_SCHEMA_IDS

    runtime = set(known_json_schemas())
    failures: list[str] = []
    if runtime != RELEASE_SCHEMA_IDS:
        missing = sorted(runtime - RELEASE_SCHEMA_IDS)
        orphaned = sorted(RELEASE_SCHEMA_IDS - runtime)
        failures.append(
            f"schema release inventory mismatch; missing={missing}, orphaned={orphaned}"
        )

    pattern = re.compile(r"codex-usage-tracker(?:-[a-z0-9-]+-v[0-9]+|\.[a-z0-9-]+\.v[0-9]+)")
    emitted: set[str] = set()
    runtime_roots = (
        repo_root / "src" / import_package,
        repo_root / "frontend" / "dashboard" / "src",
    )
    for root in runtime_roots:
        for path in root.rglob("*"):
            if path.suffix in {".js", ".json", ".py", ".ts", ".tsx"}:
                emitted.update(pattern.findall(path.read_text(encoding="utf-8")))
    undocumented_runtime = sorted(emitted - runtime)
    if undocumented_runtime:
        failures.append(f"emitted schemas missing from runtime registry: {undocumented_runtime}")

    documentation = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in ("docs/contracts.md", "docs/cli-json-schemas.md")
    )
    undocumented_release = sorted(RELEASE_SCHEMA_IDS - set(pattern.findall(documentation)))
    if undocumented_release:
        failures.append(f"release schemas missing from documentation: {undocumented_release}")
    return failures


def check_compatibility_inventory(repo_root: Path) -> list[str]:
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "src"))
    from codex_usage_tracker.interfaces.mcp.registry import tool_specs
    from tests.release_catalog import DEPRECATED_MCP_TOOL_NAMES

    runtime = {spec.name for spec in tool_specs() if spec.lifecycle == "deprecated"}
    failures: list[str] = []
    if runtime != DEPRECATED_MCP_TOOL_NAMES:
        missing = sorted(runtime - DEPRECATED_MCP_TOOL_NAMES)
        orphaned = sorted(DEPRECATED_MCP_TOOL_NAMES - runtime)
        failures.append(
            f"deprecated MCP inventory mismatch; missing={missing}, orphaned={orphaned}"
        )

    ledger = (repo_root / "docs" / "deprecations.md").read_text(encoding="utf-8")
    undocumented = sorted(name for name in runtime if f"`{name}`" not in ledger)
    if undocumented:
        failures.append(f"deprecated MCP tools missing from docs/deprecations.md: {undocumented}")
    return failures


def check_skill_packaging(repo_root: Path) -> list[str]:
    failures: list[str] = []
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = set(
        pyproject["tool"]["setuptools"]["package-data"]["codex_usage_tracker.plugin_data"]
    )
    if "dashboard/locales/*" not in package_data:
        failures.append("pyproject.toml package data is missing dashboard locale catalogs")
    for source_skill in sorted((repo_root / "skills").glob("*/SKILL.md")):
        skill_name = source_skill.parent.name
        package_skill = (
            repo_root
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


def check_tracked_files_for_secrets(
    repo_root: Path,
    patterns: dict[str, Pattern[str]],
) -> list[str]:
    failures: list[str] = []
    for path in tracked_files(repo_root):
        if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".sqlite", ".db"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                failures.append(f"possible {label} in tracked file: {path.relative_to(repo_root)}")
    return failures


def check_react_dashboard_privacy_artifacts(
    repo_root: Path,
    roots: list[str],
    suffixes: set[str],
    patterns: dict[str, Pattern[str]],
) -> list[str]:
    failures: list[str] = []
    for path in _react_dashboard_privacy_scan_files(repo_root, roots, suffixes):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                failures.append(f"possible {label}: {path.relative_to(repo_root)}")
    return failures


def is_ancestor_when_available(repo_root: Path, commit: str, ref: str) -> bool:
    exists = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
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
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _workflow_job_block(workflow: str, job_name: str) -> str | None:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return None if match is None else match.group("body")


def _workflow_step_block(job: str, step_name: str) -> str | None:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(step_name)}\n"
        rf"(?P<body>.*?)(?=^      - |\Z)",
        job,
    )
    return None if match is None else match.group("body")


def tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repo_root / line for line in result.stdout.splitlines() if line]


def _react_dashboard_privacy_scan_files(
    repo_root: Path,
    roots: list[str],
    suffixes: set[str],
) -> list[Path]:
    files: list[Path] = []
    for relative_root in roots:
        root = repo_root / relative_root
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [path for path in root.rglob("*") if path.is_file()]
        else:
            continue
        files.extend(
            path
            for path in candidates
            if path.suffix in suffixes
            and "__pycache__" not in path.parts
            and "node_modules" not in path.parts
        )
    return sorted(set(files))
