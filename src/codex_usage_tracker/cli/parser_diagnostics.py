"""Argument parser construction for diagnostics CLI commands."""

from __future__ import annotations

import argparse

from codex_usage_tracker.diagnostics.reports import (
    DIAGNOSTIC_CALL_SORT_CHOICES,
    DIAGNOSTIC_DIRECTION_CHOICES,
    DIAGNOSTIC_FACT_SORT_CHOICES,
)


def add_diagnostics_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    diagnostics = subparsers.add_parser(
        "diagnostics",
        help="Inspect aggregate diagnostic facts and their associated token costs",
    )
    diagnostic_subparsers = diagnostics.add_subparsers(
        dest="diagnostics_command",
        required=True,
    )

    summary = diagnostic_subparsers.add_parser(
        "summary",
        help="Summarize diagnostic facts by fact type",
    )
    _add_diagnostics_fact_filters(summary)
    _add_diagnostics_fact_sort(summary, default_limit=20)

    facts = diagnostic_subparsers.add_parser(
        "facts",
        help="List diagnostic facts with associated token totals",
    )
    _add_diagnostics_fact_filters(facts)
    _add_diagnostics_fact_sort(facts, default_limit=50)

    compactions = diagnostic_subparsers.add_parser(
        "compactions",
        help="List compaction diagnostic facts",
    )
    _add_diagnostics_base_filters(compactions)
    _add_diagnostics_fact_sort(compactions, default_limit=50)

    tools = diagnostic_subparsers.add_parser(
        "tools",
        help="List tool/function diagnostic facts",
    )
    _add_diagnostics_base_filters(tools)
    _add_diagnostics_fact_sort(tools, default_limit=50)

    overview = diagnostic_subparsers.add_parser(
        "overview",
        help="Show the on-demand aggregate diagnostic overview snapshot",
    )
    overview.add_argument("--include-archived", action="store_true")
    overview.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the overview snapshot before reading it.",
    )
    overview.add_argument("--json", action="store_true", dest="as_json")

    tool_output = diagnostic_subparsers.add_parser(
        "tool-output",
        help="Show the on-demand aggregate tool-output snapshot",
    )
    tool_output.add_argument("--include-archived", action="store_true")
    tool_output.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the tool-output snapshot before reading it.",
    )
    tool_output.add_argument("--json", action="store_true", dest="as_json")

    commands = diagnostic_subparsers.add_parser(
        "commands",
        help="Show the on-demand aggregate command root snapshot",
    )
    commands.add_argument("--include-archived", action="store_true")
    commands.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the command snapshot before reading it.",
    )
    commands.add_argument("--json", action="store_true", dest="as_json")

    git_interactions = diagnostic_subparsers.add_parser(
        "git-interactions",
        help="Show on-demand aggregate Git and GitHub CLI interactions",
    )
    git_interactions.add_argument("--include-archived", action="store_true")
    git_interactions.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the Git interaction snapshot before reading it.",
    )
    git_interactions.add_argument("--json", action="store_true", dest="as_json")

    file_reads = diagnostic_subparsers.add_parser(
        "file-reads",
        help="Show the on-demand aggregate file-read snapshot",
    )
    file_reads.add_argument("--include-archived", action="store_true")
    file_reads.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the file-read snapshot before reading it.",
    )
    file_reads.add_argument("--json", action="store_true", dest="as_json")

    file_modifications = diagnostic_subparsers.add_parser(
        "file-modifications",
        help="Show on-demand aggregate file-modification snapshots",
    )
    file_modifications.add_argument("--include-archived", action="store_true")
    file_modifications.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the file-modification snapshot before reading it.",
    )
    file_modifications.add_argument("--json", action="store_true", dest="as_json")

    read_productivity = diagnostic_subparsers.add_parser(
        "read-productivity",
        help="Show temporal read-to-modify diagnostic correlations",
    )
    read_productivity.add_argument("--include-archived", action="store_true")
    read_productivity.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the read-productivity snapshot before reading it.",
    )
    read_productivity.add_argument("--json", action="store_true", dest="as_json")

    concentration = diagnostic_subparsers.add_parser(
        "concentration",
        help="Show concentration of token impact by source log, cwd, and day",
    )
    concentration.add_argument("--include-archived", action="store_true")
    concentration.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the concentration snapshot before reading it.",
    )
    concentration.add_argument("--json", action="store_true", dest="as_json")

    guided_summary = diagnostic_subparsers.add_parser(
        "guided-summary",
        help="Show plain-language aggregate usage-driver diagnostics",
    )
    guided_summary.add_argument("--include-archived", action="store_true")
    guided_summary.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist guided summary snapshot before reading it.",
    )
    guided_summary.add_argument("--json", action="store_true", dest="as_json")

    usage_drain = diagnostic_subparsers.add_parser(
        "usage-drain",
        help="Show usage-drain modeling and cumulative cost diagnostic reports",
    )
    usage_drain.add_argument("--include-archived", action="store_true")
    usage_drain.add_argument(
        "--refresh",
        action="store_true",
        help="Recompute and persist the usage-drain snapshot before reading it.",
    )
    usage_drain.add_argument("--json", action="store_true", dest="as_json")

    fact_calls = diagnostic_subparsers.add_parser(
        "fact-calls",
        help="List calls associated with one diagnostic fact",
    )
    fact_calls.add_argument("--fact-type", required=True)
    fact_calls.add_argument("--fact-name", required=True)
    _add_diagnostics_base_filters(fact_calls)
    fact_calls.add_argument("--offset", type=int, default=0)
    fact_calls.add_argument("--limit", type=int, default=50, help="Maximum rows; use 0 for all")
    fact_calls.add_argument("--sort", choices=DIAGNOSTIC_CALL_SORT_CHOICES, default="tokens")
    fact_calls.add_argument("--direction", choices=DIAGNOSTIC_DIRECTION_CHOICES, default="desc")
    fact_calls.add_argument("--json", action="store_true", dest="as_json")


def _add_diagnostics_base_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since", help="Only include calls at or after this ISO date/time")
    parser.add_argument("--until", help="Only include calls at or before this ISO date/time")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--thread")
    parser.add_argument("--min-tokens", type=int)
    parser.add_argument("--include-archived", action="store_true")


def _add_diagnostics_fact_filters(parser: argparse.ArgumentParser) -> None:
    _add_diagnostics_base_filters(parser)
    parser.add_argument("--fact-type")
    parser.add_argument("--fact-name")
    parser.add_argument("--fact-category")


def _add_diagnostics_fact_sort(
    parser: argparse.ArgumentParser,
    *,
    default_limit: int,
) -> None:
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum rows; use 0 for all")
    parser.add_argument("--sort", choices=DIAGNOSTIC_FACT_SORT_CHOICES, default="uncached")
    parser.add_argument("--direction", choices=DIAGNOSTIC_DIRECTION_CHOICES, default="desc")
    parser.add_argument("--json", action="store_true", dest="as_json")
