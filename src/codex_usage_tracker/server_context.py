"""Raw context payload helpers for the dashboard server."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from codex_usage_tracker.context import (
    CONTEXT_MODE_QUICK,
    CONTEXT_MODES,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
from codex_usage_tracker.server_utils import (
    first_query_value,
    parse_bool_query_value,
    parse_context_limit,
    truthy_query_value,
)


class ContextRequestError(ValueError):
    """Raised for invalid context API request parameters."""


def context_payload(
    query: str,
    *,
    db_path: Path,
    default_context_chars: int,
) -> dict[str, object]:
    """Build the raw context API payload after auth/enable checks."""
    params = parse_qs(query)
    record_id = first_query_value(params.get("record_id"))
    if not record_id:
        raise ContextRequestError("record_id required")

    context_mode = (first_query_value(params.get("mode")) or CONTEXT_MODE_QUICK).strip().lower()
    if context_mode not in CONTEXT_MODES:
        raise ContextRequestError("mode must be one of: " + ", ".join(sorted(CONTEXT_MODES)))

    return load_call_context(
        record_id=record_id,
        db_path=db_path,
        max_chars=parse_context_limit(
            first_query_value(params.get("max_chars")),
            default_context_chars,
        ),
        max_entries=parse_context_limit(
            first_query_value(params.get("max_entries")),
            DEFAULT_CONTEXT_ENTRIES,
        ),
        include_tool_output=truthy_query_value(first_query_value(params.get("include_tool_output"))),
        include_compaction_history=truthy_query_value(
            first_query_value(params.get("include_compaction_history")),
        ),
        diagnostics=parse_bool_query_value(first_query_value(params.get("diagnostics")), False),
        mode=context_mode,
    )
