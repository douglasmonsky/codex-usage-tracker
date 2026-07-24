from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release_quality import check_ci_workflow

_COVERAGE_STEP = """      - name: Changed-line coverage
        if: matrix.python-version == '3.14' && github.event_name == 'pull_request'
        env:
          BASE_REF: ${{ github.base_ref }}
        run: diff-cover coverage.xml --compare-branch="origin/$BASE_REF" --fail-under=90
"""
_SETUP_NODE_PIN = (
    "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0"
)


def _write_release_fixture(tmp_path: Path, coverage_step: str = _COVERAGE_STEP) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        f"""name: CI

jobs:
  package:
    name: Build package
    steps:
      - uses: {_SETUP_NODE_PIN}
        with:
          node-version: "22"
      - run: npm ci
      - run: npm run dashboard:assets:check
      - run: python -m build
      - run: python -m twine check dist/*
      - run: python scripts/check_release.py --dist
      - run: python scripts/smoke_installed_package.py
  test:
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: python -m pytest --cov-report=xml
{coverage_step}""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dashboard:assets:check": (
                        "npm run dashboard:build && python3 "
                        "scripts/check_release.py --dashboard-assets"
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.coverage.report]
fail_under = 85

[tool.agent_maintainer]
coverage_fail_under = 85
diff_cover_fail_under = 90
""",
        encoding="utf-8",
    )


def test_release_check_accepts_blocking_coverage_and_setup_node_v7(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path)

    assert check_ci_workflow(tmp_path, (_SETUP_NODE_PIN,)) == []


@pytest.mark.parametrize(
    "coverage_step",
    [
        _COVERAGE_STEP.replace(
            "        env:\n",
            "        continue-on-error: true\n        env:\n",
        ),
        _COVERAGE_STEP.replace(
            "if: matrix.python-version == '3.14' && github.event_name == 'pull_request'",
            "if: false",
        ),
    ],
    ids=["continue-on-error", "disabled-condition"],
)
def test_release_check_rejects_non_blocking_changed_coverage(
    tmp_path: Path,
    coverage_step: str,
) -> None:
    _write_release_fixture(tmp_path, coverage_step)

    failures = check_ci_workflow(tmp_path, (_SETUP_NODE_PIN,))

    assert any("coverage step" in failure for failure in failures)
