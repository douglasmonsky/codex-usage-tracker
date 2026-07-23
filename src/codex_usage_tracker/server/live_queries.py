"""Live dashboard API query helpers."""

from __future__ import annotations

from typing import Any

import codex_usage_tracker.server.utils as server_utils


def live_query_params(
    params: dict[str, list[str]],
    *,
    include_archived_default: bool,
    thread_key: str | None = None,
) -> dict[str, Any]:
    """Normalize live usage API query parameters for store queries and payload filters."""
    first = server_utils.first_query_value
    include_archived = server_utils.parse_bool_query_value(
        first(params.get("include_archived")),
        include_archived_default,
    )
    search = first(params.get("q")) or first(params.get("search"))
    thread = first(params.get("thread")) if thread_key is None else None
    sort = first(params.get("sort")) or "time"
    direction = first(params.get("direction")) or "desc"
    filters = {
        "q": search,
        "since": first(params.get("since")),
        "until": first(params.get("until")),
        "model": first(params.get("model")),
        "effort": first(params.get("effort")),
        "source": first(params.get("source")),
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
        "sort": sort,
        "direction": direction,
    }
    return {
        "limit": server_utils.parse_api_limit(first(params.get("limit")), 100),
        "offset": server_utils.parse_api_offset(first(params.get("offset"))),
        "search": search,
        "since": filters["since"],
        "until": filters["until"],
        "model": filters["model"],
        "effort": filters["effort"],
        "source": filters["source"],
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
        "sort": sort,
        "direction": direction,
        "filters": filters,
    }
