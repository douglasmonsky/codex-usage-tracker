"""Call-list payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from codex_usage_tracker.reports import (
    QUERY_CREDIT_CONFIDENCE_CHOICES,
    QUERY_PRICING_STATUS_CHOICES,
)
from codex_usage_tracker.server_utils import (
    first_query_value,
    has_more_rows,
    next_row_offset,
    optional_choice_filter,
)

LiveQueryParams = Callable[..., dict[str, Any]]
LiveCallRows = Callable[..., tuple[list[dict[str, object]], int]]
ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


class MissingThreadKeyError(ValueError):
    """Raised when a thread-calls request omits a thread key."""


def handle_calls_request(
    query: str,
    *,
    live_query_params: LiveQueryParams,
    live_call_rows: LiveCallRows,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle call-list route errors and response writing."""
    try:
        payload = calls_payload(
            query,
            live_query_params=live_query_params,
            live_call_rows=live_call_rows,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading calls", exc)
        return
    send_json(HTTPStatus.OK, payload)


def calls_payload(
    query: str,
    *,
    live_query_params: LiveQueryParams,
    live_call_rows: LiveCallRows,
) -> dict[str, object]:
    """Build the filtered calls API payload."""
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
    rows, total_matched = live_call_rows(
        query_params=query_params,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
    )
    return _calls_payload(
        schema="codex-usage-tracker-calls-v1",
        rows=rows,
        total_matched=total_matched,
        query_params=query_params,
        filters={
            **query_params["filters"],
            "pricing_status": pricing_status,
            "credit_confidence": credit_confidence,
        },
    )


def thread_calls_payload(
    query: str,
    *,
    live_query_params: LiveQueryParams,
    live_call_rows: LiveCallRows,
) -> dict[str, object]:
    """Build the thread-scoped calls API payload."""
    params = parse_qs(query)
    thread_key = first_query_value(params.get("thread_key")) or first_query_value(params.get("thread"))
    if not thread_key:
        raise MissingThreadKeyError("thread_key required")
    query_params = live_query_params(params, thread_key=thread_key)
    rows, total_matched = live_call_rows(
        query_params=query_params,
        pricing_status=None,
        credit_confidence=None,
    )
    payload = _calls_payload(
        schema="codex-usage-tracker-thread-calls-v1",
        rows=rows,
        total_matched=total_matched,
        query_params=query_params,
    )
    payload["thread_key"] = thread_key
    return payload


def _calls_payload(
    *,
    schema: str,
    rows: list[dict[str, object]],
    total_matched: int,
    query_params: dict[str, Any],
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
    limit = query_params["limit"]
    offset = query_params["offset"]
    payload = {
        "schema": schema,
        "rows": rows,
        "row_count": len(rows),
        "total_matched_rows": total_matched,
        "limit": limit,
        "offset": offset,
        "has_more": has_more_rows(limit, offset, len(rows), total_matched),
        "next_offset": next_row_offset(limit, offset, len(rows), total_matched),
        "raw_context_included": False,
    }
    if filters is not None:
        payload["filters"] = filters
    return payload
