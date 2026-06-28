"""Thread-list payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.server_utils import (
    first_query_value,
    parse_api_limit,
    parse_api_offset,
    parse_bool_query_value,
)
from codex_usage_tracker.store import query_thread_summaries


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
