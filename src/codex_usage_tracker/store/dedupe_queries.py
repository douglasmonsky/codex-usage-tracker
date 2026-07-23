"""Read-only diagnostics for canonical usage deduplication."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.core.usage_identity import FINGERPRINT_VERSION
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

_MAX_DIAGNOSTIC_ROWS = 1_000


def query_dedupe_counts(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Return canonical accounting counts without hydrating token columns."""

    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS physical_rows,
                coalesce(SUM(is_duplicate), 0) AS excluded_copied_rows
            FROM usage_events INDEXED BY idx_usage_duplicate_reason
            """
        ).fetchone()
    physical_rows = int(row["physical_rows"] if row is not None else 0)
    excluded_copied_rows = int(
        row["excluded_copied_rows"] if row is not None else 0
    )
    return {
        "physical_rows": physical_rows,
        "canonical_rows": physical_rows - excluded_copied_rows,
        "excluded_copied_rows": excluded_copied_rows,
    }


def query_dedupe_diagnostics(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Return aggregate dedupe status and bounded physical duplicate provenance."""

    normalized_limit = min(max(int(limit), 0), _MAX_DIAGNOSTIC_ROWS)
    with connect(db_path) as conn:
        init_db(conn)
        totals = row_to_dict(
            conn.execute(
                """
                SELECT
                    COUNT(*) AS physical_rows,
                    coalesce(SUM(CASE WHEN is_duplicate = 0 THEN 1 ELSE 0 END), 0)
                        AS canonical_rows,
                    coalesce(SUM(is_duplicate), 0) AS excluded_copied_rows,
                    COUNT(DISTINCT CASE WHEN is_duplicate = 1 THEN usage_fingerprint END)
                        AS duplicate_fingerprint_groups,
                    coalesce(SUM(total_tokens), 0) AS physical_total_tokens,
                    coalesce(SUM(CASE WHEN is_duplicate = 1 THEN total_tokens ELSE 0 END), 0)
                        AS excluded_total_tokens,
                    coalesce(SUM(CASE WHEN is_duplicate = 0 THEN total_tokens ELSE 0 END), 0)
                        AS canonical_total_tokens
                FROM usage_events
                """
            ).fetchone()
        )
        reasons = {
            str(row["duplicate_reason"]): int(row["row_count"])
            for row in conn.execute(
                """
                SELECT duplicate_reason, COUNT(*) AS row_count
                FROM usage_events
                WHERE is_duplicate = 1 AND duplicate_reason IS NOT NULL
                GROUP BY duplicate_reason
                ORDER BY duplicate_reason
                """
            )
        }
        rows = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT
                    duplicate.record_id,
                    duplicate.canonical_record_id,
                    (
                        SELECT canonical.record_id
                        FROM usage_events AS canonical
                        WHERE canonical.usage_fingerprint = duplicate.usage_fingerprint
                          AND canonical.is_duplicate = 0
                        ORDER BY canonical.event_timestamp, canonical.source_file,
                            canonical.line_number, canonical.record_id
                        LIMIT 1
                    ) AS duplicate_of_record_id,
                    duplicate.usage_fingerprint,
                    duplicate.duplicate_reason,
                    duplicate.source_file,
                    duplicate.line_number,
                    duplicate.session_id,
                    duplicate.turn_id,
                    duplicate.turn_timestamp,
                    duplicate.event_timestamp,
                    duplicate.model,
                    duplicate.effort,
                    duplicate.input_tokens,
                    duplicate.cached_input_tokens,
                    duplicate.output_tokens,
                    duplicate.reasoning_output_tokens,
                    duplicate.total_tokens,
                    duplicate.cumulative_input_tokens,
                    duplicate.cumulative_cached_input_tokens,
                    duplicate.cumulative_output_tokens,
                    duplicate.cumulative_reasoning_output_tokens,
                    duplicate.cumulative_total_tokens
                FROM usage_events AS duplicate
                WHERE duplicate.is_duplicate = 1
                ORDER BY duplicate.event_timestamp DESC, duplicate.source_file,
                    duplicate.line_number, duplicate.record_id
                LIMIT ?
                """,
                (normalized_limit,),
            )
        ]
    summary = {
        "dedupe_enabled": True,
        "fingerprint_version": FINGERPRINT_VERSION,
        **{key: int(value or 0) for key, value in totals.items()},
        "duplicate_reasons": reasons,
    }
    return {
        "schema": "codex-usage-tracker-dedupe-diagnostics-v1",
        "summary": summary,
        "row_count": len(rows),
        "limit": normalized_limit,
        "truncated": summary["excluded_copied_rows"] > len(rows),
        "rows": rows,
        "provenance": {
            "physical_rows_preserved": True,
            "raw_content_included": False,
        },
    }
