"""Lifecycle and index-maintenance CLI parser builders."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_usage_tracker.core.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
)
from codex_usage_tracker.reports.agentic_dogfood import DEFAULT_AGENTIC_DOGFOOD_DIR


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


def _add_inspect_log_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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
