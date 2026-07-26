from __future__ import annotations

from pathlib import Path

import tomllib

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_wemake_is_not_a_repository_or_ci_gate() -> None:
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = config["project"]["optional-dependencies"]["dev"]
    agent_maintainer = config["tool"]["agent_maintainer"]

    assert not any("wemake" in dependency.lower() for dependency in dev_dependencies)
    assert agent_maintainer["enable_wemake"] is False
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
    policy = config["tool"]["agent_maintainer"]

    assert not any("git-agent-ratchet" in dependency for dependency in dev_dependencies)
    assert policy["file_length_max_physical"] == 600
    assert policy["file_length_max_source"] == 600
    assert policy["change_block_lines"] == 5_000
    assert policy["change_block_files"] == 100
    assert policy["xenon_max_absolute"] == "B"
    assert policy["xenon_max_modules"] == "B"
    assert policy["xenon_max_average"] == "B"
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
        "ruff check .",
        "-m mypy",
        "-m pytest",
        "-m pyright",
        "-m tach check",
        "scripts/check_release.py",
        "scripts/check_product_complexity.py",
        "scripts/check_kernel_maintainability.py",
        "dashboard:verify",
    ):
        assert command in justfile

    assert justfile.count("dashboard:verify") == 1
    assert "npm run dashboard:governance" not in justfile
