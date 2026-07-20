"""Status payload helpers for the dashboard server."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.core.conversational_readiness import conversational_readiness
from codex_usage_tracker.server.utils import (
    first_query_value,
    parse_bool_query_value,
    safe_int,
)
from codex_usage_tracker.store.api import (
    query_latest_observed_usage,
    query_usage_status,
    refresh_metadata,
)
from codex_usage_tracker.store.dedupe_queries import query_dedupe_diagnostics

ExceptionSender = Callable[[str, BaseException], None]
JsonSender = Callable[[HTTPStatus, dict[str, object]], None]


def handle_readiness_request(*, codex_home: Path, send_json: JsonSender) -> None:
    """Return MCP conversational readiness without querying usage data."""
    send_json(HTTPStatus.OK, dict(conversational_readiness(codex_home=codex_home)))


def handle_status_request(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    include_archived_default: bool,
    send_exception: ExceptionSender,
    send_json: JsonSender,
) -> None:
    """Handle status route errors and response writing."""
    try:
        payload = status_payload(
            query,
            codex_home=codex_home,
            db_path=db_path,
            include_archived_default=include_archived_default,
        )
    except sqlite3.Error as exc:
        send_exception("Database error while reading status", exc)
        return
    send_json(HTTPStatus.OK, payload)


def status_payload(
    query: str,
    *,
    codex_home: Path,
    db_path: Path,
    include_archived_default: bool,
) -> dict[str, object]:
    """Build the live status API payload."""
    params = parse_qs(query)
    include_archived = parse_bool_query_value(
        first_query_value(params.get("include_archived")),
        include_archived_default,
    )
    counts = query_usage_status(
        db_path=db_path,
        include_archived=include_archived,
    )
    observed_usage = query_latest_observed_usage(
        db_path=db_path,
        include_archived=include_archived,
    )
    dedupe = query_dedupe_diagnostics(db_path=db_path, limit=0)["summary"]
    metadata = refresh_metadata(db_path)
    parser_diagnostics = {
        key.removeprefix("parser_"): safe_int(value)
        for key, value in metadata.items()
        if key.startswith("parser_") and safe_int(value)
    }
    return {
        "schema": "codex-usage-tracker-status-v1",
        "payload_schema": "codex-usage-tracker-live-api-v1",
        "latest_refresh_at": metadata.get("latest_refresh_at"),
        "include_archived": include_archived,
        "row_counts": counts,
        "max_event_timestamp": counts.get("max_event_timestamp"),
        "observed_usage": observed_usage,
        "dedupe": dedupe,
        "parser_adapter": metadata.get("parser_adapter"),
        "parser_diagnostics": parser_diagnostics,
        "conversational_analysis": conversational_readiness(codex_home=codex_home),
    }
