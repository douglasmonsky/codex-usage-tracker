"""CLI runner for diagnostics subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.diagnostics.reports import (
    build_diagnostics_fact_calls_report,
    build_diagnostics_facts_report,
    build_diagnostics_summary_report,
)
from codex_usage_tracker.diagnostics.snapshots import (
    build_diagnostic_commands_report,
    build_diagnostic_concentration_report,
    build_diagnostic_file_modifications_report,
    build_diagnostic_file_reads_report,
    build_diagnostic_git_interactions_report,
    build_diagnostic_guided_summary_report,
    build_diagnostic_overview_report,
    build_diagnostic_read_productivity_report,
    build_diagnostic_tool_output_report,
    build_diagnostic_usage_drain_report,
)

ReportBuilder = Callable[[argparse.Namespace], Any]


def run_diagnostics(args: argparse.Namespace) -> int:
    """Run a diagnostics CLI subcommand."""
    command = args.diagnostics_command
    try:
        report = _REPORT_BUILDERS[command](args)
    except KeyError as exc:
        raise ValueError(f"unknown diagnostics command: {command}") from exc

    if args.as_json:
        print_json(report.payload)
        return 0
    print(report.render())
    return 0


def diagnostic_fact_type_filter(args: argparse.Namespace) -> str | None:
    """Return the fact type filter implied by a diagnostics subcommand."""
    command = args.diagnostics_command
    if command == "compactions":
        return "compaction"
    return getattr(args, "fact_type", None)


def _build_summary_report(args: argparse.Namespace) -> Any:
    return build_diagnostics_summary_report(
        db_path=args.db,
        limit=args.limit,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        min_tokens=args.min_tokens,
        fact_type=args.fact_type,
        fact_name=args.fact_name,
        fact_category=args.fact_category,
        include_archived=args.include_archived,
        sort=args.sort,
        direction=args.direction,
    )


def _build_facts_report(args: argparse.Namespace) -> Any:
    command = args.diagnostics_command
    return build_diagnostics_facts_report(
        db_path=args.db,
        limit=args.limit,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        min_tokens=args.min_tokens,
        fact_type=diagnostic_fact_type_filter(args),
        fact_name=getattr(args, "fact_name", None),
        fact_category=getattr(args, "fact_category", None),
        include_archived=args.include_archived,
        sort=args.sort,
        direction=args.direction,
        fact_group="tools" if command == "tools" else None,
        view=command,
    )


def _build_fact_calls_report(args: argparse.Namespace) -> Any:
    return build_diagnostics_fact_calls_report(
        db_path=args.db,
        fact_type=args.fact_type,
        fact_name=args.fact_name,
        limit=args.limit,
        offset=args.offset,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        min_tokens=args.min_tokens,
        include_archived=args.include_archived,
        sort=args.sort,
        direction=args.direction,
        privacy_mode=args.privacy_mode,
    )


def _build_snapshot_report(args: argparse.Namespace) -> Any:
    builder = _SNAPSHOT_REPORT_BUILDERS[args.diagnostics_command]
    return builder(
        db_path=args.db,
        include_archived=args.include_archived,
        refresh=args.refresh,
    )


def _build_usage_drain_report(args: argparse.Namespace) -> Any:
    return build_diagnostic_usage_drain_report(
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        include_archived=args.include_archived,
        refresh=args.refresh,
    )


_REPORT_BUILDERS: dict[str, ReportBuilder] = {
    "summary": _build_summary_report,
    "facts": _build_facts_report,
    "compactions": _build_facts_report,
    "tools": _build_facts_report,
    "fact-calls": _build_fact_calls_report,
    "overview": _build_snapshot_report,
    "tool-output": _build_snapshot_report,
    "commands": _build_snapshot_report,
    "git-interactions": _build_snapshot_report,
    "file-reads": _build_snapshot_report,
    "file-modifications": _build_snapshot_report,
    "read-productivity": _build_snapshot_report,
    "concentration": _build_snapshot_report,
    "guided-summary": _build_snapshot_report,
    "usage-drain": _build_usage_drain_report,
}

_SNAPSHOT_REPORT_BUILDERS: dict[str, Callable[..., Any]] = {
    "overview": build_diagnostic_overview_report,
    "tool-output": build_diagnostic_tool_output_report,
    "commands": build_diagnostic_commands_report,
    "git-interactions": build_diagnostic_git_interactions_report,
    "file-reads": build_diagnostic_file_reads_report,
    "file-modifications": build_diagnostic_file_modifications_report,
    "read-productivity": build_diagnostic_read_productivity_report,
    "concentration": build_diagnostic_concentration_report,
    "guided-summary": build_diagnostic_guided_summary_report,
}
