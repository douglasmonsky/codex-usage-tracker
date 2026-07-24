"""Offline policy checks for build-once release artifact promotion."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def check_publish_workflow(repo_root: Path) -> list[str]:
    """Require one build whose exact bytes are promoted through every release target."""
    workflow_path = repo_root / ".github" / "workflows" / "publish.yml"
    if not workflow_path.exists():
        return ["missing publish workflow: .github/workflows/publish.yml"]
    workflow = workflow_path.read_text(encoding="utf-8")
    failures = _required_text_failures(workflow)
    failures.extend(_event_policy_failures(workflow))
    failures.extend(_promotion_job_failures(workflow))
    return failures


def check_release_artifact_contract(repo_root: Path, version: str) -> list[str]:
    """Reconstruct the release manifest payload from a built dist directory."""
    source_path = str(repo_root / "src")
    if source_path not in sys.path:
        sys.path.insert(0, source_path)
    from codex_usage_tracker.release.artifact_manifest import (
        ManifestError,
        inspect_artifacts,
    )

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ["release artifact contract could not resolve the source Git SHA"]
    try:
        inspect_artifacts(
            repo_root / "dist",
            expected_sha=result.stdout.strip(),
            expected_version=version,
            repository_root=repo_root,
        )
    except ManifestError as exc:
        return [f"release artifact contract failed: {exc}"]
    return []


def _required_text_failures(workflow: str) -> list[str]:
    required_text = [
        "workflow_dispatch:",
        "release:",
        "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247 # v1.14.1",
        "id-token: write",
        "repository-url: https://test.pypi.org/legacy/",
        "python -m twine check dist/*",
        "codex_usage_tracker.release.artifact_normalization",
        "name: Build one release artifact",
        "name: Pin reproducible build epoch",
        'SOURCE_DATE_EPOCH=$(git show -s --format=%ct "$GITHUB_SHA")',
        "name: Publish unchanged bytes to TestPyPI",
        "name: Qualify TestPyPI artifact",
        "name: Promote TestPyPI bytes to PyPI",
        "name: Attach verified PyPI bytes to GitHub Release",
        "name: Verify TestPyPI, PyPI, and GitHub Release hashes",
        "codex_usage_tracker.release.artifact_manifest create",
        "codex_usage_tracker.release.artifact_manifest verify",
        "codex_usage_tracker.release.promotion_evidence download-index",
        "codex_usage_tracker.release.promotion_evidence create",
        "codex_usage_tracker.release.promotion_evidence verify",
        "--artifact-dir qualified-dist",
        "manifest-sha256:",
        'expected_tag="v$version"',
        'if [ "$GITHUB_REF_NAME" != "$expected_tag" ]; then',
        "name: python-dist",
        "name: promotion-evidence",
        "packages-dir: release-bundle/dist/",
        "packages-dir: promoted-dist/",
        "gh release upload",
        "gh release download",
        "cmp release-bundle/release-manifest.json public-github/release-manifest.json",
        "name: testpypi",
        "name: pypi",
        "https://test.pypi.org/project/codex-usage-tracking/",
        "https://pypi.org/project/codex-usage-tracking/",
        "steps.package-version.outputs.exists != 'true'",
    ]
    return [
        f"publish workflow is missing artifact-promotion text: {required}"
        for required in required_text
        if required not in workflow
    ]


def _event_policy_failures(workflow: str) -> list[str]:
    failures: list[str] = []
    if re.search(r"(?m)^\s*push\s*:", workflow):
        failures.append("publish workflow must not publish on ordinary pushes")
    if re.search(r"(?m)^\s*pull_request\s*:", workflow):
        failures.append("publish workflow must not publish on pull requests")
    if "secrets." in workflow or "api-token" in workflow or "password:" in workflow:
        failures.append("publish workflow must not use token secrets or password-based publishing")
    if "inputs.target" in workflow:
        failures.append(
            "publish workflow must not allow an unqualified manual PyPI target; "
            "manual dispatch is TestPyPI-only"
        )
    if workflow.count("python -m build") != 1:
        failures.append("publish workflow must build distributions exactly once")
    if workflow.count("name: python-dist") != 6:
        failures.append(
            "publish workflow must upload python-dist once and download that named artifact "
            "in every verification stage"
        )
    return failures


def _promotion_job_failures(workflow: str) -> list[str]:
    job_names = [
        "build",
        "publish-testpypi",
        "qualify-testpypi",
        "publish-pypi",
        "attach-github-release",
        "verify-public-release",
    ]
    failures: list[str] = []
    positions = [workflow.find(f"\n  {job_name}:\n") for job_name in job_names]
    if -1 in positions or positions != sorted(positions):
        failures.append("publish workflow release jobs are missing or out of promotion order")
    for job_name in job_names:
        if _workflow_job_block(workflow, job_name) is None:
            failures.append(f"publish workflow is missing job: {job_name}")
    failures.extend(
        _missing_job_text(
            workflow,
            "build",
            "build-once proof",
            [
                "outputs:",
                "manifest-sha256:",
                "Build wheel and sdist once",
                "Upload the sole build artifact",
                "name: python-dist",
            ],
        )
    )
    failures.extend(
        _missing_job_text(
            workflow,
            "qualify-testpypi",
            "proof",
            [
                "needs: [build, publish-testpypi]",
                "download-index",
                "--output qualified-dist",
                "--artifact-dir qualified-dist",
                "promotion_evidence create",
                "installed-smoke passed",
            ],
        )
    )
    failures.extend(
        _missing_job_text(
            workflow,
            "publish-pypi",
            "promotion proof",
            [
                "needs: [build, qualify-testpypi]",
                "if: github.event_name == 'release'",
                "--output promoted-dist",
                "packages-dir: promoted-dist/",
            ],
        )
    )
    pypi = _workflow_job_block(workflow, "publish-pypi") or ""
    if "python -m build" in pypi:
        failures.append("publish workflow PyPI job must not rebuild distributions")
    return failures


def _missing_job_text(
    workflow: str,
    job_name: str,
    label: str,
    required_text: list[str],
) -> list[str]:
    job = _workflow_job_block(workflow, job_name) or ""
    return [
        f"publish workflow {job_name} job is missing {label}: {required}"
        for required in required_text
        if required not in job
    ]


def _workflow_job_block(workflow: str, job_name: str) -> str | None:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return None if match is None else match.group("body")
