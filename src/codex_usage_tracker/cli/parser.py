"""Argument parser construction for the Codex usage tracker CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.cli.parser_diagnostics import add_diagnostics_parser
from codex_usage_tracker.context.api import DEFAULT_CONTEXT_CHARS, DEFAULT_CONTEXT_ENTRIES
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_SUPPORT_BUNDLE_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import PRIVACY_MODE_CHOICES
from codex_usage_tracker.pricing.api import OPENAI_PRICING_MD_URL, VALID_PRICING_TIERS
from codex_usage_tracker.reports.agentic_dogfood import DEFAULT_AGENTIC_DOGFOOD_DIR
from codex_usage_tracker.reports.api import (
    EXPENSIVE_PRESET_CHOICES,
    QUERY_CREDIT_CONFIDENCE_CHOICES,
    QUERY_PRICING_STATUS_CHOICES,
    SUMMARY_GROUP_BY_CHOICES,
    SUMMARY_PRESET_CHOICES,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-usage-tracker")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    parser.add_argument("--allowance", type=Path, default=DEFAULT_ALLOWANCE_PATH)
    parser.add_argument("--rate-card", type=Path, default=DEFAULT_RATE_CARD_PATH)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS_PATH)
    parser.add_argument("--projects", type=Path, default=DEFAULT_PROJECTS_PATH)
    parser.add_argument(
        "--lang",
        default=None,
        help=(
            "Initial dashboard language. Accepts supported language codes and common aliases; "
            "defaults to CODEX_USAGE_TRACKER_LANG or en."
        ),
    )
    parser.add_argument(
        "--privacy-mode",
        choices=PRIVACY_MODE_CHOICES,
        default="normal",
        help=(
            "Project metadata display mode: normal keeps local labels, redacted hides "
            "raw paths and hashes unnamed projects, strict also hides branch, relative cwd, and tags."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_setup_parser(subparsers)
    _add_doctor_parser(subparsers)
    _add_install_plugin_parser(subparsers)
    _add_upgrade_plugin_parser(subparsers)
    _add_uninstall_plugin_parser(subparsers)
    _add_refresh_parser(subparsers)
    _add_inspect_log_parser(subparsers)
    _add_rebuild_index_parser(subparsers)
    _add_dogfood_agentic_parser(subparsers)
    _add_reset_db_parser(subparsers)
    _add_summary_parser(subparsers)
    _add_query_parser(subparsers)
    _add_recommendations_parser(subparsers)
    _add_action_brief_parser(subparsers)
    add_diagnostics_parser(subparsers)
    _add_session_parser(subparsers)
    _add_context_parser(subparsers)
    _add_dashboard_parsers(subparsers)
    _add_expensive_parser(subparsers)
    _add_pricing_coverage_parser(subparsers)
    _add_source_coverage_parser(subparsers)
    _add_export_parser(subparsers)
    _add_pricing_parsers(subparsers)
    _add_allowance_parser(subparsers)
    _add_allowance_intelligence_parsers(subparsers)
    _add_rate_card_parser(subparsers)
    _add_threshold_parser(subparsers)
    _add_project_parser(subparsers)
    _add_support_bundle_parser(subparsers)
    return parser


def _add_setup_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = subparsers.add_parser(
        "setup",
        help="Run first-time setup: plugin install, pricing init, refresh, and doctor",
    )
    setup.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    setup.add_argument("--include-archived", action="store_true")
    setup.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_LINK)
    setup.add_argument("--marketplace", type=Path, default=DEFAULT_MARKETPLACE_PATH)
    setup.add_argument(
        "--python",
        type=Path,
        default=None,
        dest="python_executable",
        help="Python executable Codex should use for the MCP server.",
    )
    setup.add_argument(
        "--force-plugin",
        action="store_true",
        help="Replace an existing generated plugin wrapper or source-checkout symlink.",
    )
    setup.add_argument("--skip-pricing", action="store_true")
    setup.add_argument(
        "--update-pricing",
        action="store_true",
        help="Fetch current pricing during setup instead of writing a local template.",
    )
    setup.add_argument("--json", action="store_true", dest="as_json")


def _add_doctor_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    doctor = subparsers.add_parser("doctor", help="Check local setup without writing files")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument(
        "--suggest-repair",
        action="store_true",
        help="Include read-only repair suggestions for warning and failure checks.",
    )


def _add_install_plugin_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    install_plugin_cmd = subparsers.add_parser(
        "install-plugin",
        help="Register this installed package as a local Codex plugin",
    )
    install_plugin_cmd.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_LINK)
    install_plugin_cmd.add_argument("--marketplace", type=Path, default=DEFAULT_MARKETPLACE_PATH)
    install_plugin_cmd.add_argument(
        "--python",
        type=Path,
        default=None,
        dest="python_executable",
        help="Python executable Codex should use for the MCP server.",
    )
    install_plugin_cmd.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing generated plugin directory or source-checkout symlink.",
    )
    install_plugin_cmd.add_argument("--json", action="store_true", dest="as_json")


def _add_upgrade_plugin_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    upgrade_plugin_cmd = subparsers.add_parser(
        "upgrade-plugin",
        help="Refresh the generated local Codex plugin wrapper for this installed package",
    )
    upgrade_plugin_cmd.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_LINK)
    upgrade_plugin_cmd.add_argument("--marketplace", type=Path, default=DEFAULT_MARKETPLACE_PATH)
    upgrade_plugin_cmd.add_argument(
        "--python",
        type=Path,
        default=None,
        dest="python_executable",
        help="Python executable Codex should use for the MCP server.",
    )
    upgrade_plugin_cmd.add_argument("--json", action="store_true", dest="as_json")


def _add_uninstall_plugin_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    uninstall_plugin_cmd = subparsers.add_parser(
        "uninstall-plugin",
        help="Remove the generated local Codex plugin wrapper and marketplace entry",
    )
    uninstall_plugin_cmd.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_LINK)
    uninstall_plugin_cmd.add_argument("--marketplace", type=Path, default=DEFAULT_MARKETPLACE_PATH)
    uninstall_plugin_cmd.add_argument("--json", action="store_true", dest="as_json")


def _add_refresh_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    refresh = subparsers.add_parser("refresh", help="Scan Codex logs into SQLite")
    refresh.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    refresh.add_argument("--include-archived", action="store_true")
    refresh.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Skip local content indexing and store aggregate usage rows only.",
    )
    refresh.add_argument("--json", action="store_true", dest="as_json")


def _add_inspect_log_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    inspect = subparsers.add_parser(
        "inspect-log",
        help="Inspect one Codex JSONL log through the parser without writing to SQLite",
    )
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    inspect.add_argument("--json", action="store_true", dest="as_json")


def _add_rebuild_index_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    rebuild = subparsers.add_parser(
        "rebuild-index",
        help="Clear aggregate rows and rescan local Codex logs",
    )
    rebuild.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    rebuild.add_argument("--include-archived", action="store_true")
    rebuild.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Rebuild aggregate usage rows without local content indexing.",
    )
    rebuild.add_argument("--json", action="store_true", dest="as_json")


def _add_dogfood_agentic_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    dogfood = subparsers.add_parser(
        "dogfood-agentic",
        help="Run repeatable local dogfood checks for agentic MCP investigation reports",
    )
    dogfood.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    dogfood.add_argument("--output-dir", type=Path, default=DEFAULT_AGENTIC_DOGFOOD_DIR)
    dogfood.add_argument("--since", help="Only include calls at or after this ISO date/time")
    dogfood.add_argument("--until", help="Only include calls at or before this ISO date/time")
    dogfood.add_argument("--thread")
    dogfood.add_argument("--include-archived", action="store_true")
    dogfood.add_argument("--evidence-limit", type=int, default=5)
    dogfood.add_argument(
        "--hypotheses",
        action="store_true",
        help="Run slower full hypothesis evidence scans instead of quick routing checks.",
    )
    dogfood.add_argument(
        "--deep-investigations",
        action="store_true",
        help="Also run the slower full usage_investigate dogfood paths instead of reusing action brief findings.",
    )
    dogfood.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh active local usage before running the dogfood report.",
    )
    dogfood.add_argument(
        "--markdown",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write a compact Markdown summary next to summary.json.",
    )
    dogfood.add_argument("--json", action="store_true", dest="as_json")


def _add_reset_db_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    reset = subparsers.add_parser(
        "reset-db",
        help="Clear tracker-owned aggregate rows and refresh metadata",
    )
    reset.add_argument(
        "--yes",
        action="store_true",
        help="Confirm clearing local aggregate usage rows. Raw Codex logs are not touched.",
    )
    reset.add_argument("--json", action="store_true", dest="as_json")


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
    query.add_argument("--limit", type=int, default=100, help="Maximum rows to return; use 0 for all")
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
    recommendations.add_argument("--since", help="Only include calls at or after this ISO date/time")
    recommendations.add_argument("--until", help="Only include calls at or before this ISO date/time")
    recommendations.add_argument("--model")
    recommendations.add_argument("--effort")
    recommendations.add_argument("--thread")
    recommendations.add_argument("--project")
    recommendations.add_argument("--min-score", type=float)
    recommendations.add_argument("--limit", type=int, default=20, help="Maximum rows to return; use 0 for all")
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


def _add_dashboard_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    dashboard = subparsers.add_parser("dashboard", help="Generate static dashboard")
    dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    dashboard.add_argument("--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all")
    dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    dashboard.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived session rows already present in the SQLite index.",
    )
    dashboard.add_argument("--open", action="store_true")
    dashboard.add_argument("--json", action="store_true", dest="as_json")

    open_dashboard = subparsers.add_parser(
        "open-dashboard", help="Generate the default dashboard and open it"
    )
    open_dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    open_dashboard.add_argument("--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all")
    open_dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    open_dashboard.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived sessions when refreshing and in the generated dashboard.",
    )
    open_dashboard.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Refresh the SQLite index before generating the dashboard. "
            "This is the default; use --no-refresh to open the cached index only."
        ),
    )
    open_dashboard.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    open_dashboard.add_argument("--json", action="store_true", dest="as_json")

    serve = subparsers.add_parser(
        "serve-dashboard",
        help="Serve dashboard with lazy localhost context loading",
    )
    serve.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    serve.add_argument("--limit", type=int, default=5000, help="Initial maximum calls to load; use 0 for all")
    serve.add_argument("--since", help="Only include calls at or after this ISO date/time")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    serve.add_argument(
        "--context-api",
        choices=["explicit", "disabled"],
        default="explicit",
        help="Enable explicit per-row context loading or disable the context API.",
    )
    serve.add_argument(
        "--no-context-api",
        action="store_true",
        help="Start with dashboard context loading off; it can be enabled from the local dashboard.",
    )
    serve.add_argument("--open", action="store_true")
    serve.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Refresh the SQLite index before generating and serving the dashboard. "
            "This is the default; use --no-refresh to serve the cached index only."
        ),
    )
    serve.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    serve.add_argument("--include-archived", action="store_true")
    serve.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Accepted for API consistency; serve-dashboard still runs as a long-lived server.",
    )


def _add_expensive_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    expensive = subparsers.add_parser("expensive", help="Show largest last-call usage rows")
    expensive.add_argument("--limit", type=int, default=20)
    expensive.add_argument("--since", help="Only include calls at or after this ISO date/time")
    expensive.add_argument(
        "--preset",
        choices=EXPENSIVE_PRESET_CHOICES,
        help="Convenience date window",
    )
    expensive.add_argument("--json", action="store_true", dest="as_json")


def _add_pricing_coverage_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pricing_coverage = subparsers.add_parser(
        "pricing-coverage", help="Show priced, estimated, and unpriced token coverage"
    )
    pricing_coverage.add_argument("--since", help="Only include calls at or after this ISO date/time")
    pricing_coverage.add_argument("--limit", type=int, default=20)
    pricing_coverage.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Return the coverage report as JSON",
    )


def _add_source_coverage_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    source_coverage = subparsers.add_parser(
        "source-coverage",
        help="Show source provenance and parser coverage",
    )
    source_coverage.add_argument("--include-archived", action="store_true")
    source_coverage.add_argument("--limit", type=int, default=20)
    source_coverage.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Return source coverage report as JSON",
    )


def _add_export_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    export = subparsers.add_parser("export", help="Export aggregate usage CSV")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--limit", type=int)
    export.add_argument("--json", action="store_true", dest="as_json")


def _add_pricing_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pricing = subparsers.add_parser("init-pricing", help="Write a local pricing template")
    pricing.add_argument("--output", type=Path, default=DEFAULT_PRICING_PATH)
    pricing.add_argument("--force", action="store_true")
    pricing.add_argument("--json", action="store_true", dest="as_json")

    update_pricing = subparsers.add_parser(
        "update-pricing", help="Fetch OpenAI text-token pricing into the local config"
    )
    update_pricing.add_argument("--output", type=Path, default=None)
    update_pricing.add_argument("--source", choices=["openai-docs"], default="openai-docs")
    update_pricing.add_argument("--tier", choices=VALID_PRICING_TIERS, default="standard")
    update_pricing.add_argument("--source-url", default=OPENAI_PRICING_MD_URL)
    update_pricing.add_argument(
        "--no-estimates",
        action="store_true",
        help="Skip estimated prices for internal Codex model labels.",
    )
    update_pricing.add_argument("--json", action="store_true", dest="as_json")

    pin_pricing = subparsers.add_parser(
        "pin-pricing",
        help="Copy the current local pricing config to a reproducible report snapshot",
    )
    pin_pricing.add_argument("--output", type=Path, required=True)
    pin_pricing.add_argument("--force", action="store_true")
    pin_pricing.add_argument("--json", action="store_true", dest="as_json")


def _add_allowance_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    allowance = subparsers.add_parser(
        "init-allowance",
        help="Write a local template for optional Codex allowance windows",
    )
    allowance.add_argument("--output", type=Path, default=None)
    allowance.add_argument("--force", action="store_true")
    allowance.add_argument("--json", action="store_true", dest="as_json")

    parse_allowance = subparsers.add_parser(
        "parse-allowance",
        help="Update allowance windows from pasted Codex /status or usage text",
    )
    parse_allowance.add_argument(
        "text",
        nargs="*",
        help="Pasted usage text. Reads stdin when omitted.",
    )
    parse_allowance.add_argument("--output", type=Path, default=None)
    parse_allowance.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an invalid existing allowance config.",
    )
    parse_allowance.add_argument("--json", action="store_true", dest="as_json")


def _add_allowance_intelligence_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    history = subparsers.add_parser(
        "allowance-history",
        help="Return normalized observed Codex allowance history",
    )
    _add_allowance_intelligence_filters(history, default_limit=1000)
    history.add_argument("--json", action="store_true", dest="as_json")

    diagnostics = subparsers.add_parser(
        "allowance-diagnostics",
        help="Diagnose observed allowance movement against local credit estimates",
    )
    _add_allowance_intelligence_filters(diagnostics, default_limit=10000)
    diagnostics.add_argument("--json", action="store_true", dest="as_json")

    export = subparsers.add_parser(
        "allowance-export",
        help="Build strict-privacy allowance evidence bundle for manual sharing",
    )
    _add_allowance_intelligence_filters(export, default_limit=10000)
    export.add_argument("--output", type=Path, default=None)
    export.add_argument("--json", action="store_true", dest="as_json")


def _add_allowance_intelligence_filters(
    parser: argparse.ArgumentParser, *, default_limit: int
) -> None:
    parser.add_argument(
        "--window-kind",
        choices=("weekly", "five_hour", "custom", "unknown"),
        default=None,
        help="Limit analysis to one observed allowance window kind.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help="Maximum normalized observations to inspect. Use 0 for all.",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived Codex sessions.",
    )


def _add_rate_card_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    rate_card = subparsers.add_parser(
        "update-rate-card",
        help="Write the bundled or supplied Codex credit rate-card snapshot locally",
    )
    rate_card.add_argument("--output", type=Path, default=None)
    rate_card.add_argument(
        "--source-file",
        type=Path,
        default=None,
        help="Validate and copy this JSON rate-card snapshot instead of the bundled one.",
    )
    rate_card.add_argument("--json", action="store_true", dest="as_json")


def _add_threshold_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    thresholds = subparsers.add_parser(
        "init-thresholds",
        help="Write a local template for dashboard recommendation thresholds",
    )
    thresholds.add_argument("--output", type=Path, default=None)
    thresholds.add_argument("--force", action="store_true")
    thresholds.add_argument("--json", action="store_true", dest="as_json")


def _add_project_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    projects = subparsers.add_parser(
        "init-projects",
        help="Write a local template for project aliases, ignored paths, and tags",
    )
    projects.add_argument("--output", type=Path, default=None)
    projects.add_argument("--force", action="store_true")
    projects.add_argument("--json", action="store_true", dest="as_json")


def _add_support_bundle_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    support = subparsers.add_parser(
        "support-bundle",
        help="Write a privacy-preserving diagnostic bundle for support",
    )
    support.add_argument("--output", type=Path, default=DEFAULT_SUPPORT_BUNDLE_PATH)
    support.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    support.add_argument("--json", action="store_true", dest="as_json")
