from __future__ import annotations

import configparser
import json
from collections import Counter
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_dependency_and_dead_code_scans_use_reviewed_project_policy() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    deptry = config["tool"]["deptry"]
    assert deptry["known_first_party"] == ["codex_usage_tracker"]
    assert deptry["optional_dependencies_dev_groups"] == ["dev"]
    assert deptry["extend_exclude"] == ["scripts"]

    maintainer = config["tool"]["agent_maintainer"]
    assert "config/vulture-whitelist.py" in maintainer["vulture_paths"]
    assert maintainer["enable_pip_audit"] is True
    assert maintainer["pip_audit_args"] == ["-r", "requirements/audit.txt"]
    assert config["tool"]["vulture"]["min_confidence"] == 60


def test_runtime_audit_input_is_fully_pinned() -> None:
    requirements = (ROOT / "requirements" / "audit.txt").read_text(encoding="utf-8")
    requirement_lines = [
        line for line in requirements.splitlines() if line and not line.startswith((" ", "#"))
    ]

    assert any(line.startswith("mcp==") for line in requirement_lines)
    assert any(line.startswith("tiktoken==") for line in requirement_lines)
    assert all("==" in line for line in requirement_lines)


def test_workflow_security_policy_is_explicit() -> None:
    workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))
    workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)

    assert workflow_text.count("uses: actions/checkout@") == workflow_text.count(
        "persist-credentials: false"
    )
    assert all(
        "permissions:\n  contents: read" in path.read_text(encoding="utf-8") for path in workflows
    )

    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "github-actions"' in dependabot
    assert 'interval: "weekly"' in dependabot

    zizmor = (ROOT / "zizmor.yml").read_text(encoding="utf-8")
    assert "actions/*: ref-pin" in zizmor
    assert "pypa/*: ref-pin" in zizmor


def test_bandit_baseline_contains_only_reviewed_heuristics() -> None:
    bandit_config = configparser.ConfigParser()
    bandit_config.read(ROOT / ".bandit", encoding="utf-8")
    assert bandit_config["bandit"]["baseline"] == "config/bandit-baseline.json"

    baseline = json.loads((ROOT / "config" / "bandit-baseline.json").read_text(encoding="utf-8"))
    findings = baseline["results"]
    assert Counter(finding["test_id"] for finding in findings) == {
        "B105": 14,
        "B310": 1,
        "B404": 1,
        "B603": 1,
        "B608": 61,
    }
    assert all(finding["issue_severity"] in {"LOW", "MEDIUM"} for finding in findings)
