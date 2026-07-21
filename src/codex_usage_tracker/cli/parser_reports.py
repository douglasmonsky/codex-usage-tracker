"""Usage report and context CLI parser builders."""

from __future__ import annotations

import argparse

from codex_usage_tracker.context.api import DEFAULT_CONTEXT_CHARS, DEFAULT_CONTEXT_ENTRIES
from codex_usage_tracker.reports.api import (
    QUERY_CREDIT_CONFIDENCE_CHOICES,
    QUERY_PRICING_STATUS_CHOICES,
    SUMMARY_GROUP_BY_CHOICES,
    SUMMARY_PRESET_CHOICES,
)


def _add_summary_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    summary = subparsers.add_parser("summary", help="Show aggregate usage summary")
    summary.add_argument(
        "--group-by",
        choices=SUMMARY_GROUP_BY_CHOICES,
        default="thread",
    )
    summary.add_argument(
        "--preset",
        choices=SUMMARY_PRESET_CHOICES,
        help="Convenience preset for common summaries",
    )
    summary.add_argument("--since", help="Only include calls at or after this ISO date/time")
    summary.add_argument("--limit", type=int, default=20)
    summary.add_argument("--json", action="store_true", dest="as_json")


def _add_subagents_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("subagents", help="Analyze observed subagent spawns and usage")
    parser.add_argument("--since", help="Only include calls at or after this ISO date/time")
    parser.add_argument("--parent-thread")
    parser.add_argument("--agent-role")
    parser.add_argument("--subagent-type")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", dest="as_json")


def _add_query_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    query = subparsers.add_parser(
        "query",
        help="Return stable JSON aggregate usage rows with filters",
    )
    query.add_argument("--since", help="Only include calls at or after this ISO date/time")
    query.add_argument("--until", help="Only include calls at or before this ISO date/time")
    query.add_argument("--model")
    query.add_argument("--effort")
    query.add_argument("--thread")
    query.add_argument("--project")
    query.add_argument("--pricing-status", choices=QUERY_PRICING_STATUS_CHOICES)
    query.add_argument("--credit-confidence", choices=QUERY_CREDIT_CONFIDENCE_CHOICES)
    query.add_argument("--min-tokens", type=int)
    query.add_argument("--min-credits", type=float)
    query.add_argument(
        "--limit", type=int, default=100, help="Maximum rows to return; use 0 for all"
    )
    query.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Accepted for consistency; query always returns JSON.",
    )


def _add_recommendations_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    recommendations = subparsers.add_parser(
        "recommendations",
        help="Rank aggregate usage rows and threads by action recommendation severity",
    )
    recommendations.add_argument(
        "--since", help="Only include calls at or after this ISO date/time"
    )
    recommendations.add_argument(
        "--until", help="Only include calls at or before this ISO date/time"
    )
    recommendations.add_argument("--model")
    recommendations.add_argument("--effort")
    recommendations.add_argument("--thread")
    recommendations.add_argument("--project")
    recommendations.add_argument("--min-score", type=float)
    recommendations.add_argument(
        "--limit", type=int, default=20, help="Maximum rows to return; use 0 for all"
    )
    recommendations.add_argument("--json", action="store_true", dest="as_json")


def _add_action_brief_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    action_brief = subparsers.add_parser(
        "action-brief",
        help="Build compact aggregate remediation brief for usage-waste investigations",
    )
    action_brief.add_argument("--goal", default="token_waste")
    action_brief.add_argument("--since", help="Only include calls at or after this ISO date/time")
    action_brief.add_argument("--until", help="Only include calls at or before this ISO date/time")
    action_brief.add_argument("--thread")
    action_brief.add_argument("--include-archived", action="store_true")
    action_brief.add_argument("--evidence-limit", type=int, default=5)
    action_brief.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Accepted for consistency; action-brief always returns JSON.",
    )


def _add_session_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    session = subparsers.add_parser("session", help="Show one session's usage")
    session.add_argument("session_id", nargs="?")
    session.add_argument("--limit", type=int, default=200)
    session.add_argument("--json", action="store_true", dest="as_json")


def _add_context_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    context = subparsers.add_parser(
        "context",
        help="Load raw logged context for one usage record on demand",
    )
    context.add_argument("record_id")
    context.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_CONTEXT_CHARS,
        help="Maximum redacted context characters to return; use 0 for no character limit.",
    )
    context.add_argument(
        "--max-entries",
        type=int,
        default=DEFAULT_CONTEXT_ENTRIES,
        help="Maximum context entries to return; use 0 for all matching entries.",
    )
    context.add_argument(
        "--include-tool-output",
        action="store_true",
        help="Include redacted, size-limited tool output in the on-demand context.",
    )
    context.add_argument(
        "--include-compaction-history",
        action="store_true",
        help="Include redacted compaction replacement history when a compaction event is present.",
    )
    context.add_argument("--json", action="store_true", dest="as_json")
