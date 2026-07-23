"""Canonical parser for the stable and compatibility CLI surfaces."""

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
    _add_subagents_parser,
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
from codex_usage_tracker.interfaces.cli.namespaces import (
    LEGACY_TOP_LEVEL_ALIASES,
    STABLE_TOP_LEVEL_COMMANDS,
)


def build_parser(language: str | None = None) -> argparse.ArgumentParser:
    """Build the short primary CLI plus hidden, parseable legacy aliases."""
    parser_class = argument_parser_class(language)
    parser = parser_class(prog="codex-usage-tracker")
    _add_global_options(parser)
    primary_inventory = "{" + ",".join(STABLE_TOP_LEVEL_COMMANDS) + "}"
    subparsers = parser.add_subparsers(dest="command", required=True, metavar=primary_inventory)

    _add_legacy_surface(subparsers)
    legacy = dict(subparsers.choices)
    _mark_top_level_commands(legacy)
    _add_primary_commands(subparsers, legacy)

    localize_parser_help(parser, language)
    _hide_legacy_help_entries(subparsers)
    return parser


def _add_global_options(parser: argparse.ArgumentParser) -> None:
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


def _add_legacy_surface(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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
    _add_subagents_parser(subparsers)
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


def _mark_top_level_commands(legacy: dict[str, argparse.ArgumentParser]) -> None:
    for name in STABLE_TOP_LEVEL_COMMANDS:
        parser = legacy.get(name)
        if parser is not None:
            parser.set_defaults(command_path=(name,), compatibility_alias=None)
    for name in LEGACY_TOP_LEVEL_ALIASES:
        legacy[name].set_defaults(command_path=(name,), compatibility_alias=name)


def _add_primary_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    legacy: dict[str, argparse.ArgumentParser],
) -> None:
    status = subparsers.add_parser("status", help="Show current tracker status")
    status.add_argument("--json", action="store_true", dest="as_json")
    status.set_defaults(command_path=("status",), compatibility_alias=None)

    analyze = subparsers.add_parser("analyze", help="Run a bounded usage analysis")
    analyze.add_argument("--goal", default="token_waste")
    analyze.add_argument("--filters", default="{}", help="Analysis filters as a JSON object")
    analyze.add_argument("--since")
    analyze.add_argument("--until")
    analyze.add_argument("--model")
    analyze.add_argument("--effort")
    analyze.add_argument("--thread-key")
    analyze.add_argument("--project")
    analyze.add_argument("--origin")
    analyze.add_argument("--service-tier")
    analyze.add_argument("--subagent-role")
    analyze.add_argument("--subagent-type")
    analyze.add_argument("--parent-thread-key")
    analyze.add_argument("--history-scope", choices=("active", "all"), default="active")
    analyze.add_argument("--evidence-limit", type=int, default=5)
    analyze.add_argument("--comparison", default="{}", help="Comparison as a JSON object")
    analyze.add_argument("--execution", choices=("auto", "sync", "async"), default="auto")
    analyze.add_argument("--json", action="store_true", dest="as_json")
    analyze.set_defaults(command_path=("analyze",), compatibility_alias=None)

    opened = subparsers.add_parser("open", help="Open the Evidence Console at an exact target")
    target = opened.add_mutually_exclusive_group()
    target.add_argument("--target-json")
    target.add_argument("--target-id")
    target.add_argument("--call-id")
    target.add_argument("--thread-key")
    opened.add_argument("--json", action="store_true", dest="as_json")
    opened.set_defaults(command_path=("open",), compatibility_alias=None)

    _add_config_namespace(subparsers, legacy)
    _add_service_namespace(subparsers, legacy)
    _add_admin_namespace(subparsers, legacy)


def _add_config_namespace(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    legacy: dict[str, argparse.ArgumentParser],
) -> None:
    config = subparsers.add_parser("config", help="Manage local tracker configuration")
    groups = config.add_subparsers(dest="config_group", required=True)
    mappings = {
        "pricing": (("init", "init-pricing"), ("update", "update-pricing"), ("pin", "pin-pricing")),
        "allowance": (
            ("init", "init-allowance"),
            ("parse", "parse-allowance"),
            ("history", "allowance-history"),
            ("diagnostics", "allowance-diagnostics"),
            ("export", "allowance-export"),
        ),
        "rate-card": (("update", "update-rate-card"),),
        "projects": (("init", "init-projects"),),
        "thresholds": (("init", "init-thresholds"),),
    }
    for group_name, commands in mappings.items():
        group = groups.add_parser(group_name)
        actions = group.add_subparsers(dest="config_action", required=True)
        for action_name, legacy_name in commands:
            _clone_leaf(
                actions, action_name, legacy[legacy_name], ("config", group_name, action_name)
            )
    config.set_defaults(compatibility_alias=None)


def _add_service_namespace(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    legacy: dict[str, argparse.ArgumentParser],
) -> None:
    service = subparsers.add_parser("service", help="Manage the local dashboard service")
    actions = service.add_subparsers(dest="service_action", required=True)
    legacy_service = _subparser_action(legacy["dashboard-service"])
    for action_name in ("install", "status", "uninstall"):
        _clone_leaf(
            actions,
            action_name,
            legacy_service.choices[action_name],
            ("service", action_name),
        )
    _clone_leaf(actions, "serve", legacy["serve-dashboard"], ("service", "serve"))
    service.set_defaults(compatibility_alias=None)


def _add_admin_namespace(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    legacy: dict[str, argparse.ArgumentParser],
) -> None:
    admin = subparsers.add_parser("admin", help="Run operational and maintenance commands")
    actions = admin.add_subparsers(dest="admin_action", required=True)
    for action_name in (
        "inspect-log",
        "rebuild-index",
        "reset-db",
        "dedupe-diagnostics",
        "source-coverage",
        "support-bundle",
    ):
        _clone_leaf(actions, action_name, legacy[action_name], ("admin", action_name))
    _clone_leaf(actions, "dogfood", legacy["dogfood-agentic"], ("admin", "dogfood"))
    mcp = actions.add_parser("mcp", help="Run the MCP server over standard input/output")
    mcp_actions = mcp.add_subparsers(dest="mcp_action", required=True)
    serve = mcp_actions.add_parser("serve", help="Run the MCP server over standard input/output")
    serve.add_argument("--profile", choices=("core", "full", "developer"), default=None)
    serve.set_defaults(command_path=("admin", "mcp", "serve"), compatibility_alias=None)
    admin.set_defaults(compatibility_alias=None)


def _clone_leaf(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    source: argparse.ArgumentParser,
    command_path: tuple[str, ...],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, parents=[source], add_help=False)
    parser.set_defaults(command_path=command_path, compatibility_alias=None)
    return parser


def _subparser_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[argparse.ArgumentParser]:
    return next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )


def _hide_legacy_help_entries(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    by_name = {action.dest: action for action in subparsers._choices_actions}
    subparsers._choices_actions[:] = [by_name[name] for name in STABLE_TOP_LEVEL_COMMANDS]
