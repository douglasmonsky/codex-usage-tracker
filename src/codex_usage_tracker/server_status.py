"""Status payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.server_utils import (
    first_query_value,
    parse_bool_query_value,
    safe_int,
)
from codex_usage_tracker.store import (
    query_latest_observed_usage,
    query_usage_status,
    refresh_metadata,
)


def status_payload(
    query: str,
    *,
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
        "parser_adapter": metadata.get("parser_adapter"),
        "parser_diagnostics": parser_diagnostics,
    }
