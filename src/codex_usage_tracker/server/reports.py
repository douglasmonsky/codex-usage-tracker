"""Report-pack payload helpers for the local dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from codex_usage_tracker.reports.api import (
    QUERY_CREDIT_CONFIDENCE_CHOICES,
    QUERY_PRICING_STATUS_CHOICES,
)
from codex_usage_tracker.server.utils import (
    first_query_value,
    optional_choice_filter,
    parse_report_limit,
)

LiveQueryParams = Callable[..., dict[str, Any]]
LiveCallRows = Callable[..., tuple[list[dict[str, Any]], int]]
ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_reports_pack_request(
    query: str,
    *,
    live_query_params: LiveQueryParams,
    live_call_rows: LiveCallRows,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle aggregate report-pack route errors and response writing."""
    try:
        payload = reports_pack_payload(
            query,
            live_query_params=live_query_params,
            live_call_rows=live_call_rows,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while building report pack", exc)
        return
    send_json(HTTPStatus.OK, payload)


def reports_pack_payload(
    query: str,
    *,
    live_query_params: LiveQueryParams,
    live_call_rows: LiveCallRows,
) -> dict[str, object]:
    """Build an aggregate-only report pack from live dashboard rows."""
    params = parse_qs(query)
    query_params = live_query_params(params)
    pricing_status = optional_choice_filter(
        first_query_value(params.get("pricing_status")),
        QUERY_PRICING_STATUS_CHOICES,
        "pricing_status",
    )
    credit_confidence = optional_choice_filter(
        first_query_value(params.get("credit_confidence")),
        QUERY_CREDIT_CONFIDENCE_CHOICES,
        "credit_confidence",
    )
    evidence_limit = min(parse_report_limit(first_query_value(params.get("evidence_limit")), 8), 50)
    rows, total_matched = live_call_rows(
        query_params=query_params,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    reports = _report_summaries(rows)
    return {
        "schema": "codex-usage-tracker-reports-pack-v1",
        "reports": reports,
        "evidence": {
            str(report["key"]): _report_evidence_payload(str(report["key"]), rows, evidence_limit)
            for report in reports
        },
        "row_count": len(rows),
        "total_matched_rows": total_matched,
        "limit": query_params["limit"],
        "offset": query_params["offset"],
        "filters": {
            **query_params["filters"],
            "pricing_status": pricing_status,
            "credit_confidence": credit_confidence,
        },
        "raw_context_included": False,
    }


def _report_summaries(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    if not rows:
        return []
    reports: list[dict[str, object]] = [
        {
            "key": "cost-curves",
            "title": "Cost Curves",
            "status": "Ready",
            "owner": "Threads",
            "description": "Estimated cost concentration by loaded aggregate thread.",
        },
        {
            "key": "usage-drain-model",
            "title": "Usage Drain Model",
            "status": "Ready",
            "owner": "Reports",
            "description": "Highest estimated credit-impact calls from loaded aggregate rows.",
        },
    ]
    if any(_is_fast_candidate(row) for row in rows):
        reports.append(
            {
                "key": "fast-mode-proxy",
                "title": "Fast Mode Proxy",
                "status": "Ready",
                "owner": "Calls",
                "description": "Low-effort and fast-call candidates inferred from aggregate rows.",
            }
        )
    return reports


def _report_evidence_payload(
    report_key: str,
    rows: list[dict[str, Any]],
    evidence_limit: int,
) -> dict[str, object]:
    evidence_rows = _report_evidence_rows(report_key, rows, evidence_limit)
    return {
        "report_key": report_key,
        "rows": evidence_rows,
        "row_count": len(evidence_rows),
        "limit": evidence_limit,
        "raw_context_included": False,
    }


def _report_evidence_rows(
    report_key: str,
    rows: list[dict[str, Any]],
    evidence_limit: int,
) -> list[dict[str, Any]]:
    if report_key == "fast-mode-proxy":
        return sorted(
            [row for row in rows if _is_fast_candidate(row)],
            key=lambda row: (
                _duration_seconds(row),
                -_usage_credits(row),
                -_number(row, "total_tokens"),
            ),
        )[:evidence_limit]
    if report_key == "cost-curves":
        return sorted(
            rows,
            key=lambda row: (-_number(row, "estimated_cost_usd"), -_number(row, "total_tokens")),
        )[:evidence_limit]
    return sorted(rows, key=lambda row: (-_usage_credits(row), -_number(row, "total_tokens")))[
        :evidence_limit
    ]


def _is_fast_candidate(row: dict[str, Any]) -> bool:
    effort = str(row.get("effort") or "").lower()
    return bool(row.get("fast")) or effort == "low"


def _usage_credits(row: dict[str, Any]) -> float:
    credits = _number(row, "usage_credits")
    return credits if credits > 0 else _number(row, "estimated_cost_usd") * 25


def _duration_seconds(row: dict[str, Any]) -> float:
    duration = _number(row, "duration_seconds") or _number(row, "call_duration_seconds")
    return duration if duration > 0 else float("inf")


def _number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0
