"""Dashboard, pricing, allowance, and export CLI parser builders."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_usage_tracker.context.api import DEFAULT_CONTEXT_CHARS
from codex_usage_tracker.core.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_SUPPORT_BUNDLE_PATH,
)
from codex_usage_tracker.pricing.api import OPENAI_PRICING_MD_URL, VALID_PRICING_TIERS
from codex_usage_tracker.reports.api import (
    EXPENSIVE_PRESET_CHOICES,
)


def _add_dashboard_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    dashboard = subparsers.add_parser("dashboard", help="Generate static dashboard")
    dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    dashboard.add_argument(
        "--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all"
    )
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
    open_dashboard.add_argument(
        "--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all"
    )
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
    serve.add_argument(
        "--limit", type=int, default=5000, help="Initial maximum calls to load; use 0 for all"
    )
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


def _add_dedupe_diagnostics_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    diagnostics = subparsers.add_parser(
        "dedupe-diagnostics",
        help="Show copied clone usage rows excluded from billable totals",
    )
    diagnostics.add_argument("--limit", type=int, default=100)
    diagnostics.add_argument("--json", action="store_true", dest="as_json")


def _add_pricing_coverage_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pricing_coverage = subparsers.add_parser(
        "pricing-coverage", help="Show priced, estimated, and unpriced token coverage"
    )
    pricing_coverage.add_argument(
        "--since", help="Only include calls at or after this ISO date/time"
    )
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
