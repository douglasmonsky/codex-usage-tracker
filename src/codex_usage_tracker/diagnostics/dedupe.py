"""Public deduplication diagnostic contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.dedupe_queries import query_dedupe_diagnostics


def build_dedupe_diagnostics(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    limit: int = 100,
) -> dict[str, Any]:
    """Build the shared CLI, HTTP, dashboard, and MCP dedupe payload."""

    return query_dedupe_diagnostics(db_path=db_path, limit=limit)


def render_dedupe_diagnostics(payload: dict[str, Any]) -> str:
    """Render a concise human-readable dedupe summary."""

    summary = payload["summary"]
    return "\n".join(
        (
            "Usage deduplication: enabled",
            f"Canonical billable rows: {summary['canonical_rows']}",
            f"Physical source rows: {summary['physical_rows']}",
            f"Copied clone rows excluded: {summary['excluded_copied_rows']}",
            f"Tokens excluded: {summary['excluded_total_tokens']}",
            f"Fingerprint version: {summary['fingerprint_version']}",
        )
    )
