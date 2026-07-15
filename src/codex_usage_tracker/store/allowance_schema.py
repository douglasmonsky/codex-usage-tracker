"""Schema and rebuild boundary for derived allowance intelligence."""

import sqlite3

MIGRATION_NAMES = {
    27: "add allowance intelligence storage",
    28: "repair allowance intelligence query indexes",
    29: "persist allowance subscription plan provenance",
}


def migrate_allowance_intelligence_v2(conn: sqlite3.Connection) -> None:
    """Create structural storage for reset-cycle allowance analysis.

    Pricing estimates are deliberately nullable: they are materialized only by
    later analysis services that can establish their pricing provenance.
    """

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS allowance_source_state (
            state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
            allowance_generation INTEGER NOT NULL,
            source_revision TEXT NOT NULL,
            observation_count INTEGER NOT NULL,
            latest_observed_at TEXT,
            model_version TEXT NOT NULL,
            rebuilt_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS allowance_cycles (
            cycle_id TEXT PRIMARY KEY,
            window_kind TEXT NOT NULL,
            window_key TEXT NOT NULL,
            cohort_key TEXT NOT NULL,
            plan_type TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0,
            reset_at INTEGER,
            reset_lower_bound INTEGER,
            reset_upper_bound INTEGER,
            first_observed_at TEXT,
            last_observed_at TEXT,
            start_used_percent REAL,
            end_used_percent REAL,
            latest_used_percent REAL,
            peak_used_percent REAL,
            observation_count INTEGER NOT NULL DEFAULT 0,
            conflict_count INTEGER NOT NULL DEFAULT 0,
            reversal_count INTEGER NOT NULL DEFAULT 0,
            censored_interval_count INTEGER NOT NULL DEFAULT 0,
            canonical_observation_count INTEGER NOT NULL DEFAULT 0,
            canonical_tokens INTEGER NOT NULL DEFAULT 0,
            canonical_credits REAL,
            priced_credits REAL,
            unpriced_credits REAL,
            price_coverage REAL,
            quality_grade TEXT,
            status TEXT NOT NULL DEFAULT 'ambiguous',
            cycle_state TEXT NOT NULL DEFAULT 'ambiguous',
            source_revision TEXT NOT NULL,
            model_version TEXT
        );

        CREATE TABLE IF NOT EXISTS allowance_intervals (
            interval_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            window_kind TEXT NOT NULL,
            window_key TEXT NOT NULL,
            cohort_key TEXT NOT NULL,
            is_archived INTEGER NOT NULL DEFAULT 0,
            start_observation_id TEXT,
            end_observation_id TEXT,
            start_record_id TEXT,
            end_record_id TEXT,
            start_observed_at TEXT,
            end_observed_at TEXT,
            start_used_percent REAL,
            end_used_percent REAL,
            visible_percent_delta REAL,
            percent_resolution REAL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_credits REAL,
            price_coverage REAL,
            confidence REAL,
            confidence_mix TEXT,
            point_kind TEXT NOT NULL,
            interval_kind TEXT,
            censor_reason TEXT,
            simultaneous_conflict_count INTEGER NOT NULL DEFAULT 0,
            explained_movement REAL,
            unexplained_movement REAL,
            eligible_for_interpolation INTEGER NOT NULL DEFAULT 0,
            eligible_for_calibration INTEGER NOT NULL DEFAULT 0,
            eligible_for_forecasting INTEGER NOT NULL DEFAULT 0,
            eligible_for_change_detection INTEGER NOT NULL DEFAULT 0,
            source_revision TEXT NOT NULL,
            model_version TEXT,
            FOREIGN KEY(cycle_id) REFERENCES allowance_cycles(cycle_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS allowance_analysis_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            source_revision TEXT NOT NULL,
            model_version TEXT NOT NULL,
            archive_scope TEXT NOT NULL,
            window_kind TEXT NOT NULL,
            cohort_key TEXT NOT NULL,
            forecast_horizon INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            result_json TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_observations_active_newest
        ON allowance_observations(event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC)
        WHERE is_archived = 0;

        CREATE INDEX IF NOT EXISTS idx_allowance_observations_active_window_newest
        ON allowance_observations(
            window_kind, event_timestamp DESC, cumulative_total_tokens DESC, window_key DESC
        ) WHERE is_archived = 0;

        DROP INDEX IF EXISTS idx_allowance_cycles_latest_cohort_window;
        DROP INDEX IF EXISTS idx_allowance_cycles_cohort_time_range;
        CREATE INDEX idx_allowance_cycles_latest_cohort_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, cohort_key,
            last_observed_at DESC, cycle_id DESC
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_cycles_latest_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, last_observed_at DESC, cycle_id DESC
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_cycles_series_cohort_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, cohort_key, first_observed_at, cycle_id
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_cycles_series_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, first_observed_at, cycle_id
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_cycles_source_revision
        ON allowance_cycles(source_revision);

        DROP INDEX IF EXISTS idx_allowance_intervals_cycle_evidence_desc;
        CREATE INDEX IF NOT EXISTS idx_allowance_intervals_evidence_cohort_window
        ON allowance_intervals(
            is_archived, source_revision, window_kind, cohort_key,
            end_observed_at DESC, interval_id DESC
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_intervals_evidence_window
        ON allowance_intervals(
            is_archived, source_revision, window_kind, end_observed_at DESC, interval_id DESC
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_intervals_source_revision
        ON allowance_intervals(source_revision);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_allowance_analysis_snapshots_cache_key
        ON allowance_analysis_snapshots(
            source_revision, model_version, archive_scope, window_kind, cohort_key, forecast_horizon
        );
        """
    )


def rebuild_allowance_intelligence(conn: sqlite3.Connection) -> None:
    """Discard derived allowance analysis after canonical usage changes."""

    if not _table_exists(conn, "allowance_source_state"):
        return
    conn.execute("DELETE FROM allowance_analysis_snapshots")
    conn.execute("DELETE FROM allowance_intervals")
    conn.execute("DELETE FROM allowance_cycles")
    conn.execute("DELETE FROM allowance_source_state")


def migrate_allowance_query_indexes_v3(conn: sqlite3.Connection) -> None:
    """Repair revision-aware allowance indexes for databases already at v26."""

    conn.executescript(
        """
        DROP INDEX IF EXISTS idx_allowance_cycles_latest_cohort_window;
        DROP INDEX IF EXISTS idx_allowance_cycles_cohort_time_range;
        DROP INDEX IF EXISTS idx_allowance_cycles_latest_window;
        DROP INDEX IF EXISTS idx_allowance_cycles_series_cohort_window;
        DROP INDEX IF EXISTS idx_allowance_cycles_series_window;
        CREATE INDEX idx_allowance_cycles_latest_cohort_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, cohort_key,
            last_observed_at DESC, cycle_id DESC
        );
        CREATE INDEX idx_allowance_cycles_latest_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, last_observed_at DESC, cycle_id DESC
        );
        CREATE INDEX idx_allowance_cycles_series_cohort_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, cohort_key, first_observed_at, cycle_id
        );
        CREATE INDEX idx_allowance_cycles_series_window
        ON allowance_cycles(
            is_archived, source_revision, window_kind, first_observed_at, cycle_id
        );

        DROP INDEX IF EXISTS idx_allowance_intervals_cycle_evidence_desc;
        DROP INDEX IF EXISTS idx_allowance_intervals_evidence_cohort_window;
        DROP INDEX IF EXISTS idx_allowance_intervals_evidence_window;
        DROP INDEX IF EXISTS idx_allowance_intervals_evidence_cohort;
        DROP INDEX IF EXISTS idx_allowance_intervals_evidence_global;
        CREATE INDEX idx_allowance_intervals_evidence_cohort_window
        ON allowance_intervals(
            is_archived, source_revision, window_kind, cohort_key,
            end_observed_at DESC, interval_id DESC
        );
        CREATE INDEX idx_allowance_intervals_evidence_window
        ON allowance_intervals(
            is_archived, source_revision, window_kind, end_observed_at DESC, interval_id DESC
        );
        CREATE INDEX idx_allowance_intervals_evidence_cohort
        ON allowance_intervals(
            is_archived, source_revision, cohort_key, end_observed_at DESC, interval_id DESC
        );
        CREATE INDEX idx_allowance_intervals_evidence_global
        ON allowance_intervals(
            is_archived, source_revision, end_observed_at DESC, interval_id DESC
        );
        """
    )


def add_allowance_plan_provenance(conn: sqlite3.Connection) -> None:
    """Add explicit observed subscription plan provenance to reset windows."""
    columns = {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in conn.execute("PRAGMA table_info(allowance_cycles)").fetchall()
    }
    if "plan_type" not in columns:
        conn.execute("ALTER TABLE allowance_cycles ADD COLUMN plan_type TEXT")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
        ).fetchone()
        is not None
    )
