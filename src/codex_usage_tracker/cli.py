"""Command-line interface for local Codex usage tracking."""

from __future__ import annotations

import argparse
import json
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.formatting import (
    format_calls,
    format_doctor,
    format_pricing_coverage,
    format_session,
    format_summary,
)
from codex_usage_tracker.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.pricing import (
    OPENAI_PRICING_MD_URL,
    VALID_PRICING_TIERS,
    annotate_rows_with_efficiency,
    load_pricing_config,
    summarize_pricing_coverage,
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.store import (
    export_usage_csv,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
    refresh_usage_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="codex-usage-tracker")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local setup without writing files")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    refresh = subparsers.add_parser("refresh", help="Scan Codex logs into SQLite")
    refresh.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    refresh.add_argument("--include-archived", action="store_true")

    summary = subparsers.add_parser("summary", help="Show aggregate usage summary")
    summary.add_argument(
        "--group-by",
        choices=["date", "model", "effort", "cwd", "thread", "session"],
        default="thread",
    )
    summary.add_argument(
        "--preset",
        choices=["today", "last-7-days", "by-model", "by-cwd", "by-thread", "expensive"],
        help="Convenience preset for common summaries",
    )
    summary.add_argument("--since", help="Only include calls at or after this ISO date/time")
    summary.add_argument("--limit", type=int, default=20)

    session = subparsers.add_parser("session", help="Show one session's usage")
    session.add_argument("session_id", nargs="?")
    session.add_argument("--limit", type=int, default=200)

    dashboard = subparsers.add_parser("dashboard", help="Generate static dashboard")
    dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    dashboard.add_argument("--limit", type=int, default=5000)
    dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    dashboard.add_argument("--open", action="store_true")

    open_dashboard = subparsers.add_parser(
        "open-dashboard", help="Generate the default dashboard and open it"
    )
    open_dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD_PATH)
    open_dashboard.add_argument("--limit", type=int, default=5000)
    open_dashboard.add_argument("--since", help="Only include calls at or after this ISO date/time")
    open_dashboard.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the SQLite index before generating the dashboard",
    )
    open_dashboard.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)

    expensive = subparsers.add_parser("expensive", help="Show largest last-call usage rows")
    expensive.add_argument("--limit", type=int, default=20)
    expensive.add_argument("--since", help="Only include calls at or after this ISO date/time")
    expensive.add_argument(
        "--preset",
        choices=["today", "last-7-days"],
        help="Convenience date window",
    )

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

    export = subparsers.add_parser("export", help="Export aggregate usage CSV")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--limit", type=int)

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

    args = parser.parse_args()

    if args.command == "doctor":
        report = run_doctor(db_path=args.db, pricing_path=args.pricing)
        print(json.dumps(report, indent=2) if args.as_json else format_doctor(report))
        return 0 if report["status"] != "fail" else 1

    if args.command == "refresh":
        result = refresh_usage_index(
            codex_home=args.codex_home,
            db_path=args.db,
            include_archived=args.include_archived,
        )
        print(
            f"Scanned {result.scanned_files} files, parsed {result.parsed_events} "
            f"usage events, upserted {result.inserted_or_updated_events} rows into {result.db_path}."
        )
        return 0

    if args.command == "summary":
        group_by, since = _resolve_summary_options(args.group_by, args.preset, args.since)
        pricing = load_pricing_config(args.pricing)
        if args.preset == "expensive":
            rows = query_most_expensive_calls(args.db, limit=args.limit, since=since)
            print(format_calls(annotate_rows_with_efficiency(rows, pricing)))
            return 0
        rows = query_summary(args.db, group_by, args.limit, since=since)
        if group_by == "model":
            rows = annotate_rows_with_efficiency(rows, pricing, model_field="group_key")
        print(format_summary(rows, group_by))
        return 0

    if args.command == "session":
        print(format_session(query_session_usage(args.db, args.session_id, args.limit)))
        return 0

    if args.command == "dashboard":
        output = generate_dashboard(
            db_path=args.db,
            output_path=args.output,
            limit=args.limit,
            pricing_path=args.pricing,
            since=args.since,
        )
        print(f"Wrote dashboard to {output}")
        if args.open:
            webbrowser.open(output.resolve().as_uri())
        return 0

    if args.command == "open-dashboard":
        if args.refresh:
            refresh_usage_index(codex_home=args.codex_home, db_path=args.db)
        output = generate_dashboard(
            db_path=args.db,
            output_path=args.output,
            limit=args.limit,
            pricing_path=args.pricing,
            since=args.since,
        )
        print(f"Opening dashboard at {output}")
        webbrowser.open(output.resolve().as_uri())
        return 0

    if args.command == "expensive":
        since = _resolve_since(args.preset, args.since)
        pricing = load_pricing_config(args.pricing)
        rows = query_most_expensive_calls(args.db, limit=args.limit, since=since)
        print(format_calls(annotate_rows_with_efficiency(rows, pricing)))
        return 0

    if args.command == "pricing-coverage":
        pricing = load_pricing_config(args.pricing)
        rows = query_summary(args.db, group_by="model", limit=1000, since=args.since)
        report = summarize_pricing_coverage(rows, pricing=pricing)
        print(json.dumps(report, indent=2) if args.as_json else format_pricing_coverage(report, args.limit))
        return 0

    if args.command == "export":
        count = export_usage_csv(output_path=args.output, db_path=args.db, limit=args.limit)
        print(f"Wrote {count} aggregate usage rows to {args.output}")
        return 0

    if args.command == "init-pricing":
        output = write_pricing_template(args.output, force=args.force)
        print(f"Wrote local pricing template to {output}")
        return 0

    if args.command == "update-pricing":
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

    parser.error("unknown command")
    return 2


def _resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    if preset == "by-model":
        group_by = "model"
    elif preset == "by-cwd":
        group_by = "cwd"
    elif preset == "by-thread":
        group_by = "thread"
    return group_by, _resolve_since(preset, since)


def _resolve_since(preset: str | None, since: str | None) -> str | None:
    if since:
        return since
    if preset == "today":
        return date.today().isoformat()
    if preset == "last-7-days":
        return (date.today() - timedelta(days=6)).isoformat()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
