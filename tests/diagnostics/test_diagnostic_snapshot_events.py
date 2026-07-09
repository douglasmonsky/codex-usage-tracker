from __future__ import annotations

import json

import pytest

from codex_usage_tracker.diagnostics.snapshot_events import (
    command_root_and_child,
    shell_command_from_payload,
)


def test_shell_command_from_payload_reads_supported_argument_shapes() -> None:
    assert (
        shell_command_from_payload(
            {"arguments": json.dumps({"cmd": "git diff --stat"})},
            function_name="exec_command",
        )
        == "git diff --stat"
    )
    assert (
        shell_command_from_payload(
            {"arguments": {"command": "pytest -q"}},
            function_name="functions.exec_command",
        )
        == "pytest -q"
    )
    assert shell_command_from_payload({"cmd": "rg TODO"}, function_name="shell") == "rg TODO"
    assert (
        shell_command_from_payload(
            {"arguments": "{not json", "command": "fallback"},
            function_name="exec_command",
        )
        == "fallback"
    )
    assert shell_command_from_payload({"cmd": "git status"}, function_name="read_file") is None


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
