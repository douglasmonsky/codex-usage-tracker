"""Argument parser construction for the Codex usage tracker CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.cli.help_i18n import argument_parser_class, localize_parser_help
from codex_usage_tracker.cli.parser_data import (
    _add_allowance_intelligence_parsers,
    _add_allowance_parser,
    _add_dashboard_parsers,
    _add_dashboard_service_parser,
    _add_dedupe_diagnostics_parser,
    _add_expensive_parser,
    _add_export_parser,
    _add_pricing_coverage_parser,
    _add_pricing_parsers,
    _add_project_parser,
    _add_rate_card_parser,
    _add_source_coverage_parser,
    _add_support_bundle_parser,
    _add_threshold_parser,
)
from codex_usage_tracker.cli.parser_diagnostics import add_diagnostics_parser
from codex_usage_tracker.cli.parser_lifecycle import (
    _add_doctor_parser,
    _add_dogfood_agentic_parser,
    _add_inspect_log_parser,
    _add_install_plugin_parser,
    _add_rebuild_index_parser,
    _add_refresh_parser,
    _add_reset_db_parser,
    _add_setup_parser,
    _add_uninstall_plugin_parser,
    _add_upgrade_plugin_parser,
)
from codex_usage_tracker.cli.parser_reports import (
    _add_action_brief_parser,
    _add_context_parser,
    _add_query_parser,
    _add_recommendations_parser,
    _add_session_parser,
    _add_summary_parser,
)
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import PRIVACY_MODE_CHOICES


def build_parser(language: str | None = None) -> argparse.ArgumentParser:
    parser_class = argument_parser_class(language)
    parser = parser_class(prog="codex-usage-tracker")
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
    _add_dashboard_service_parser(subparsers)
    _add_dedupe_diagnostics_parser(subparsers)
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
    localize_parser_help(parser, language)
    return parser
