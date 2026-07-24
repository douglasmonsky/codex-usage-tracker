from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_quality import (
    REVIEWED_PYTHON_SMOKE_IMAGE,
    check_immutable_action_pins,
    check_installed_smoke_docker_image,
)

ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"


def _write_workflow(tmp_path: Path, uses_line: str) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        f"""name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - {uses_line}
""",
        encoding="utf-8",
    )


def test_accepts_reviewed_full_sha_and_local_action(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        f"uses: actions/checkout@{CHECKOUT_SHA} # v7.0.1\n"
        "      - uses: ./github/actions/local-check",
    )

    assert check_immutable_action_pins(tmp_path) == []


def test_repository_workflows_are_immutably_pinned() -> None:
    assert check_immutable_action_pins(ROOT) == []


@pytest.mark.parametrize(
    "uses_line",
    [
        f'"uses": actions/checkout@{CHECKOUT_SHA} # v7.0.1',
        f"uses : actions/checkout@{CHECKOUT_SHA} # v7.0.1",
    ],
    ids=["quoted-key", "space-before-colon"],
)
def test_rejects_noncanonical_uses_keys(tmp_path: Path, uses_line: str) -> None:
    _write_workflow(tmp_path, uses_line)

    failures = check_immutable_action_pins(tmp_path)

    assert any("unsupported uses reference" in failure for failure in failures)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("actions/checkout@v7 # v7.0.1", "full 40-character commit SHA"),
        ("actions/checkout@main # v7.0.1", "full 40-character commit SHA"),
        ("actions/checkout@3d3c42e # v7.0.1", "full 40-character commit SHA"),
        (f"actions/checkout@{CHECKOUT_SHA}", "reviewed release comment"),
        (f"actions/checkout@{CHECKOUT_SHA} # v7.0.0", "reviewed action pin"),
    ],
    ids=["tag", "branch", "abbreviated-sha", "missing-comment", "mismatched-comment"],
)
def test_rejects_mutable_or_unreviewed_action_reference(
    tmp_path: Path,
    reference: str,
    expected: str,
) -> None:
    _write_workflow(tmp_path, f"uses: {reference}")

    failures = check_immutable_action_pins(tmp_path)

    assert any(expected in failure for failure in failures)


@pytest.mark.parametrize(
    ("reference", "expected_failures"),
    [
        ("docker://python:3.14-slim", 1),
        ("docker://python@sha256:" + "a" * 64, 0),
    ],
    ids=["mutable-docker-tag", "immutable-docker-digest"],
)
def test_requires_immutable_docker_action_references(
    tmp_path: Path,
    reference: str,
    expected_failures: int,
) -> None:
    _write_workflow(tmp_path, f"uses: {reference}")

    assert len(check_immutable_action_pins(tmp_path)) == expected_failures


@pytest.mark.parametrize(
    ("default_image", "expected_failures"),
    [
        (REVIEWED_PYTHON_SMOKE_IMAGE, 0),
        ("python:3.14-slim", 1),
    ],
    ids=["reviewed-digest", "mutable-default-with-decoy"],
)
def test_validates_actual_smoke_default_assignment(
    tmp_path: Path,
    default_image: str,
    expected_failures: int,
) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "smoke_installed_package.py").write_text(
        f'# Decoy: {REVIEWED_PYTHON_SMOKE_IMAGE}\nDEFAULT_DOCKER_IMAGE = "{default_image}"\n',
        encoding="utf-8",
    )

    assert len(check_installed_smoke_docker_image(tmp_path)) == expected_failures
