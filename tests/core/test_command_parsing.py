from __future__ import annotations

import pytest

from codex_usage_tracker.core.command_parsing import command_root_and_child, safe_label


@pytest.mark.parametrize(
    ("command", "expected_root"),
    [
        ("bash -lc 'rg TODO src'", "rg"),
        ("zsh -lc 'git status --short'", "git"),
        ("sh -c 'nl -ba src/app.py'", "nl"),
        ("python -m pytest -q", "pytest"),
        ("python3 -m mypy", "mypy"),
        ("uv run pytest -q", "pytest"),
        ("poetry run python -m pytest", "pytest"),
        ("npx eslint .", "eslint"),
        ("npm run test", "npm"),
        ("$PWCLI status", "pwcli"),
    ],
)
def test_command_root_and_child_normalizes_common_wrappers(
    command: str, expected_root: str
) -> None:
    root, _child = command_root_and_child(command)
    assert root == expected_root


def test_command_root_and_child_handles_git_options_and_malformed_quotes() -> None:
    assert command_root_and_child("git -C /tmp/repo status --short") == ("git", "status")
    assert command_root_and_child("bash -lc '") == ("unknown_command", "unknown")


def test_safe_label_rejects_paths_and_secret_prefixes() -> None:
    assert safe_label("PyTest") == "pytest"
    assert safe_label("src/private.py") is None
    assert safe_label("ghp_example") is None
