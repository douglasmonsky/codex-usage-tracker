"""Usage dashboard refresh helpers."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.server_utils import elapsed_ms
from codex_usage_tracker.store import refresh_usage_index


def refresh_usage_payload(
    *,
    codex_home: Path,
    db_path: Path,
    include_archived: bool,
    refresh_lock: Any,
) -> tuple[dict[str, object], float]:
    """Refresh the usage index and return the live API refresh payload."""
    refresh_started = perf_counter()
    with refresh_lock:
        result = refresh_usage_index(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=include_archived,
        )
    return (
        {
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "skipped_events": result.skipped_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "db_path": result.db_path,
            "parser_diagnostics": result.parser_diagnostics,
            "include_archived": include_archived,
        },
        elapsed_ms(refresh_started),
    )
