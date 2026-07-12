"""Schema objects owned by the Compression Lab repository."""

from __future__ import annotations

import sqlite3


def create_compression_run_tables(conn: sqlite3.Connection) -> None:
    """Create persistent run, candidate, and component-claim tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS compression_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            detector_set_version TEXT NOT NULL,
            estimator_version TEXT NOT NULL,
            compression_schema_version INTEGER NOT NULL,
            scope_json TEXT NOT NULL,
            filters_json TEXT NOT NULL DEFAULT '{}',
            coverage_json TEXT NOT NULL DEFAULT '{}',
            progress_percent REAL NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'pending',
            current_detector TEXT,
            completed_detectors INTEGER NOT NULL DEFAULT 0,
            total_detectors INTEGER NOT NULL DEFAULT 0,
            records_examined INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            cache_reused INTEGER NOT NULL DEFAULT 0,
            timing_json TEXT NOT NULL DEFAULT '{}',
            error_summary_json TEXT NOT NULL DEFAULT '{}',
            aggregate_profile_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            last_accessed_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_compression_runs_cache_lookup
        ON compression_runs(
            source_revision,
            scope_hash,
            detector_set_version,
            estimator_version,
            compression_schema_version,
            status,
            completed_at DESC
        );

        CREATE INDEX IF NOT EXISTS idx_compression_runs_last_accessed
        ON compression_runs(last_accessed_at);

        CREATE TABLE IF NOT EXISTS compression_candidates (
            candidate_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            family TEXT NOT NULL,
            pattern TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            rank INTEGER NOT NULL,
            confidence_grade TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            observation_count INTEGER NOT NULL,
            observed_exposure_tokens INTEGER NOT NULL,
            observed_exposure_json TEXT NOT NULL,
            gross_low INTEGER NOT NULL,
            gross_likely INTEGER NOT NULL,
            gross_high INTEGER NOT NULL,
            adjusted_low INTEGER NOT NULL,
            adjusted_likely INTEGER NOT NULL,
            adjusted_high INTEGER NOT NULL,
            detector_version TEXT NOT NULL,
            estimator_version TEXT NOT NULL,
            estimator_tier TEXT NOT NULL,
            estimator_name TEXT NOT NULL,
            confidence_reasons_json TEXT NOT NULL,
            estimator_assumptions_json TEXT NOT NULL,
            evidence_handles_json TEXT NOT NULL,
            intervention_json TEXT NOT NULL,
            verification_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            overlaps_json TEXT NOT NULL,
            thread_keys_json TEXT NOT NULL,
            first_seen TEXT,
            last_seen TEXT,
            FOREIGN KEY(run_id) REFERENCES compression_runs(run_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_rank
        ON compression_candidates(run_id, rank, candidate_id);

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_family_savings
        ON compression_candidates(run_id, family, adjusted_likely DESC);

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_confidence
        ON compression_candidates(run_id, confidence_grade, confidence_score DESC);

        CREATE TABLE IF NOT EXISTS compression_candidate_records (
            candidate_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            component TEXT NOT NULL,
            exposure_tokens INTEGER NOT NULL,
            estimate_low INTEGER NOT NULL,
            estimate_likely INTEGER NOT NULL,
            estimate_high INTEGER NOT NULL,
            evidence_role TEXT NOT NULL,
            trace_handle_json TEXT NOT NULL,
            PRIMARY KEY(candidate_id, record_id, component),
            FOREIGN KEY(candidate_id)
                REFERENCES compression_candidates(candidate_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_compression_candidate_records_record
        ON compression_candidate_records(record_id, component);
        """
    )
