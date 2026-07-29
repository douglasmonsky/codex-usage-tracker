"""Experimental Candidate C SQLite schema.

The event backbone is the only total-order and occurrence authority. Typed
point facts and lifecycle entities refer back to backbone occurrences rather
than copying a second sequence index.
"""

from __future__ import annotations

import sqlite3

CANDIDATE_ID = "C"
SCHEMA_VERSION = 1

_TABLE_STATEMENTS = (
    """
    CREATE TABLE metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE source_manifestations (
        manifestation_id TEXT NOT NULL,
        revision TEXT NOT NULL,
        source_path TEXT NOT NULL,
        logical_source TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        source_state TEXT NOT NULL,
        byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
        record_count INTEGER NOT NULL CHECK (record_count >= 0),
        content_sha256 TEXT NOT NULL,
        PRIMARY KEY (manifestation_id, revision, source_path)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE event_backbone (
        occurrence_id TEXT PRIMARY KEY,
        logical_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_at_us INTEGER NOT NULL,
        event_kind_order INTEGER NOT NULL,
        source_order INTEGER NOT NULL,
        manifestation_id TEXT NOT NULL,
        revision TEXT NOT NULL,
        source_path TEXT NOT NULL,
        record_ordinal INTEGER NOT NULL CHECK (record_ordinal >= 0),
        byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
        byte_end INTEGER NOT NULL CHECK (byte_end >= byte_start),
        payload_sha256 TEXT NOT NULL,
        canonical_owner INTEGER NOT NULL CHECK (canonical_owner IN (0, 1)),
        FOREIGN KEY (
            manifestation_id,
            revision,
            source_path
        ) REFERENCES source_manifestations (
            manifestation_id,
            revision,
            source_path
        ),
        UNIQUE (manifestation_id, revision, source_path, record_ordinal)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        first_occurrence_id TEXT NOT NULL,
        project_id TEXT,
        parent_session_id TEXT,
        started_at_us INTEGER NOT NULL,
        terminal_at_us INTEGER,
        state TEXT NOT NULL,
        completion_basis TEXT,
        FOREIGN KEY (first_occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE session_transitions (
        occurrence_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        state TEXT NOT NULL,
        completion_basis TEXT,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE turns (
        turn_id TEXT PRIMARY KEY,
        first_occurrence_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        started_at_us INTEGER NOT NULL,
        state TEXT NOT NULL,
        FOREIGN KEY (first_occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE model_calls (
        call_id TEXT PRIMARY KEY,
        canonical_occurrence_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        event_at_us INTEGER NOT NULL,
        model TEXT NOT NULL,
        reasoning_effort TEXT,
        context_window_tokens INTEGER,
        uncached_input_tokens INTEGER,
        cached_input_tokens INTEGER,
        reasoning_tokens INTEGER,
        output_tokens INTEGER,
        FOREIGN KEY (canonical_occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id),
        FOREIGN KEY (turn_id) REFERENCES turns (turn_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE tool_invocations (
        tool_id TEXT PRIMARY KEY,
        first_occurrence_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        resource_id TEXT,
        transport_name TEXT NOT NULL,
        semantic_operation TEXT NOT NULL,
        write_intent INTEGER NOT NULL CHECK (write_intent IN (0, 1)),
        started_at_us INTEGER NOT NULL,
        terminal_at_us INTEGER,
        state TEXT NOT NULL,
        duration_us INTEGER,
        output_bytes INTEGER,
        FOREIGN KEY (first_occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id),
        FOREIGN KEY (turn_id) REFERENCES turns (turn_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE tool_transitions (
        occurrence_id TEXT PRIMARY KEY,
        tool_id TEXT NOT NULL,
        state TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (tool_id) REFERENCES tool_invocations (tool_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE state_changes (
        change_id TEXT PRIMARY KEY,
        occurrence_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        change_kind TEXT NOT NULL,
        preceding_activity_count INTEGER NOT NULL CHECK (preceding_activity_count >= 0),
        causal_attribution INTEGER NOT NULL CHECK (causal_attribution = 0),
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id),
        FOREIGN KEY (turn_id) REFERENCES turns (turn_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE allowance_observations (
        observation_id TEXT PRIMARY KEY,
        occurrence_id TEXT NOT NULL UNIQUE,
        provider TEXT NOT NULL,
        plan_identity TEXT NOT NULL,
        limit_id TEXT NOT NULL,
        cycle_id TEXT NOT NULL,
        reset_identity TEXT NOT NULL,
        window_kind TEXT NOT NULL,
        observation_ordinal INTEGER NOT NULL,
        used_percent TEXT,
        remaining_percent TEXT,
        event_at_us INTEGER NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE allowance_compatibility (
        occurrence_id TEXT PRIMARY KEY,
        start_observation_id TEXT NOT NULL,
        end_observation_id TEXT NOT NULL,
        compatibility_key TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE compaction_boundaries (
        compaction_id TEXT PRIMARY KEY,
        occurrence_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL,
        before_context_epoch TEXT NOT NULL,
        after_context_epoch TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE activities (
        activity_id TEXT PRIMARY KEY,
        occurrence_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        activity_kind TEXT NOT NULL,
        state TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE parent_observations (
        occurrence_id TEXT PRIMARY KEY,
        child_session_id TEXT NOT NULL,
        parent_session_id TEXT NOT NULL,
        transition TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE selector_anchors (
        selector TEXT PRIMARY KEY,
        logical_id TEXT NOT NULL,
        selector_kind TEXT NOT NULL,
        occurrence_id TEXT NOT NULL UNIQUE,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE oracle_cases (
        oracle_id TEXT PRIMARY KEY,
        occurrence_id TEXT NOT NULL UNIQUE,
        question_id TEXT NOT NULL,
        variant TEXT NOT NULL,
        slice_name TEXT NOT NULL,
        observed_facts_json TEXT NOT NULL,
        selector_ids_json TEXT NOT NULL,
        inputs_json TEXT NOT NULL,
        FOREIGN KEY (occurrence_id) REFERENCES event_backbone (occurrence_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE source_phase_occurrences (
        group_name TEXT NOT NULL,
        call_id TEXT NOT NULL,
        revision TEXT NOT NULL,
        disposition TEXT NOT NULL,
        event_at_us INTEGER NOT NULL,
        PRIMARY KEY (group_name, call_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE session_usage_current (
        session_id TEXT PRIMARY KEY,
        calls INTEGER NOT NULL,
        uncached_input_tokens INTEGER,
        cached_input_tokens INTEGER,
        reasoning_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        last_event_at_us INTEGER NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE model_effort_current (
        model TEXT NOT NULL,
        reasoning_effort TEXT NOT NULL,
        calls INTEGER NOT NULL,
        uncached_input_tokens INTEGER,
        cached_input_tokens INTEGER,
        reasoning_tokens INTEGER,
        output_tokens INTEGER,
        PRIMARY KEY (model, reasoning_effort)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE dirty_projection_keys (
        consumer TEXT NOT NULL,
        dirty_key TEXT NOT NULL,
        PRIMARY KEY (consumer, dirty_key)
    ) WITHOUT ROWID
    """,
)

