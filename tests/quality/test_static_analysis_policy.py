from __future__ import annotations

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
    assert config["tool"]["vulture"]["min_confidence"] == 60
