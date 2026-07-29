from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

SCHEMA_VERSION = 1

TABLE_DDL = (
    """
    CREATE TABLE candidate_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE source_manifestations (
        manifestation_pk INTEGER PRIMARY KEY,
        manifestation_id TEXT NOT NULL,
        relative_path TEXT NOT NULL UNIQUE,
        logical_source TEXT NOT NULL,
        revision TEXT NOT NULL,
        state TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
        record_count INTEGER NOT NULL CHECK (record_count >= 0),
        content_sha256 TEXT NOT NULL,
        selected_history TEXT NOT NULL,
        moving_tail INTEGER NOT NULL CHECK (moving_tail IN (0, 1))
    )
    """,
    """
    CREATE TABLE occurrences (
        occurrence_pk INTEGER PRIMARY KEY,
        manifestation_pk INTEGER NOT NULL
            REFERENCES source_manifestations(manifestation_pk),
        record_ordinal INTEGER NOT NULL CHECK (record_ordinal >= 0),
        byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
        byte_end INTEGER NOT NULL CHECK (byte_end > byte_start),
        entity_kind INTEGER NOT NULL CHECK (entity_kind > 0),
        logical_id TEXT NOT NULL,
        missing_time INTEGER NOT NULL CHECK (missing_time IN (0, 1)),
        event_at_us INTEGER NOT NULL,
        source_order INTEGER NOT NULL,
        event_kind_order INTEGER NOT NULL,
        session_id TEXT,
        turn_id TEXT,
        canonical INTEGER NOT NULL CHECK (canonical IN (0, 1)),
        sequence_indexed INTEGER NOT NULL CHECK (sequence_indexed IN (0, 1)),
        UNIQUE (manifestation_pk, record_ordinal)
    )
    """,
    """
    CREATE TABLE sequence_index (
        missing_time INTEGER NOT NULL,
        event_at_us INTEGER NOT NULL,
        source_order INTEGER NOT NULL,
        event_kind_order INTEGER NOT NULL,
        logical_id TEXT NOT NULL,
        entity_kind INTEGER NOT NULL,
        occurrence_pk INTEGER NOT NULL UNIQUE
            REFERENCES occurrences(occurrence_pk) ON DELETE CASCADE,
        PRIMARY KEY (
            missing_time,
            event_at_us,
            source_order,
            event_kind_order,
            logical_id
        )
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT,
        direct_parent_session_id TEXT,
        root_session_id TEXT,
        delegation_depth INTEGER,
        started_at_us INTEGER,
        terminal_at_us INTEGER,
        state TEXT NOT NULL,
        completion_basis TEXT,
        start_occurrence_pk INTEGER REFERENCES occurrences(occurrence_pk),
        terminal_occurrence_pk INTEGER REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE session_parent_observations (
        child_session_id TEXT PRIMARY KEY,
        parent_session_id TEXT NOT NULL,
        transition TEXT NOT NULL,
        event_at_us INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE turns (
        turn_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        started_at_us INTEGER,
        state TEXT NOT NULL,
        start_occurrence_pk INTEGER REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE model_calls (
        call_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        event_at_us INTEGER,
        model TEXT NOT NULL,
        reasoning_effort TEXT,
        context_window_tokens INTEGER,
        uncached_input_tokens INTEGER,
        cached_input_tokens INTEGER,
        reasoning_tokens INTEGER,
        output_tokens INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE tool_invocations (
        tool_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        transport_name TEXT NOT NULL,
        semantic_operation TEXT NOT NULL,
        resource_id TEXT,
        write_intent INTEGER NOT NULL CHECK (write_intent IN (0, 1)),
        state TEXT NOT NULL,
        started_at_us INTEGER,
        terminal_at_us INTEGER,
        duration_us INTEGER,
        output_bytes INTEGER,
        start_occurrence_pk INTEGER REFERENCES occurrences(occurrence_pk),
        terminal_occurrence_pk INTEGER REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE tool_transitions (
        occurrence_pk INTEGER PRIMARY KEY REFERENCES occurrences(occurrence_pk),
        tool_id TEXT NOT NULL REFERENCES tool_invocations(tool_id),
        state TEXT NOT NULL,
        event_at_us INTEGER,
        transition_kind TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE activities (
        activity_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT,
        activity_kind TEXT NOT NULL,
        state TEXT NOT NULL,
        event_at_us INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE state_changes (
        change_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        turn_id TEXT,
        resource_id TEXT NOT NULL,
        change_kind TEXT NOT NULL,
        preceding_activity_count INTEGER NOT NULL CHECK (preceding_activity_count >= 0),
        causal_attribution TEXT,
        event_at_us INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE compaction_boundaries (
        compaction_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        before_context_epoch TEXT NOT NULL,
        after_context_epoch TEXT NOT NULL,
        event_at_us INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE allowance_observations (
        observation_id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        limit_id TEXT NOT NULL,
        plan_identity TEXT NOT NULL,
        window_kind TEXT NOT NULL,
        cycle_id TEXT NOT NULL,
        reset_identity TEXT NOT NULL,
        observation_ordinal INTEGER NOT NULL,
        used_percent TEXT NOT NULL,
        remaining_percent TEXT NOT NULL,
        event_at_us INTEGER,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE allowance_compatibility (
        compatibility_id TEXT PRIMARY KEY,
        start_observation_id TEXT NOT NULL,
        end_observation_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        limit_id TEXT NOT NULL,
        plan_identity TEXT NOT NULL,
        window_kind TEXT NOT NULL,
        cycle_id TEXT NOT NULL,
        reset_identity TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE selector_anchors (
        selector_kind TEXT NOT NULL,
        logical_id TEXT NOT NULL,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk),
        PRIMARY KEY (selector_kind, logical_id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE question_cases (
        oracle_id TEXT PRIMARY KEY,
        question_id TEXT NOT NULL,
        variant TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        occurrence_pk INTEGER NOT NULL UNIQUE REFERENCES occurrences(occurrence_pk)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE question_case_fields (
        oracle_id TEXT NOT NULL REFERENCES question_cases(oracle_id) ON DELETE CASCADE,
        field_name TEXT NOT NULL,
        value_kind TEXT NOT NULL,
        integer_value INTEGER,
        text_value TEXT,
        PRIMARY KEY (oracle_id, field_name)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE question_case_selectors (
        oracle_id TEXT NOT NULL REFERENCES question_cases(oracle_id) ON DELETE CASCADE,
        selector TEXT NOT NULL,
        manifestation_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        revision TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        record_ordinal INTEGER NOT NULL,
        byte_start INTEGER NOT NULL,
        byte_end INTEGER NOT NULL,
        PRIMARY KEY (oracle_id, selector)
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
        latest_event_at_us INTEGER
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE tool_family_current (
        transport_name TEXT NOT NULL,
        semantic_operation TEXT NOT NULL,
        invocations INTEGER NOT NULL,
        succeeded INTEGER NOT NULL,
        failed INTEGER NOT NULL,
        cancelled INTEGER NOT NULL,
        output_bytes INTEGER NOT NULL,
        duration_us INTEGER NOT NULL,
        PRIMARY KEY (transport_name, semantic_operation)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE publication_log (
        publication_id TEXT PRIMARY KEY,
        fixture_manifest_digest TEXT NOT NULL,
        fixture_oracle_digest TEXT NOT NULL,
        state TEXT NOT NULL,
        promoted_at_us INTEGER NOT NULL,
        change_kind TEXT NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE source_mutations (
        mutation_id TEXT PRIMARY KEY,
        change_kind TEXT NOT NULL,
        inserted_entities INTEGER NOT NULL,
        updated_entities INTEGER NOT NULL,
        removed_entities INTEGER NOT NULL,
        recanonicalized_entities INTEGER NOT NULL,
        publication_id TEXT NOT NULL
    ) WITHOUT ROWID
    """,
)

