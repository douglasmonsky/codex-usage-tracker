"""Lifecycle and index-maintenance CLI command handlers."""

from __future__ import annotations

import argparse
import json
from typing import Any

from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.cli.plugin_installer import install_plugin, uninstall_plugin
from codex_usage_tracker.core.api_payloads import (
    path_payload,
    plugin_install_payload,
    plugin_uninstall_payload,
    refresh_result_payload,
)
from codex_usage_tracker.core.formatting import (
    format_doctor,
)
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.pricing.api import update_pricing_from_openai_docs, write_pricing_template
from codex_usage_tracker.recommendation_engine.api import (
    rebuild_usage_index,
    refresh_usage_index,
)
from codex_usage_tracker.reports.agentic_dogfood import build_agentic_dogfood_report
from codex_usage_tracker.store.api import reset_usage_database


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
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        thresholds_path=args.thresholds,
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
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        thresholds_path=args.thresholds,
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


def _run_rebuild_index(args: argparse.Namespace) -> int:
    result = rebuild_usage_index(
        codex_home=args.codex_home,
        db_path=args.db,
        include_archived=args.include_archived,
        aggregate_only=args.aggregate_only,
        pricing_path=args.pricing,
        allowance_path=args.allowance,
        rate_card_path=args.rate_card,
        thresholds_path=args.thresholds,
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
