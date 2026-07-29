from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_wemake_is_not_a_repository_or_ci_gate() -> None:
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = config["project"]["optional-dependencies"]["dev"]

    assert not any("wemake" in dependency.lower() for dependency in dev_dependencies)
    assert "agent_maintainer" not in config["tool"]
    assert not (_REPO_ROOT / "scripts" / "check_wemake_baseline.py").exists()

    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((_REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    ).lower()
    assert "wemake" not in workflows
    assert "check_wemake_baseline" not in workflows


def test_maintainability_policy_has_one_non_stylistic_guardrail_per_concern() -> None:
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = config["project"]["optional-dependencies"]["dev"]

    assert not any("git-agent-ratchet" in dependency for dependency in dev_dependencies)
    assert any(dependency.startswith("xenon") for dependency in dev_dependencies)
    maintainability = (
        _REPO_ROOT / "scripts" / "check_kernel_maintainability.py"
    ).read_text(encoding="utf-8")
    assert "max_physical" not in maintainability
    assert "max_source" not in maintainability
    assert maintainability.count('"C"') == 1
    assert maintainability.count('"B"') == 2
    for name in (
        "git-agent-ratchet-duplicate-helpers.json",
        "git-agent-ratchet-max-file-lines.json",
        "git-agent-ratchet-private-imports.json",
    ):
        assert not (_REPO_ROOT / ".agent-maintainer" / name).exists()


def test_repository_verification_wrappers_do_not_use_generic_maintainer_profiles() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")

    assert "agent_maintainer verify" not in justfile
    for command in (
        "scripts/check_kernel_scope.py",
        "scripts/generate_kernel_manifests.py --check",
        "-m ruff check",
        "-m mypy",
        "-m pytest",
        "-m pyright",
        "scripts/check_release.py",
        "scripts/check_kernel_maintainability.py",
    ):
        assert command in justfile

    for retired_command in (
        "dashboard:",
        "check_product_complexity.py",
        "agent_maintainer verify",
        "-m tach check",
    ):
        assert retired_command not in justfile


def test_ci_runs_performance_contracts_only_in_the_dedicated_step() -> None:
    workflow = (
        _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "tests/kernel/test_ingest_*.py" not in workflow
    for path in (
        "tests/kernel/test_ingest_performance.py",
        "tests/kernel/allowance/test_performance.py",
        "tests/kernel/evidence/test_performance.py",
        "tests/kernel/interfaces/test_performance.py",
        "tests/kernel/query/test_performance.py",
    ):
        assert workflow.count(path) == 2
        assert f"--ignore={path}" in workflow
    assert 'if [ "$MATRIX_PYTHON" = "3.14" ]; then' not in workflow
    assert "CODEX_USAGE_PERFORMANCE_LANE: github_hosted_qualified" in workflow
    assert "CODEX_USAGE_PERFORMANCE_REPORT: performance-qualification.json" in workflow
    assert "-p tests.kernel.performance_qualification" in workflow
    assert "continue-on-error:" not in workflow
    assert "Summarize performance qualification" in workflow
    assert "Upload performance qualification telemetry" in workflow


def test_hosted_performance_workflow_is_truthfully_qualified_not_controlled() -> None:
    workflow = (
        _REPO_ROOT / ".github" / "workflows" / "performance-qualification.yml"
    ).read_text(encoding="utf-8")
    qualification = (
        _REPO_ROOT / "docs" / "quality" / "CI_PERFORMANCE_QUALIFICATION.md"
    ).read_text(encoding="utf-8")

    assert "name: Qualified hosted performance" in workflow
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "CODEX_USAGE_PERFORMANCE_LANE: github_hosted_qualified" in workflow
    assert "-p tests.kernel.performance_qualification" in workflow
    assert "continue-on-error:" not in workflow
    assert "self-hosted" not in workflow
    assert "controlled" not in workflow.lower()
    assert "CODEX_USAGE_PERFORMANCE_LANE=strict" in qualification
    assert "Strict mode has no runner escape" in qualification
