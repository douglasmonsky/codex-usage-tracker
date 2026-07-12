"""Persist bounded metadata for local investigation runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def create_investigation_run_tables(conn: sqlite3.Connection) -> None:
    """Create the bounded investigation-run summary table."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS investigation_runs (
            run_key TEXT PRIMARY KEY,
            run_kind TEXT NOT NULL,
            question TEXT NOT NULL DEFAULT '',
            payload_schema TEXT NOT NULL,
            content_mode TEXT NOT NULL,
            includes_indexed_content INTEGER NOT NULL DEFAULT 0,
            includes_raw_fragments INTEGER NOT NULL DEFAULT 0,
            privacy_mode TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}',
            branch_count INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_investigation_runs_kind_created
        ON investigation_runs(run_kind, created_at);
        """
    )


def insert_investigation_run(
    conn: sqlite3.Connection,
    *,
    run_kind: str,
    payload: dict[str, Any],
) -> str:
    """Record a share-safe run summary and return its key."""

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    schema = str(payload.get("schema") or "")
    question = str(payload.get("question") or "")
    summary_value = payload.get("summary")
    summary = summary_value if isinstance(summary_value, dict) else {}
    branches_value = payload.get("branches")
    branches = branches_value if isinstance(branches_value, list) else []
    run_key = _stable_hash(f"{run_kind}:{schema}:{question}:{created_at}")
    conn.execute(
        """
        INSERT INTO investigation_runs (
            run_key,
            run_kind,
            question,
            payload_schema,
            content_mode,
            includes_indexed_content,
            includes_raw_fragments,
            privacy_mode,
            summary_json,
            branch_count,
            evidence_count,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_key) DO UPDATE SET
            run_kind=excluded.run_kind,
            question=excluded.question,
            payload_schema=excluded.payload_schema,
            content_mode=excluded.content_mode,
            includes_indexed_content=excluded.includes_indexed_content,
            includes_raw_fragments=excluded.includes_raw_fragments,
            privacy_mode=excluded.privacy_mode,
            summary_json=excluded.summary_json,
            branch_count=excluded.branch_count,
            evidence_count=excluded.evidence_count,
            created_at=excluded.created_at
        """,
        (
            run_key,
            run_kind,
            question,
            schema,
            str(payload.get("content_mode") or ""),
            int(bool(payload.get("includes_indexed_content"))),
            int(bool(payload.get("includes_raw_fragments"))),
            str(payload.get("privacy_mode") or ""),
            json.dumps(summary, sort_keys=True, separators=(",", ":")),
            len(branches),
            _evidence_count(branches),
            created_at,
        ),
    )
    return run_key


def _evidence_count(branches: list[object]) -> int:
    total = 0
    for branch in branches:
        if isinstance(branch, dict):
            value = branch.get("evidence_count")
            if isinstance(value, bool):
                total += int(value)
            elif isinstance(value, int):
                total += value
            elif isinstance(value, str):
                try:
                    total += int(value)
                except ValueError:
                    continue
    return total


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
