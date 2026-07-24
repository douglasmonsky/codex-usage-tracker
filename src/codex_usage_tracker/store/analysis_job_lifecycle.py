"""Lifecycle and retention policy for persisted analysis jobs."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_usage_tracker.store.analysis_job_codec import _json_load, _timestamp
from codex_usage_tracker.store.connection import open_read_only_connection

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "interrupted")
STATUSES = (*ACTIVE_STATUSES, *TERMINAL_STATUSES)
PROGRESS_KEYS = frozenset({"percent", "stage"})
ERROR_KEYS = frozenset({"code", "severity", "message", "remediation"})
REQUEST_ROOT_KEYS = {
    "analysis.request.v1": frozenset(
        {
            "goal",
            "filters",
            "history",
            "evidence_limit",
            "comparison",
            "execution",
        }
    ),
    "allowance-analysis.request.v1": frozenset(
        {
            "snapshot_id",
            "source_revision",
            "model_version",
            "rate_card_revision",
            "data_as_of",
            "parameters",
        }
    ),
}
RESULT_ROOT_KEYS = {
    "codex-usage-tracker.analysis.v2": frozenset(
        {
            "schema",
            "analysis_id",
            "goal",
            "summary",
            "findings",
            "evidence",
            "methodology",
            "suggested_questions",
            "strategy_id",
            "strategy_version",
            "source_revision",
            "accounting",
            "messages",
            "limitations",
            "dashboard_destinations",
        }
    )
}


def lease_expired(row: sqlite3.Row, current: datetime) -> bool:
    """Return whether a persisted lease is missing, malformed, or expired."""
    try:
        expires_at = datetime.fromisoformat(str(row["lease_expires_at"]).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        return True
    return expires_at.astimezone(timezone.utc) <= current


def can_transition(current: str, target: str) -> bool:
    """Allow only monotonic active-to-active or active-to-terminal transitions."""
    if current == "queued":
        return target in {"queued", "running", "completed", "failed", "cancelled"}
    if current == "running":
        return target in {"running", "completed", "failed", "cancelled"}
    return False


def monotonic_progress(
    current: sqlite3.Row,
    candidate: Mapping[str, object],
) -> Mapping[str, object]:
    """Keep stored progress when a late checkpoint reports a lower percent."""
    stored = _json_load(current["progress_json"])
    stored_mapping = stored if isinstance(stored, Mapping) else {}
    stored_percent = stored_mapping.get("percent", 0)
    candidate_percent = candidate.get("percent", 0)
    if (
        type(stored_percent) is int
        and type(candidate_percent) is int
        and candidate_percent < stored_percent
    ):
        return stored_mapping
    return candidate


def prune_in_connection(
    conn: sqlite3.Connection,
    *,
    current: datetime,
    terminal_retention: timedelta,
    max_terminal_jobs: int,
) -> int:
    """Prune terminal rows and update the cumulative counter transactionally."""
    cutoff = _timestamp(current - terminal_retention)
    old = conn.execute(
        """
        DELETE FROM analysis_jobs
        WHERE status IN ('completed', 'failed', 'cancelled', 'interrupted')
          AND last_accessed_at < ?
        """,
        (cutoff,),
    ).rowcount
    excess = conn.execute(
        """
        DELETE FROM analysis_jobs
        WHERE job_id IN (
            SELECT job_id
            FROM analysis_jobs
            WHERE status IN ('completed', 'failed', 'cancelled', 'interrupted')
            ORDER BY last_accessed_at DESC, job_id DESC
            LIMIT -1 OFFSET ?
        )
        """,
        (max_terminal_jobs,),
    ).rowcount
    pruned = max(0, int(old)) + max(0, int(excess))
    if pruned:
        conn.execute(
            """
            INSERT INTO analysis_job_stats (key, value)
            VALUES ('pruned_total', ?)
            ON CONFLICT(key) DO UPDATE SET value = value + excluded.value
            """,
            (pruned,),
        )
    return pruned


def job_counts(db_path: Path) -> dict[str, int]:
    """Return bounded lifecycle counts without initializing or mutating the store."""
    counts = {
        "active": 0,
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "interrupted": 0,
        "pruned": 0,
    }
    if not db_path.is_file():
        return counts
    conn = open_read_only_connection(db_path)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'analysis_jobs'"
        ).fetchone()
        if table is None:
            return counts
        for row in conn.execute(
            "SELECT status, COUNT(*) AS count FROM analysis_jobs GROUP BY status"
        ):
            status = str(row["status"])
            if status in counts:
                counts[status] = int(row["count"])
            elif status == "cancelled":
                counts["failed"] += int(row["count"])
        pruned = conn.execute(
            "SELECT value FROM analysis_job_stats WHERE key = 'pruned_total'"
        ).fetchone()
        if pruned is not None:
            counts["pruned"] = int(pruned["value"])
    finally:
        conn.close()
    counts["active"] = counts["queued"] + counts["running"]
    return counts
