"""Command-line interface for local Codex usage tracking."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.allowance import write_allowance_template
from codex_usage_tracker.context import DEFAULT_CONTEXT_CHARS, load_call_context
from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.formatting import (
    format_doctor,
    format_session,
)
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.parser import inspect_log, load_session_index
from codex_usage_tracker.plugin_installer import install_plugin
from codex_usage_tracker.pricing import (
    OPENAI_PRICING_MD_URL,
    VALID_PRICING_TIERS,
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.reports import (
    EXPENSIVE_PRESET_CHOICES,
    SUMMARY_GROUP_BY_CHOICES,
    SUMMARY_PRESET_CHOICES,
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_summary_report,
)
from codex_usage_tracker.store import (
    rebuild_usage_index,
    export_usage_csv,
    query_session_usage,
    refresh_usage_index,
)
from codex_usage_tracker.server import serve_dashboard


def main() -> int:
    try:
        return _main()
    except BrokenPipeError:
        return 1
    except (FileExistsError, FileNotFoundError, PermissionError, RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.error("unknown command")
        return 2
    return handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-usage-tracker")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    parser.add_argument("--allowance", type=Path, default=DEFAULT_ALLOWANCE_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_doctor_parser(subparsers)
    _add_install_plugin_parser(subparsers)
    _add_refresh_parser(subparsers)
    _add_inspect_log_parser(subparsers)
    _add_rebuild_index_parser(subparsers)
    _add_summary_parser(subparsers)
    _add_session_parser(subparsers)
    _add_context_parser(subparsers)
    _add_dashboard_parsers(subparsers)
    _add_expensive_parser(subparsers)
    _add_pricing_coverage_parser(subparsers)
    _add_export_parser(subparsers)
    _add_pricing_parsers(subparsers)
    _add_allowance_parser(subparsers)
    return parser


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


def _add_refresh_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    refresh = subparsers.add_parser("refresh", help="Scan Codex logs into SQLite")
    refresh.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    refresh.add_argument("--include-archived", action="store_true")


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


def _add_session_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    session = subparsers.add_parser("session", help="Show one session's usage")
    session.add_argument("session_id", nargs="?")
    session.add_argument("--limit", type=int, default=200)


def _add_context_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    context = subparsers.add_parser(
        "context",
        help="Load raw logged context for one usage record on demand",
    )
    context.add_argument("record_id")
    context.add_argument("--max-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    context.add_argument("--max-entries", type=int, default=80)
    context.add_argument(
        "--include-tool-output",
        action="store_true",
        help="Include redacted, size-limited tool output in the on-demand context.",
    )


def _add_dashboard_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    dashboard = subparsers.add_parser("dashboard", help="Generate static dashboard")
    dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    dashboard.add_argument("--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all")
    dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    dashboard.add_argument("--open", action="store_true")

    open_dashboard = subparsers.add_parser(
        "open-dashboard", help="Generate the default dashboard and open it"
    )
    open_dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    open_dashboard.add_argument("--limit", type=int, default=5000, help="Maximum calls to load; use 0 for all")
    open_dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    open_dashboard.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the SQLite index before generating the dashboard",
    )
    open_dashboard.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)

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
    serve.add_argument("--open", action="store_true")
    serve.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the SQLite index before generating and serving the dashboard",
    )
    serve.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    serve.add_argument("--include-archived", action="store_true")


def _add_expensive_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    expensive = subparsers.add_parser("expensive", help="Show largest last-call usage rows")
    expensive.add_argument("--limit", type=int, default=20)
    expensive.add_argument("--since", help="Only include calls at or after this ISO date/time")
    expensive.add_argument(
        "--preset",
        choices=EXPENSIVE_PRESET_CHOICES,
        help="Convenience date window",
    )


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


def _add_export_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    export = subparsers.add_parser("export", help="Export aggregate usage CSV")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--limit", type=int)


def _add_pricing_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pricing = subparsers.add_parser("init-pricing", help="Write a local pricing template")
    pricing.add_argument("--output", type=Path, default=DEFAULT_PRICING_PATH)
    pricing.add_argument("--force", action="store_true")

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


def _add_allowance_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    allowance = subparsers.add_parser(
        "init-allowance",
        help="Write a local template for optional Codex allowance windows",
    )
    allowance.add_argument("--output", type=Path, default=None)
    allowance.add_argument("--force", action="store_true")


def _run_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(
        db_path=args.db,
        pricing_path=args.pricing,
        suggest_repair=args.suggest_repair,
    )
    print(json.dumps(report, indent=2) if args.as_json else format_doctor(report))
    return 0 if report["status"] != "fail" else 1


def _run_install_plugin(args: argparse.Namespace) -> int:
    result = install_plugin(
        plugin_dir=args.plugin_dir,
        marketplace_path=args.marketplace,
        python_executable=args.python_executable,
        force=args.force,
    )
    replacement_note = " Replaced existing plugin path." if result.replaced_existing else ""
    print(f"Installed Codex Usage Tracker plugin at {result.plugin_dir}.{replacement_note}")
    print(f"MCP Python: {result.python_executable}")
    print(f"Updated marketplace: {result.marketplace_path}")
    print("Restart Codex to discover the plugin.")
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    result = refresh_usage_index(
        codex_home=args.codex_home,
        db_path=args.db,
        include_archived=args.include_archived,
    )
    print(
        f"Scanned {result.scanned_files} files, parsed {result.parsed_events} "
        f"usage events, upserted {result.inserted_or_updated_events} rows into {result.db_path}."
    )
    if result.skipped_events:
        print(f"Skipped {result.skipped_events} malformed token-count events.")
    if result.parser_diagnostics:
        diagnostics = ", ".join(
            f"{key}={value}" for key, value in result.parser_diagnostics.items()
        )
        print(f"Parser diagnostics: {diagnostics}")
    return 0


def _run_inspect_log(args: argparse.Namespace) -> int:
    payload = inspect_log(args.path, session_index=load_session_index(args.codex_home))
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Log: {payload['path']}")
    print(f"Adapter: {payload['adapter']}")
    print(f"File session id: {payload['file_session_id'] or 'unknown'}")
    print(f"Parsed events: {payload['event_count']}")
    if payload["session_ids"]:
        print("Sessions: " + ", ".join(str(value) for value in payload["session_ids"]))
    if payload["models"]:
        print("Models: " + ", ".join(str(value) for value in payload["models"]))
    diagnostics = payload["diagnostics"]
    if diagnostics:
        print(
            "Diagnostics: "
            + ", ".join(f"{key}={value}" for key, value in dict(diagnostics).items())
        )
    else:
        print("Diagnostics: none")
    return 0


def _run_rebuild_index(args: argparse.Namespace) -> int:
    result = rebuild_usage_index(
        codex_home=args.codex_home,
        db_path=args.db,
        include_archived=args.include_archived,
    )
    print(
        f"Rebuilt aggregate index: scanned {result.scanned_files} files, parsed "
        f"{result.parsed_events} usage events, upserted "
        f"{result.inserted_or_updated_events} rows into {result.db_path}."
    )
    if result.skipped_events:
        print(f"Skipped {result.skipped_events} malformed token-count events.")
    if result.parser_diagnostics:
        diagnostics = ", ".join(
            f"{key}={value}" for key, value in result.parser_diagnostics.items()
        )
        print(f"Parser diagnostics: {diagnostics}")
    return 0


def _run_summary(args: argparse.Namespace) -> int:
    report = build_summary_report(
        db_path=args.db,
        pricing_path=args.pricing,
        group_by=args.group_by,
        preset=args.preset,
        since=args.since,
        limit=args.limit,
    )
    print(report.render())
    return 0


def _run_session(args: argparse.Namespace) -> int:
    print(format_session(query_session_usage(args.db, args.session_id, args.limit)))
    return 0


def _run_context(args: argparse.Namespace) -> int:
    payload = load_call_context(
        record_id=args.record_id,
        db_path=args.db,
        max_chars=args.max_chars,
        max_entries=args.max_entries,
        include_tool_output=args.include_tool_output,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _run_dashboard(args: argparse.Namespace) -> int:
    output = generate_dashboard(
        db_path=args.db,
        output_path=args.output,
        limit=args.limit,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        since=args.since,
    )
    print(f"Wrote dashboard to {output}")
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0


def _run_open_dashboard(args: argparse.Namespace) -> int:
    if args.refresh:
        refresh_usage_index(codex_home=args.codex_home, db_path=args.db)
    output = generate_dashboard(
        db_path=args.db,
        output_path=args.output,
        limit=args.limit,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        since=args.since,
    )
    print(f"Opening dashboard at {output}")
    webbrowser.open(output.resolve().as_uri())
    return 0


def _run_serve_dashboard(args: argparse.Namespace) -> int:
    if args.refresh:
        refresh_usage_index(
            codex_home=args.codex_home,
            db_path=args.db,
            include_archived=args.include_archived,
        )
    serve_dashboard(
        db_path=args.db,
        output_path=args.output,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        limit=args.limit,
        since=args.since,
        host=args.host,
        port=args.port,
        context_chars=args.context_chars,
        open_browser=args.open,
        codex_home=args.codex_home,
        include_archived=args.include_archived,
    )
    return 0


def _run_expensive(args: argparse.Namespace) -> int:
    report = build_expensive_calls_report(
        db_path=args.db,
        pricing_path=args.pricing,
        limit=args.limit,
        preset=args.preset,
        since=args.since,
    )
    print(report.render())
    return 0


def _run_pricing_coverage(args: argparse.Namespace) -> int:
    report = build_pricing_coverage_report(
        db_path=args.db,
        pricing_path=args.pricing,
        since=args.since,
    )
    print(json.dumps(report.payload, indent=2) if args.as_json else report.render(args.limit))
    return 0


def _run_export(args: argparse.Namespace) -> int:
    count = export_usage_csv(output_path=args.output, db_path=args.db, limit=args.limit)
    print(f"Wrote {count} aggregate usage rows to {args.output}")
    return 0


def _run_init_pricing(args: argparse.Namespace) -> int:
    output = write_pricing_template(args.output, force=args.force)
    print(f"Wrote local pricing template to {output}")
    return 0


def _run_update_pricing(args: argparse.Namespace) -> int:
    output = args.output or args.pricing
    result = update_pricing_from_openai_docs(
        output,
        tier=args.tier,
        source_url=args.source_url,
        include_estimates=not args.no_estimates,
    )
    estimate_suffix = (
        f", including {result.estimated_model_count} estimated internal model"
        f"{'' if result.estimated_model_count == 1 else 's'}"
        if result.estimated_model_count
        else ""
    )
    print(
        f"Wrote {result.model_count} {result.tier} pricing entries from "
        f"{result.source_url} to {result.path}{estimate_suffix}"
        + (f" (backup: {result.backup_path})" if result.backup_path else "")
    )
    return 0


def _run_init_allowance(args: argparse.Namespace) -> int:
    output = write_allowance_template(args.output or args.allowance, force=args.force)
    print(f"Wrote allowance template to {output}")
    return 0


_COMMAND_HANDLERS = {
    "doctor": _run_doctor,
    "install-plugin": _run_install_plugin,
    "refresh": _run_refresh,
    "inspect-log": _run_inspect_log,
    "rebuild-index": _run_rebuild_index,
    "summary": _run_summary,
    "session": _run_session,
    "context": _run_context,
    "dashboard": _run_dashboard,
    "open-dashboard": _run_open_dashboard,
    "serve-dashboard": _run_serve_dashboard,
    "expensive": _run_expensive,
    "pricing-coverage": _run_pricing_coverage,
    "export": _run_export,
    "init-pricing": _run_init_pricing,
    "update-pricing": _run_update_pricing,
    "init-allowance": _run_init_allowance,
}

if __name__ == "__main__":
    raise SystemExit(main())