INDEX_DDL = (
    "CREATE INDEX occurrence_logical_idx ON occurrences(entity_kind, logical_id)",
    "CREATE INDEX occurrence_session_idx ON occurrences(session_id, occurrence_pk)",
    "CREATE INDEX occurrence_turn_idx ON occurrences(turn_id, occurrence_pk)",
    "CREATE INDEX sequence_logical_idx ON sequence_index(logical_id)",
    "CREATE INDEX call_time_idx ON model_calls(event_at_us, call_id)",
    "CREATE INDEX call_session_time_idx ON model_calls(session_id, event_at_us, call_id)",
    "CREATE INDEX call_turn_time_idx ON model_calls(turn_id, event_at_us, call_id)",
    "CREATE INDEX tool_session_time_idx ON tool_invocations(session_id, started_at_us, tool_id)",
    "CREATE INDEX tool_resource_time_idx ON tool_invocations(resource_id, started_at_us, tool_id)",
    "CREATE INDEX state_change_turn_time_idx ON state_changes(turn_id, event_at_us, change_id)",
    """
    CREATE INDEX allowance_compatibility_idx
        ON allowance_observations(
            provider,
            limit_id,
            plan_identity,
            window_kind,
            cycle_id,
            reset_identity,
            event_at_us,
            observation_id
        )
    """,
    "CREATE INDEX question_id_idx ON question_cases(question_id, oracle_id)",
)


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    target = f"file:{path}?mode=ro" if readonly else str(path)
    connection = sqlite3.connect(target, uri=readonly)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
    return connection


def configure_writer(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA page_size = 4096")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA cache_size = -20000")
    connection.execute("PRAGMA mmap_size = 0")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA wal_autocheckpoint = 1000")


def create_schema(
    connection: sqlite3.Connection,
    *,
    index_mode: str = "present",
) -> None:
    if index_mode not in {"present", "deferred", "rebuilt"}:
        raise ValueError(f"unknown Candidate D index mode: {index_mode}")
    configure_writer(connection)
    for statement in TABLE_DDL:
        connection.execute(statement)
    if index_mode == "present":
        create_indexes(connection)
    connection.executemany(
        "INSERT INTO candidate_metadata(key, value) VALUES (?, ?)",
        (
            ("candidate_id", "D"),
            ("contract_version", "ck04-candidate-adapter-v1"),
            ("schema_version", str(SCHEMA_VERSION)),
            ("sequence_authority", "compact-sequence-index"),
        ),
    )


def create_indexes(connection: sqlite3.Connection) -> None:
    for statement in INDEX_DDL:
        connection.execute(statement)


def rebuild_indexes(connection: sqlite3.Connection) -> None:
    names = tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'index' AND sql IS NOT NULL
            ORDER BY name
            """
        )
    )
    for name in names:
        connection.execute(f'DROP INDEX "{name}"')
    create_indexes(connection)


def table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    )


def index_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type = 'index' AND sql IS NOT NULL
            ORDER BY name
            """
        )
    )


def count_rows(connection: sqlite3.Connection, names: Iterable[str]) -> int:
    total = 0
    for name in names:
        total += int(connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
    return total
