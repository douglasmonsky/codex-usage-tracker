"""Thread-list payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_api_limit,
    parse_api_offset,
    parse_bool_query_value,
)
from codex_usage_tracker.store.api import query_thread_summaries

ErrorSender = Callable[[HTTPStatus, str], None]
ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_threads_request(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
    send_error: ErrorSender,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle thread-list route errors and response writing."""
    try:
        payload = threads_payload(
            query,
            db_path=db_path,
            include_archived_default=include_archived_default,
        )
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    except sqlite3.Error as exc:
        send_exception("Database error while reading threads", exc)
        return
    send_json(HTTPStatus.OK, payload)


def threads_payload(
    query: str,
    *,
    db_path: Path,
    include_archived_default: bool,
) -> dict[str, object]:
    """Build the thread-list API payload."""
    params = parse_qs(query)
    limit = parse_api_limit(first_query_value(params.get("limit")), 100)
    offset = parse_api_offset(first_query_value(params.get("offset")))
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    rows = query_thread_summaries(
        db_path=db_path,
        limit=limit,
        offset=offset,
        search=first_query_value(params.get("q")) or first_query_value(params.get("search")),
        include_archived=include_archived,
        sort=first_query_value(params.get("sort")) or "tokens",
        direction=first_query_value(params.get("direction")) or "desc",
    )
    return {
        "schema": "codex-usage-tracker-threads-v1",
        "rows": rows,
        "row_count": len(rows),
        "limit": limit,
        "offset": offset,
        "include_archived": include_archived,
        "raw_context_included": False,
    }
