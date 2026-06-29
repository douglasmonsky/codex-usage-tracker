from __future__ import annotations

from codex_usage_tracker.cli.parser import build_parser


def test_diagnostics_cli_parser_keeps_nested_subcommand_arguments() -> None:
    parser = build_parser()

    overview = parser.parse_args(["diagnostics", "overview", "--refresh", "--json"])
    assert overview.command == "diagnostics"
    assert overview.diagnostics_command == "overview"
    assert overview.refresh is True
    assert overview.as_json is True

    calls = parser.parse_args(
        [
            "diagnostics",
            "fact-calls",
            "--fact-type",
            "function",
            "--fact-name",
            "functions.exec_command",
            "--sort",
            "tokens",
            "--direction",
            "asc",
            "--limit",
            "5",
        ]
    )
    assert calls.diagnostics_command == "fact-calls"
    assert calls.fact_type == "function"
    assert calls.fact_name == "functions.exec_command"
    assert calls.sort == "tokens"
    assert calls.direction == "asc"
    assert calls.limit == 5
