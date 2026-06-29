"""Lazy raw-context loading for one aggregate usage record."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.context.constants import (
    CONTEXT_MODE_FULL,
    CONTEXT_MODE_QUICK,
    CONTEXT_MODES,
    DEFAULT_CONTEXT_CHARS,
    DEFAULT_CONTEXT_ENTRIES,
)
from codex_usage_tracker.context.loader import (
    attach_context_diagnostics,
    context_response_payload,
    context_source_location,
    load_context_usage_record,
)
from codex_usage_tracker.context.reader import (
    _normalize_context_mode,
    _read_context_for_usage_record,
)
from codex_usage_tracker.context.token_estimates import (
    estimate_visible_tokens,
)
from codex_usage_tracker.context.values import (
    optional_str,
)
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH

__all__ = (
    "CONTEXT_MODE_FULL",
    "CONTEXT_MODE_QUICK",
    "CONTEXT_MODES",
    "DEFAULT_CONTEXT_CHARS",
    "DEFAULT_CONTEXT_ENTRIES",
    "load_call_context",
)


def load_call_context(
    record_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
    include_compaction_history: bool = False,
    diagnostics: bool = False,
    mode: str = CONTEXT_MODE_QUICK,
) -> dict[str, Any]:
    """Load logged turn context for one model call from its source JSONL file.

    This intentionally reads raw transcript-like content only on demand. The returned
    context is not written back to SQLite or embedded in the dashboard HTML.
    """

    context_mode = _normalize_context_mode(mode)
    diagnostic_payload: dict[str, Any] | None = {} if diagnostics else None
    row = load_context_usage_record(
        db_path=db_path,
        record_id=record_id,
        diagnostic_payload=diagnostic_payload,
    )
    source_file, source_file_bytes, line_number = context_source_location(
        row, record_id=record_id
    )
    loaded = _read_context_for_usage_record(
        row=row,
        source_file=source_file,
        line_number=line_number,
        max_chars=max_chars,
        max_entries=max_entries,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        context_mode=context_mode,
    )
    visible_estimate = estimate_visible_tokens(
        loaded.estimate_entries, optional_str(row.get("model"))
    )
    payload = context_response_payload(
        row=row,
        source_file=source_file,
        line_number=line_number,
        context_mode=context_mode,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
        visible_estimate=visible_estimate,
        loaded=loaded,
    )
    attach_context_diagnostics(
        payload=payload,
        diagnostic_payload=diagnostic_payload,
        loaded=loaded,
        source_file_bytes=source_file_bytes,
        line_number=line_number,
    )
    return payload