_INDEX_STATEMENTS = (
    """
    CREATE INDEX event_backbone_total_order
    ON event_backbone (
        event_at_us,
        event_kind_order,
        source_order,
        logical_id,
        occurrence_id
    )
    """,
    """
    CREATE INDEX event_backbone_logical_order
    ON event_backbone (
        logical_id,
        event_at_us,
        event_kind_order,
        source_order,
        occurrence_id
    )
    """,
    """
    CREATE INDEX model_calls_session_order
    ON model_calls (session_id, event_at_us, call_id)
    """,
    """
    CREATE INDEX model_calls_model_effort
    ON model_calls (model, reasoning_effort, event_at_us, call_id)
    """,
    """
    CREATE INDEX tool_invocations_turn_order
    ON tool_invocations (turn_id, started_at_us, tool_id)
    """,
    """
    CREATE INDEX state_changes_turn_order
    ON state_changes (turn_id, occurrence_id)
    """,
    """
    CREATE INDEX allowance_observations_order
    ON allowance_observations (
        provider,
        limit_id,
        event_at_us,
        observation_ordinal,
        observation_id
    )
    """,
    """
    CREATE INDEX oracle_cases_question
    ON oracle_cases (question_id, variant, oracle_id)
    """,
    """
    CREATE INDEX session_usage_current_rank
    ON session_usage_current (total_tokens DESC, session_id)
    """,
)


def create_schema(connection: sqlite3.Connection, *, indexes: bool = True) -> None:
    """Create Candidate C's experimental schema on an empty database."""
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in _TABLE_STATEMENTS:
        connection.execute(statement)
    if indexes:
        create_indexes(connection)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def create_indexes(connection: sqlite3.Connection) -> None:
    """Create every declared secondary index idempotently."""
    for statement in _INDEX_STATEMENTS:
        connection.execute(statement.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1))


def index_names() -> frozenset[str]:
    return frozenset(statement.split()[2] for statement in _INDEX_STATEMENTS)


def table_names() -> frozenset[str]:
    return frozenset(statement.split()[2] for statement in _TABLE_STATEMENTS)
