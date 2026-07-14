"""Usage report and context CLI command handlers."""

from __future__ import annotations

import argparse
import json

from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.core.api_payloads import (
    session_payload,
)
from codex_usage_tracker.core.formatting import (
    format_session,
)
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows
from codex_usage_tracker.recommendation_engine.query import build_recommendations_report
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_query_report,
    build_source_coverage_report,
    build_summary_report,
)
from codex_usage_tracker.store.api import (
    query_session_usage,
)


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
