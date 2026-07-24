"""Schema migration for durable generic analysis jobs."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.connection import execute_script

MIGRATION_VERSION = 36
MIGRATION_NAME = "persisted generic analysis jobs"
LEASE_MIGRATION_VERSION = 37
LEASE_MIGRATION_NAME = "lease persisted generic analysis jobs"


def create_analysis_jobs_table(conn: sqlite3.Connection) -> None:
    """Create bounded generic job storage and semantic lookup indexes."""
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS analysis_jobs (
            job_id TEXT PRIMARY KEY,
            job_kind TEXT NOT NULL,
            semantic_key TEXT NOT NULL,
            status TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            request_schema TEXT NOT NULL,
            request_json TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            result_schema TEXT,
            result_json TEXT,
            error_json TEXT,
            owner_id TEXT NOT NULL,
            lease_expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT NOT NULL,
            CHECK (
                status IN (
                    'queued',
                    'running',
                    'completed',
                    'failed',
                    'cancelled',
                    'interrupted'
                )
            )
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_jobs_active_semantic
        ON analysis_jobs(job_kind, semantic_key)
        WHERE status IN ('queued', 'running');

        CREATE INDEX IF NOT EXISTS idx_analysis_jobs_reusable
        ON analysis_jobs(
            job_kind,
            semantic_key,
            source_revision,
            result_schema,
            status,
            completed_at DESC
        );

        CREATE INDEX IF NOT EXISTS idx_analysis_jobs_retention
        ON analysis_jobs(status, last_accessed_at DESC);

        CREATE TABLE IF NOT EXISTS analysis_job_stats (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
        """,
    )


def add_analysis_job_leases(conn: sqlite3.Connection) -> None:
    """Upgrade early pre-release job tables with expired legacy leases."""
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(analysis_jobs)")}
    if "owner_id" not in columns:
        conn.execute(
            "ALTER TABLE analysis_jobs ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'legacy:prelease'"
        )
    if "lease_expires_at" not in columns:
        conn.execute(
            "ALTER TABLE analysis_jobs "
            "ADD COLUMN lease_expires_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'"
        )
