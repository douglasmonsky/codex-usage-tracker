from __future__ import annotations

import argparse
import ast
from pathlib import Path

from codex_usage_tracker.interfaces.cli.namespaces import (
    ADMIN_COMMANDS,
    CONFIG_COMMANDS,
    LEGACY_TOP_LEVEL_ALIASES,
    SERVICE_COMMANDS,
    STABLE_TOP_LEVEL_COMMANDS,
)
from codex_usage_tracker.interfaces.cli.parser import build_parser

EXPECTED_STABLE = (
    "setup",
    "status",
    "doctor",
    "refresh",
    "analyze",
    "query",
    "open",
    "export",
    "config",
    "service",
    "admin",
)


def test_primary_cli_inventory_is_exact_and_help_hides_legacy_aliases() -> None:
    parser = build_parser()
    help_text = parser.format_help()

    assert STABLE_TOP_LEVEL_COMMANDS == EXPECTED_STABLE
    assert "{" + ",".join(EXPECTED_STABLE) + "}" in help_text
    assert "summary" not in help_text
    assert "dashboard-service" not in help_text
    assert "install-plugin" not in help_text


def test_namespace_inventories_and_parsed_destinations_are_exact() -> None:
    assert CONFIG_COMMANDS == ("pricing", "allowance", "rate-card", "projects", "thresholds")
    assert SERVICE_COMMANDS == ("install", "status", "uninstall", "serve")
    assert ADMIN_COMMANDS == (
        "inspect-log",
        "rebuild-index",
        "reset-db",
        "dedupe-diagnostics",
        "source-coverage",
        "support-bundle",
        "dogfood",
        "mcp",
    )

    parser = build_parser()
    assert parser.parse_args(["config", "pricing", "init"]).command_path == (
        "config",
        "pricing",
        "init",
    )
    assert parser.parse_args(["service", "status"]).command_path == ("service", "status")
    assert parser.parse_args(["admin", "source-coverage"]).command_path == (
        "admin",
        "source-coverage",
    )
    assert parser.parse_args(["admin", "mcp", "serve", "--profile", "full"]).command_path == (
        "admin",
        "mcp",
        "serve",
    )


def test_every_historical_top_level_command_remains_parseable_as_an_alias() -> None:
    parser = build_parser()
    top_level = _top_level_subparsers(parser)

    assert set(STABLE_TOP_LEVEL_COMMANDS) | set(LEGACY_TOP_LEVEL_ALIASES) == set(top_level.choices)
    for name in LEGACY_TOP_LEVEL_ALIASES:
        args = parser.parse_args(_minimal_legacy_argv(name))
        assert args.compatibility_alias == name


def test_translated_help_keeps_the_same_short_primary_inventory() -> None:
    help_text = build_parser("zh-Hans").format_help()

    assert "{" + ",".join(EXPECTED_STABLE) + "}" in help_text
    assert "summary" not in help_text


def test_new_cli_interface_sources_parse_as_python_310() -> None:
    root = Path(__file__).resolve().parents[3]
    for relative in (
        "src/codex_usage_tracker/interfaces/cli/parser.py",
        "src/codex_usage_tracker/interfaces/cli/namespaces.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        ast.parse(source, filename=relative, feature_version=(3, 10))


def _top_level_subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[argparse.ArgumentParser]:
    return next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )


def _minimal_legacy_argv(name: str) -> list[str]:
    positional = {
        "inspect-log": ["session.jsonl"],
        "session": ["session-1"],
        "context": ["record-1"],
        "export": ["--output", "usage.csv"],
        "pin-pricing": ["--output", "pricing.json"],
    }
    nested = {
        "dashboard-service": ["status"],
        "diagnostics": ["summary"],
    }
    return [name, *positional.get(name, nested.get(name, []))]
