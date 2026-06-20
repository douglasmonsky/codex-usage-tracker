"""Command-line interface for local Codex usage tracking."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from typing import Any

from codex_usage_tracker.allowance import (
    update_rate_card,
    write_allowance_from_text,
    write_allowance_template,
)
from codex_usage_tracker.api_payloads import (
    error_code,
    path_payload,
    plugin_install_payload,
    plugin_uninstall_payload,
    refresh_result_payload,
    session_payload,
)
from codex_usage_tracker.cli_parser import build_parser
from codex_usage_tracker.context import load_call_context
from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostic_reports import (
    build_diagnostics_fact_calls_report,
    build_diagnostics_facts_report,
    build_diagnostics_summary_report,
)
from codex_usage_tracker.diagnostic_snapshots import build_diagnostic_overview_report
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.formatting import (
    format_doctor,
    format_session,
)
from codex_usage_tracker.i18n import normalize_language
from codex_usage_tracker.parser import inspect_log, load_session_index
from codex_usage_tracker.plugin_installer import install_plugin, uninstall_plugin
from codex_usage_tracker.pricing import (
    pin_pricing_snapshot,
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.projects import (
    apply_project_privacy_to_rows,
    write_project_template,
)
from codex_usage_tracker.recommendations import write_threshold_template
from codex_usage_tracker.reports import (
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_query_report,
    build_recommendations_report,
    build_summary_report,
)
from codex_usage_tracker.server import serve_dashboard
from codex_usage_tracker.store import (
    export_usage_csv,
    query_session_usage,
    rebuild_usage_index,
    refresh_usage_index,
    reset_usage_database,
)
from codex_usage_tracker.support import build_support_bundle


def main() -> int:
    try:
        return _main()
    except BrokenPipeError:
        return 1
    except (FileExistsError, FileNotFoundError, PermissionError, RuntimeError, ValueError, OSError) as exc:
        print(f"Error: [{error_code(exc)}] {exc}", file=sys.stderr)
        return 1


def _main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        parser.error("unknown command")
        return 2
    return handler(args)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str), flush=True)


def _run_setup(args: argparse.Namespace) -> int:
    lines = ["Codex Usage Tracker setup summary", ""]
    codex_home_exists = args.codex_home.expanduser().exists()
    lines.append(
        f"Codex home: {args.codex_home.expanduser()} "
        f"({'found' if codex_home_exists else 'not found yet'})"
    )
    install_result = install_plugin(
        plugin_dir=args.plugin_dir,
        marketplace_path=args.marketplace,
        python_executable=args.python_executable,
        force=args.force_plugin,
    )
    lines.append(f"Plugin: installed at {install_result.plugin_dir}")
    lines.append(f"MCP Python: {install_result.python_executable}")
    pricing_payload: dict[str, Any]
    if args.skip_pricing:
        lines.append("Pricing: skipped")
        pricing_payload = {"status": "skipped", "path": path_payload(args.pricing)}
    elif args.update_pricing:
        pricing_result = update_pricing_from_openai_docs(args.pricing)
        lines.append(
            f"Pricing: updated {pricing_result.model_count} entries from {pricing_result.source_url}"
        )
        pricing_payload = {
            "status": "updated",
            "path": path_payload(pricing_result.path),
            "source_url": pricing_result.source_url,
            "tier": pricing_result.tier,
            "fetched_at": pricing_result.fetched_at,
            "model_count": pricing_result.model_count,
            "estimated_model_count": pricing_result.estimated_model_count,
        }
    elif args.pricing.expanduser().exists():
        lines.append(f"Pricing: existing config at {args.pricing}")
        pricing_payload = {"status": "existing", "path": path_payload(args.pricing)}
    else:
        pricing_output = write_pricing_template(args.pricing)
        lines.append(f"Pricing: wrote local template at {pricing_output}")
        pricing_payload = {"status": "initialized", "path": path_payload(pricing_output)}
    refresh_result = refresh_usage_index(
        codex_home=args.codex_home,
        db_path=args.db,
        include_archived=args.include_archived,
    )
    lines.append(
        f"Refresh: scanned {refresh_result.scanned_files} files, parsed "
        f"{refresh_result.parsed_events} events, skipped {refresh_result.skipped_events}"
    )
    doctor_report = run_doctor(
        codex_home=args.codex_home,
        db_path=args.db,
        pricing_path=args.pricing,
        plugin_link=args.plugin_dir,
        marketplace_path=args.marketplace,
        suggest_repair=True,
    )
    lines.append(f"Doctor: {doctor_report['status']}")
    if doctor_report.get("repair_suggestions"):
        lines.append("Repair suggestions:")
        lines.extend(f"- {suggestion}" for suggestion in doctor_report["repair_suggestions"])
    lines.append("")
    lines.append("Restart Codex to discover or refresh the plugin tools.")
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-setup-v1",
                "codex_home": path_payload(args.codex_home),
                "codex_home_exists": codex_home_exists,
                "plugin": plugin_install_payload(
                    install_result,
                    schema="codex-usage-tracker-plugin-install-v1",
                ),
                "pricing": pricing_payload,
                "refresh": refresh_result_payload(
                    refresh_result,
                    schema="codex-usage-tracker-refresh-v1",
                ),
                "doctor": doctor_report,
                "restart_required": True,
            }
        )
        return 0 if doctor_report["status"] != "fail" else 1
    print("\n".join(lines))
    return 0 if doctor_report["status"] != "fail" else 1


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
    if args.as_json:
        _print_json(plugin_install_payload(result, schema="codex-usage-tracker-plugin-install-v1"))
        return 0
    replacement_note = " Replaced existing plugin path." if result.replaced_existing else ""
    print(f"Installed Codex Usage Tracker plugin at {result.plugin_dir}.{replacement_note}")
    print(f"MCP Python: {result.python_executable}")
    print(f"Updated marketplace: {result.marketplace_path}")
    print("Restart Codex to discover the plugin.")
    return 0


def _run_upgrade_plugin(args: argparse.Namespace) -> int:
    result = install_plugin(
        plugin_dir=args.plugin_dir,
        marketplace_path=args.marketplace,
        python_executable=args.python_executable,
        force=True,
    )
    if args.as_json:
        _print_json(plugin_install_payload(result, schema="codex-usage-tracker-plugin-upgrade-v1"))
        return 0
    print(f"Upgraded Codex Usage Tracker plugin at {result.plugin_dir}.")
    print(f"MCP Python: {result.python_executable}")
    print(f"Updated marketplace: {result.marketplace_path}")
    print("Restart Codex to discover the refreshed plugin.")
    return 0


def _run_uninstall_plugin(args: argparse.Namespace) -> int:
    result = uninstall_plugin(
        plugin_dir=args.plugin_dir,
        marketplace_path=args.marketplace,
    )
    if args.as_json:
        _print_json(plugin_uninstall_payload(result))
        return 0
    print(
        f"Removed plugin path: {'yes' if result.removed_plugin_path else 'already absent'} "
        f"({result.plugin_dir})"
    )
    print(
        f"Removed marketplace entry: {'yes' if result.removed_marketplace_entry else 'not present'} "
        f"({result.marketplace_path})"
    )
    print("Restart Codex to unload plugin tools from new sessions.")
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    result = refresh_usage_index(
        codex_home=args.codex_home,
        db_path=args.db,
        include_archived=args.include_archived,
    )
    if args.as_json:
        _print_json(refresh_result_payload(result, schema="codex-usage-tracker-refresh-v1"))
        return 0
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
    if args.as_json:
        _print_json(refresh_result_payload(result, schema="codex-usage-tracker-rebuild-index-v1"))
        return 0
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


def _run_reset_db(args: argparse.Namespace) -> int:
    if not args.yes:
        raise ValueError(
            "reset-db clears local aggregate usage rows. Re-run with --yes to confirm."
        )
    result = reset_usage_database(db_path=args.db)
    if args.as_json:
        _print_json({"schema": "codex-usage-tracker-reset-db-v1", **result})
        return 0
    print(
        f"Cleared {result['deleted_usage_events']} aggregate usage rows from {result['db_path']}."
    )
    print("Raw Codex logs were not touched.")
    return 0


def _run_summary(args: argparse.Namespace) -> int:
    report = build_summary_report(
        db_path=args.db,
        pricing_path=args.pricing,
        group_by=args.group_by,
        preset=args.preset,
        since=args.since,
        limit=args.limit,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        _print_json(report.payload())
        return 0
    print(report.render())
    return 0


def _run_query(args: argparse.Namespace) -> int:
    report = build_query_report(
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        projects_path=args.projects,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        project=args.project,
        pricing_status=args.pricing_status,
        credit_confidence=args.credit_confidence,
        min_tokens=args.min_tokens,
        min_credits=args.min_credits,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    _print_json(report.payload)
    return 0


def _run_recommendations(args: argparse.Namespace) -> int:
    report = build_recommendations_report(
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        projects_path=args.projects,
        since=args.since,
        until=args.until,
        model=args.model,
        effort=args.effort,
        thread=args.thread,
        project=args.project,
        min_score=args.min_score,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        _print_json(report.payload)
        return 0
    print(report.render())
    return 0


def _run_diagnostics(args: argparse.Namespace) -> int:
    command = args.diagnostics_command
    report: Any
    if command == "summary":
        report = build_diagnostics_summary_report(
            db_path=args.db,
            limit=args.limit,
            since=args.since,
            until=args.until,
            model=args.model,
            effort=args.effort,
            thread=args.thread,
            min_tokens=args.min_tokens,
            fact_type=args.fact_type,
            fact_name=args.fact_name,
            fact_category=args.fact_category,
            include_archived=args.include_archived,
            sort=args.sort,
            direction=args.direction,
        )
    elif command in {"facts", "compactions", "tools"}:
        report = build_diagnostics_facts_report(
            db_path=args.db,
            limit=args.limit,
            since=args.since,
            until=args.until,
            model=args.model,
            effort=args.effort,
            thread=args.thread,
            min_tokens=args.min_tokens,
            fact_type=_diagnostic_fact_type_filter(args),
            fact_name=getattr(args, "fact_name", None),
            fact_category=getattr(args, "fact_category", None),
            include_archived=args.include_archived,
            sort=args.sort,
            direction=args.direction,
            fact_group="tools" if command == "tools" else None,
            view=command,
        )
    elif command == "fact-calls":
        report = build_diagnostics_fact_calls_report(
            db_path=args.db,
            fact_type=args.fact_type,
            fact_name=args.fact_name,
            limit=args.limit,
            offset=args.offset,
            since=args.since,
            until=args.until,
            model=args.model,
            effort=args.effort,
            thread=args.thread,
            min_tokens=args.min_tokens,
            include_archived=args.include_archived,
            sort=args.sort,
            direction=args.direction,
            privacy_mode=args.privacy_mode,
        )
    elif command == "overview":
        report = build_diagnostic_overview_report(
            db_path=args.db,
            include_archived=args.include_archived,
            refresh=args.refresh,
        )
    else:
        raise ValueError(f"unknown diagnostics command: {command}")

    if args.as_json:
        _print_json(report.payload)
        return 0
    print(report.render())
    return 0


def _diagnostic_fact_type_filter(args: argparse.Namespace) -> str | None:
    command = args.diagnostics_command
    if command == "compactions":
        return "compaction"
    return getattr(args, "fact_type", None)


def _run_session(args: argparse.Namespace) -> int:
    rows = query_session_usage(args.db, args.session_id, args.limit)
    rows = apply_project_privacy_to_rows(rows, privacy_mode=args.privacy_mode)
    if args.as_json:
        _print_json(
            session_payload(
                rows,
                requested_session_id=args.session_id,
                limit=args.limit,
                privacy_mode=args.privacy_mode,
            )
        )
        return 0
    print(format_session(rows))
    return 0


def _run_context(args: argparse.Namespace) -> int:
    payload = load_call_context(
        record_id=args.record_id,
        db_path=args.db,
        max_chars=args.max_chars,
        max_entries=args.max_entries,
        include_tool_output=args.include_tool_output,
        include_compaction_history=args.include_compaction_history,
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
        rate_card_path=args.rate_card,
        since=args.since,
        thresholds_path=args.thresholds,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
        include_archived=args.include_archived,
        language=normalize_language(args.lang),
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-dashboard-v1",
                "dashboard_path": path_payload(output),
                "file_url": output.resolve().as_uri(),
                "opened": args.open,
                "limit": None if args.limit <= 0 else args.limit,
                "since": args.since,
                "privacy_mode": args.privacy_mode,
                "include_archived": args.include_archived,
                "language": normalize_language(args.lang),
            }
        )
    else:
        print(f"Wrote dashboard to {output}")
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0


def _run_open_dashboard(args: argparse.Namespace) -> int:
    refresh_payload = None
    if args.refresh:
        refresh_payload = refresh_result_payload(
            refresh_usage_index(
                codex_home=args.codex_home,
                db_path=args.db,
                include_archived=args.include_archived,
            ),
            schema="codex-usage-tracker-refresh-v1",
        )
    output = generate_dashboard(
        db_path=args.db,
        output_path=args.output,
        limit=args.limit,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        since=args.since,
        thresholds_path=args.thresholds,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
        include_archived=args.include_archived,
        language=normalize_language(args.lang),
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-open-dashboard-v1",
                "dashboard_path": path_payload(output),
                "file_url": output.resolve().as_uri(),
                "opened": True,
                "limit": None if args.limit <= 0 else args.limit,
                "since": args.since,
                "refresh": refresh_payload,
                "privacy_mode": args.privacy_mode,
                "include_archived": args.include_archived,
                "language": normalize_language(args.lang),
            }
        )
    else:
        print(f"Opening dashboard at {output}")
    webbrowser.open(output.resolve().as_uri())
    return 0


def _run_serve_dashboard(args: argparse.Namespace) -> int:
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-serve-dashboard-v1",
                "host": args.host,
                "port": args.port,
                "dashboard_path": path_payload(args.output),
                "limit": None if args.limit <= 0 else args.limit,
                "since": args.since,
                "context_api": "disabled" if args.no_context_api else args.context_api,
                "refresh_before_start": args.refresh,
                "privacy_mode": args.privacy_mode,
                "include_archived": args.include_archived,
                "language": normalize_language(args.lang),
            }
        )
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
        rate_card_path=args.rate_card,
        limit=args.limit,
        since=args.since,
        host=args.host,
        port=args.port,
        context_chars=args.context_chars,
        open_browser=args.open,
        codex_home=args.codex_home,
        include_archived=args.include_archived,
        context_api="disabled" if args.no_context_api else args.context_api,
        thresholds_path=args.thresholds,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
        language=normalize_language(args.lang),
    )
    return 0


def _run_expensive(args: argparse.Namespace) -> int:
    report = build_expensive_calls_report(
        db_path=args.db,
        pricing_path=args.pricing,
        limit=args.limit,
        preset=args.preset,
        since=args.since,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        _print_json(report.payload())
        return 0
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
    count = export_usage_csv(
        output_path=args.output,
        db_path=args.db,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-export-v1",
                "rows": count,
                "csv_path": path_payload(args.output),
                "limit": args.limit,
                "privacy_mode": args.privacy_mode,
            }
        )
        return 0
    print(f"Wrote {count} aggregate usage rows to {args.output}")
    return 0


def _run_init_pricing(args: argparse.Namespace) -> int:
    output = write_pricing_template(args.output, force=args.force)
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-init-pricing-v1",
                "pricing_path": path_payload(output),
                "created": True,
            }
        )
        return 0
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
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-update-pricing-v1",
                "pricing_path": path_payload(result.path),
                "source_url": result.source_url,
                "tier": result.tier,
                "fetched_at": result.fetched_at,
                "model_count": result.model_count,
                "estimated_model_count": result.estimated_model_count,
                "backup_path": path_payload(result.backup_path) if result.backup_path else None,
            }
        )
        return 0
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


def _run_pin_pricing(args: argparse.Namespace) -> int:
    output = pin_pricing_snapshot(
        source_path=args.pricing,
        output_path=args.output,
        force=args.force,
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-pin-pricing-v1",
                "pricing_path": path_payload(output),
                "source_pricing_path": path_payload(args.pricing),
            }
        )
        return 0
    print(f"Pinned pricing snapshot to {output}")
    print("Use this file with --pricing for reproducible historical reports.")
    return 0


def _run_init_allowance(args: argparse.Namespace) -> int:
    output = write_allowance_template(args.output or args.allowance, force=args.force)
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-init-allowance-v1",
                "allowance_path": path_payload(output),
                "created": True,
            }
        )
        return 0
    print(f"Wrote allowance template to {output}")
    return 0


def _run_parse_allowance(args: argparse.Namespace) -> int:
    text = " ".join(args.text).strip()
    if not text:
        if sys.stdin.isatty():
            raise ValueError("provide pasted usage text or pipe it on stdin")
        text = sys.stdin.read().strip()
    output = write_allowance_from_text(
        text,
        path=args.output or args.allowance,
        force=args.force,
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-parse-allowance-v1",
                "allowance_path": path_payload(output),
                "updated": True,
            }
        )
        return 0
    print(f"Updated allowance windows from pasted usage text at {output}")
    return 0


def _run_update_rate_card(args: argparse.Namespace) -> int:
    result = update_rate_card(
        args.output or args.rate_card,
        source_file=args.source_file,
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-update-rate-card-v1",
                "rate_card_path": path_payload(result.path),
                "source_url": result.source_url,
                "fetched_at": result.fetched_at,
                "model_count": result.model_count,
                "alias_count": result.alias_count,
                "backup_path": path_payload(result.backup_path) if result.backup_path else None,
            }
        )
        return 0
    print(
        f"Wrote {result.model_count} Codex credit rates and {result.alias_count} aliases "
        f"to {result.path}"
        + (f" from {result.source_url}" if result.source_url else "")
        + (f" (backup: {result.backup_path})" if result.backup_path else "")
    )
    return 0


def _run_init_thresholds(args: argparse.Namespace) -> int:
    output = write_threshold_template(args.output or args.thresholds, force=args.force)
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-init-thresholds-v1",
                "thresholds_path": path_payload(output),
                "created": True,
            }
        )
        return 0
    print(f"Wrote recommendation threshold template to {output}")
    return 0


def _run_init_projects(args: argparse.Namespace) -> int:
    output = write_project_template(args.output or args.projects, force=args.force)
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-init-projects-v1",
                "projects_path": path_payload(output),
                "created": True,
            }
        )
        return 0
    print(f"Wrote project attribution template to {output}")
    return 0


def _run_support_bundle(args: argparse.Namespace) -> int:
    output = build_support_bundle(
        output_path=args.output,
        codex_home=args.codex_home,
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        thresholds_path=args.thresholds,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        _print_json(
            {
                "schema": "codex-usage-tracker-support-bundle-v1",
                "support_bundle_path": path_payload(output),
                "privacy": {
                    "contains_raw_logs": False,
                    "contains_prompts": False,
                    "contains_assistant_messages": False,
                    "contains_tool_output": False,
                    "project_metadata_mode": args.privacy_mode,
                },
            }
        )
        return 0
    print(f"Wrote privacy-preserving support bundle to {output}")
    print("Bundle excludes raw logs, prompts, assistant messages, tool output, and context text.")
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
    "reset-db": _run_reset_db,
    "summary": _run_summary,
    "query": _run_query,
    "recommendations": _run_recommendations,
    "diagnostics": _run_diagnostics,
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
    "pin-pricing": _run_pin_pricing,
    "init-allowance": _run_init_allowance,
    "parse-allowance": _run_parse_allowance,
    "update-rate-card": _run_update_rate_card,
    "init-thresholds": _run_init_thresholds,
    "init-projects": _run_init_projects,
    "support-bundle": _run_support_bundle,
}

if __name__ == "__main__":
    raise SystemExit(main())
