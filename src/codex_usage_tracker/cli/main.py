"""Command-line interface for local Codex usage tracking."""

from __future__ import annotations

import argparse
import json
import sys

from codex_usage_tracker.cli.commands_data import (
    _run_allowance_diagnostics,
    _run_allowance_export,
    _run_allowance_history,
    _run_dedupe_diagnostics,
    _run_export,
    _run_support_bundle,
)
from codex_usage_tracker.cli.commands_lifecycle import (
    _run_doctor,
    _run_dogfood_agentic,
    _run_install_plugin,
    _run_rebuild_index,
    _run_refresh,
    _run_reset_db,
    _run_setup,
    _run_uninstall_plugin,
    _run_upgrade_plugin,
)
from codex_usage_tracker.cli.commands_reports import (
    _run_action_brief,
    _run_context,
    _run_expensive,
    _run_pricing_coverage,
    _run_query,
    _run_recommendations,
    _run_session,
    _run_source_coverage,
    _run_summary,
)
from codex_usage_tracker.cli.config import (
    run_init_allowance,
    run_init_pricing,
    run_init_projects,
    run_init_thresholds,
    run_parse_allowance,
    run_pin_pricing,
    run_update_pricing,
    run_update_rate_card,
)
from codex_usage_tracker.cli.dashboard import (
    run_dashboard,
    run_open_dashboard,
    run_serve_dashboard,
)
from codex_usage_tracker.cli.dashboard_service import run_dashboard_service
from codex_usage_tracker.cli.diagnostics import run_diagnostics
from codex_usage_tracker.cli.help_i18n import localized_cli_error_prefix, requested_cli_language
from codex_usage_tracker.cli.inspect_log_output import print_inspect_log_summary
from codex_usage_tracker.cli.parser import build_parser
from codex_usage_tracker.core.api_payloads import (
    error_code,
)
from codex_usage_tracker.parser.api import inspect_log, load_session_index


def main() -> int:
    try:
        return _main()
    except BrokenPipeError:
        return 1
    except (
        FileExistsError,
        FileNotFoundError,
        PermissionError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        language = requested_cli_language(sys.argv[1:])
        print(f"{localized_cli_error_prefix(language)}: [{error_code(exc)}] {exc}", file=sys.stderr)
        return 1


def _main() -> int:
    language = requested_cli_language(sys.argv[1:])
    parser = build_parser(language)
    args = parser.parse_args()
    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.error("未知命令" if language == "zh-Hans" else "unknown command")
        return 2
    return handler(args)


def _run_inspect_log(args: argparse.Namespace) -> int:
    payload = inspect_log(args.path, session_index=load_session_index(args.codex_home))
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0
    print_inspect_log_summary(payload)
    return 0


_COMMAND_HANDLERS = {
    "setup": _run_setup,
    "doctor": _run_doctor,
    "install-plugin": _run_install_plugin,
    "upgrade-plugin": _run_upgrade_plugin,
    "uninstall-plugin": _run_uninstall_plugin,
    "refresh": _run_refresh,
    "inspect-log": _run_inspect_log,
    "rebuild-index": _run_rebuild_index,
    "dogfood-agentic": _run_dogfood_agentic,
    "reset-db": _run_reset_db,
    "summary": _run_summary,
    "query": _run_query,
    "recommendations": _run_recommendations,
    "action-brief": _run_action_brief,
    "diagnostics": run_diagnostics,
    "session": _run_session,
    "context": _run_context,
    "dashboard": run_dashboard,
    "open-dashboard": run_open_dashboard,
    "serve-dashboard": run_serve_dashboard,
    "dashboard-service": run_dashboard_service,
    "expensive": _run_expensive,
    "pricing-coverage": _run_pricing_coverage,
    "source-coverage": _run_source_coverage,
    "allowance-history": _run_allowance_history,
    "allowance-diagnostics": _run_allowance_diagnostics,
    "allowance-export": _run_allowance_export,
    "dedupe-diagnostics": _run_dedupe_diagnostics,
    "export": _run_export,
    "init-pricing": run_init_pricing,
    "update-pricing": run_update_pricing,
    "pin-pricing": run_pin_pricing,
    "init-allowance": run_init_allowance,
    "parse-allowance": run_parse_allowance,
    "update-rate-card": run_update_rate_card,
    "init-thresholds": run_init_thresholds,
    "init-projects": run_init_projects,
    "support-bundle": _run_support_bundle,
}

if __name__ == "__main__":
    raise SystemExit(main())
