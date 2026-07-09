"""Command-line interface for local Codex usage tracking."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_diagnostics_report,
    build_allowance_export_report,
    build_allowance_history_report,
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
from codex_usage_tracker.cli.diagnostics import run_diagnostics
from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.cli.parser import build_parser
from codex_usage_tracker.cli.plugin_installer import install_plugin, uninstall_plugin
from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.core.api_payloads import (
    error_code,
    path_payload,
    plugin_install_payload,
    plugin_uninstall_payload,
    refresh_result_payload,
    session_payload,
)
from codex_usage_tracker.core.formatting import (
    format_doctor,
    format_session,
)
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.parser.api import inspect_log, load_session_index
from codex_usage_tracker.pricing.api import update_pricing_from_openai_docs, write_pricing_template
from codex_usage_tracker.reports.agentic_dogfood import build_agentic_dogfood_report
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_query_report,
    build_recommendations_report,
    build_source_coverage_report,
    build_summary_report,
)
from codex_usage_tracker.reports.support import (
    build_support_bundle,
    support_bundle_issue_guidance,
)
from codex_usage_tracker.store.api import (
    export_usage_csv,
    query_session_usage,
    rebuild_usage_index,
    refresh_usage_index,
    reset_usage_database,
)


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
        print_json(
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
        print_json(plugin_install_payload(result, schema="codex-usage-tracker-plugin-install-v1"))
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
        print_json(plugin_install_payload(result, schema="codex-usage-tracker-plugin-upgrade-v1"))
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
        print_json(plugin_uninstall_payload(result))
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
        aggregate_only=args.aggregate_only,
    )
    if args.as_json:
        print_json(refresh_result_payload(result, schema="codex-usage-tracker-refresh-v1"))
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
        aggregate_only=args.aggregate_only,
    )
    if args.as_json:
        print_json(refresh_result_payload(result, schema="codex-usage-tracker-rebuild-index-v1"))
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


def _run_dogfood_agentic(args: argparse.Namespace) -> int:
    report = build_agentic_dogfood_report(
        codex_home=args.codex_home,
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        projects_path=args.projects,
        output_dir=args.output_dir,
        since=args.since,
        until=args.until,
        thread=args.thread,
        include_archived=args.include_archived,
        evidence_limit=args.evidence_limit,
        privacy_mode=args.privacy_mode,
        refresh=args.refresh,
        run_hypotheses=args.hypotheses,
        run_deep_investigations=args.deep_investigations,
        write_markdown=args.markdown,
    )
    if args.as_json:
        print_json(report)
        return 0
    artifacts = report["artifacts"]
    print(f"Wrote agentic dogfood summary {artifacts['summary_json_path']}")
    if artifacts.get("summary_markdown_path"):
        print(f"Wrote agentic dogfood brief {artifacts['summary_markdown_path']}")
    print(
        "Family checks: "
        f"old={report['family_checks']['old_passed']} "
        f"new={report['family_checks']['new_passed']}"
    )
    print(f"Progress: {report['progress']['percent_complete']}%")
    print(f"Cache keys: {', '.join(report['cache']['cache_keys']) or 'none'}")
    print(f"Privacy checks: {report['privacy_checks']['passed']}")
    return 0


def _run_reset_db(args: argparse.Namespace) -> int:
    if not args.yes:
        raise ValueError(
            "reset-db clears local aggregate usage rows. Re-run with --yes to confirm."
        )
    result = reset_usage_database(db_path=args.db)
    if args.as_json:
        print_json({"schema": "codex-usage-tracker-reset-db-v1", **result})
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
        print_json(report.payload())
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
    print_json(report.payload)
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
        include_archived=getattr(args, "include_archived", False),
        min_score=args.min_score,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        print_json(report.payload)
        return 0
    print(report.render())
    return 0


def _run_action_brief(args: argparse.Namespace) -> int:
    report = build_action_brief_report(
        db_path=args.db,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        projects_path=args.projects,
        goal=args.goal,
        since=args.since,
        until=args.until,
        thread=args.thread,
        include_archived=args.include_archived,
        evidence_limit=args.evidence_limit,
        privacy_mode=args.privacy_mode,
    )
    print_json(report.payload)
    return 0


def _run_session(args: argparse.Namespace) -> int:
    rows = query_session_usage(args.db, args.session_id, args.limit)
    rows = apply_project_privacy_to_rows(rows, privacy_mode=args.privacy_mode)
    if args.as_json:
        print_json(
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
        print_json(report.payload())
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


def _run_source_coverage(args: argparse.Namespace) -> int:
    report = build_source_coverage_report(
        db_path=args.db,
        include_archived=args.include_archived,
    )
    if args.as_json:
        print_json(report.payload)
        return 0
    print(report.render(args.limit))
    return 0


def _run_allowance_history(args: argparse.Namespace) -> int:
    report = build_allowance_history_report(
        db_path=args.db,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        include_archived=args.include_archived,
        window_kind=args.window_kind,
        limit=_allowance_report_limit(args.limit),
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        print_json(report.payload)
        return 0
    print(report.render())
    return 0


def _run_allowance_diagnostics(args: argparse.Namespace) -> int:
    report = build_allowance_diagnostics_report(
        db_path=args.db,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        include_archived=args.include_archived,
        window_kind=args.window_kind,
        limit=_allowance_report_limit(args.limit),
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        print_json(report.payload)
        return 0
    print(report.render())
    return 0


def _run_allowance_export(args: argparse.Namespace) -> int:
    report = build_allowance_export_report(
        db_path=args.db,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        include_archived=args.include_archived,
        window_kind=args.window_kind,
        limit=_allowance_report_limit(args.limit),
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report.payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.as_json:
        print_json(report.payload)
        return 0
    if args.output is not None:
        print(f"Wrote allowance evidence export to {args.output}")
        return 0
    print(report.render())
    return 0


def _allowance_report_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _run_export(args: argparse.Namespace) -> int:
    count = export_usage_csv(
        output_path=args.output,
        db_path=args.db,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        print_json(
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
    issue_guidance = support_bundle_issue_guidance(args.privacy_mode)
    if args.as_json:
        print_json(
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
                "issue_report": issue_guidance,
            }
        )
        return 0
    print(f"Wrote privacy-preserving support bundle to {output}")
    print("Bundle excludes raw logs, prompts, assistant messages, tool output, and context text.")
    print(
        "GitHub issue fields safe to paste after review: "
        + ", ".join(issue_guidance["cli_hint_fields"])
    )
    print("Full strict-bundle field list lives in issue_report.safe_fields.")
    if not issue_guidance["safe_to_paste_after_review"]:
        print("Use --privacy-mode strict before sharing support bundles publicly.")
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
    "expensive": _run_expensive,
    "pricing-coverage": _run_pricing_coverage,
    "source-coverage": _run_source_coverage,
    "allowance-history": _run_allowance_history,
    "allowance-diagnostics": _run_allowance_diagnostics,
    "allowance-export": _run_allowance_export,
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
