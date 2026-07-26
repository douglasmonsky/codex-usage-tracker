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
