"""CLI runner for the live Evidence Console server."""

from __future__ import annotations

import argparse

from codex_usage_tracker.cli.output import print_json
from codex_usage_tracker.core.i18n import normalize_language
from codex_usage_tracker.server.api import serve_dashboard
from codex_usage_tracker.server.utils import url_host


def run_serve_dashboard(args: argparse.Namespace) -> int:
    """Serve a live dashboard."""
    if args.as_json:
        print_json(
            {
                "schema": "codex-usage-tracker-serve-dashboard-v1",
                "host": args.host,
                "port": args.port,
                "dashboard_url": _served_dashboard_url(args.host, args.port),
                "limit": _limit_value(args),
                "since": args.since,
                "context_api": _context_api(args),
                "refresh_before_start": False,
                "refresh_in_background": args.refresh,
                "privacy_mode": args.privacy_mode,
                "include_archived": args.include_archived,
                "language": _language(args),
            }
        )
    serve_dashboard(
        db_path=args.db,
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
        refresh_on_start=args.refresh,
    )
    return 0


def _served_dashboard_url(host: str, port: int) -> str:
    return f"http://{url_host(host)}:{port}/react-dashboard.html"


def _context_api(args: argparse.Namespace) -> str:
    return "disabled" if args.no_context_api else args.context_api


def _language(args: argparse.Namespace) -> str:
    return normalize_language(args.lang)


def _limit_value(args: argparse.Namespace) -> int | None:
    return None if args.limit <= 0 else args.limit
