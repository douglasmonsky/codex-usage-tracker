"""CLI runners for dashboard commands."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path
from typing import Any

from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.core.api_payloads import path_payload, refresh_result_payload
from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.dashboard.api import generate_dashboard
from codex_usage_tracker.server.api import serve_dashboard
from codex_usage_tracker.store.api import refresh_usage_index


def run_dashboard(args: argparse.Namespace) -> int:
    """Generate a static dashboard file."""
    output = _generate_dashboard(args)
    if args.as_json:
        print_json(
            _dashboard_payload(
                args,
                output=output,
                schema="codex-usage-tracker-dashboard-v1",
                opened=args.open,
            )
        )
    else:
        print(f"Wrote dashboard to {output}")
    if args.open:
        webbrowser.open(output.resolve().as_uri())
    return 0


def run_open_dashboard(args: argparse.Namespace) -> int:
    """Generate and open a static dashboard file."""
    refresh_payload = _refresh_payload(args) if args.refresh else None
    output = _generate_dashboard(args)
    if args.as_json:
        print_json(
            {
                **_dashboard_payload(
                    args,
                    output=output,
                    schema="codex-usage-tracker-open-dashboard-v1",
                    opened=True,
                ),
                "refresh": refresh_payload,
            }
        )
    else:
        print(f"Opening dashboard at {output}")
    webbrowser.open(output.resolve().as_uri())
    return 0


def run_serve_dashboard(args: argparse.Namespace) -> int:
    """Serve a live dashboard."""
    if args.as_json:
        print_json(
            {
                "schema": "codex-usage-tracker-serve-dashboard-v1",
                "host": args.host,
                "port": args.port,
                "dashboard_path": path_payload(args.output),
                "limit": _limit_value(args),
                "since": args.since,
                "context_api": _context_api(args),
                "refresh_before_start": args.refresh,
                "privacy_mode": args.privacy_mode,
                "include_archived": args.include_archived,
                "language": _language(args),
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
        context_api=_context_api(args),
        thresholds_path=args.thresholds,
        projects_path=args.projects,
        privacy_mode=args.privacy_mode,
        language=_language(args),
    )
    return 0


def _generate_dashboard(args: argparse.Namespace) -> Path:
    return generate_dashboard(
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
        language=_language(args),
    )


def _dashboard_payload(
    args: argparse.Namespace,
    *,
    output: Path,
    schema: str,
    opened: bool,
) -> dict[str, Any]:
    return {
        "schema": schema,
        "dashboard_path": path_payload(output),
        "file_url": output.resolve().as_uri(),
        "opened": opened,
        "limit": _limit_value(args),
        "since": args.since,
        "privacy_mode": args.privacy_mode,
        "include_archived": args.include_archived,
        "language": _language(args),
    }


def _refresh_payload(args: argparse.Namespace) -> dict[str, Any]:
    return refresh_result_payload(
        refresh_usage_index(
            codex_home=args.codex_home,
            db_path=args.db,
            include_archived=args.include_archived,
        ),
        schema="codex-usage-tracker-refresh-v1",
    )


def _context_api(args: argparse.Namespace) -> str:
    return "disabled" if args.no_context_api else args.context_api


def _language(args: argparse.Namespace) -> str:
    return normalize_language(args.lang)


def _limit_value(args: argparse.Namespace) -> int | None:
    return None if args.limit <= 0 else args.limit
