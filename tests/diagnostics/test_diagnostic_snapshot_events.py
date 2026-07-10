from __future__ import annotations

import json

from codex_usage_tracker.diagnostics.snapshot_events import shell_command_from_payload


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
