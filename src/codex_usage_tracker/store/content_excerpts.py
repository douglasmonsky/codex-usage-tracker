"""Explicit bounded local-content excerpts for selected evidence records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def list_content_excerpts(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    record_ids: list[str],
    limit: int,
    max_excerpt_chars: int,
) -> list[dict[str, Any]]:
    """Return raw local excerpts only for an explicit bounded request."""
    normalized_ids = sorted({str(value) for value in record_ids if value})
    normalized_limit = min(50, max(1, int(limit)))
    normalized_chars = min(2000, max(32, int(max_excerpt_chars)))
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _value in normalized_ids)
    query = "\n".join(
        (
            "SELECT fragment_id, record_id, turn_key, fragment_kind, role, safe_label,",
            "       content_hash, content_size_bytes, fragment_text,",
            "       includes_raw_fragment, line_start, line_end",
            "FROM content_fragments",
            "WHERE record_id IN (",
            placeholders,
            ") AND fragment_text != ''",
            "ORDER BY record_id, COALESCE(line_start, 0), fragment_id",
            "LIMIT ?",
        )
    )
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            query,
            [*normalized_ids, normalized_limit],
        ).fetchall()
    return [_excerpt_row(row, normalized_chars) for row in rows]


def _excerpt_row(row: Any, max_chars: int) -> dict[str, Any]:
    text = str(row["fragment_text"] or "")
    return {
        "fragment_id": row["fragment_id"],
        "record_id": row["record_id"],
        "turn_key": row["turn_key"],
        "fragment_kind": row["fragment_kind"],
        "role": row["role"],
        "safe_label": row["safe_label"],
        "content_hash": row["content_hash"],
        "content_size_bytes": int(row["content_size_bytes"] or 0),
        "excerpt": text[:max_chars],
        "excerpt_truncated": len(text) > max_chars,
        "includes_raw_fragment": bool(row["includes_raw_fragment"]),
        "line_start": row["line_start"],
        "line_end": row["line_end"],
    }
