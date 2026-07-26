"""Schema-v1 definition for foundational analytical facts."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1
APPLICATION_ID = 0x43555431
MAX_INDEX_COUNT = 18
SCHEMA_CAPABILITIES = frozenset(
    {
        "stable-identities",
        "generation-consistent-facts",
        "token-classes",
        "tool-activity",
        "allowance-observations",
    }
)
ANALYTICAL_TABLES = frozenset(
    {
        "sources",
        "generations",
        "threads",
        "turns",
        "model_calls",
        "tool_calls",
        "activity_events",
        "allowance_observations",
    }
)

_SCHEMA_SQL = """
CREATE TABLE generations (
    generation INTEGER PRIMARY KEY,
    source_revision_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    high_water_digest TEXT NOT NULL,
    inserted_count INTEGER NOT NULL CHECK (inserted_count >= 0),
    updated_count INTEGER NOT NULL CHECK (updated_count >= 0),
    deleted_count INTEGER NOT NULL CHECK (deleted_count >= 0),
    canonical_count INTEGER NOT NULL CHECK (canonical_count >= 0),
    excluded_count INTEGER NOT NULL CHECK (excluded_count >= 0),
    latest_event_at TEXT,
    parser_versions TEXT NOT NULL,
    integrity_status TEXT NOT NULL CHECK (
        integrity_status IN ('pending', 'valid', 'failed')
    )
) STRICT;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    archive_state TEXT NOT NULL CHECK (
        archive_state IN ('active', 'archived', 'missing', 'replaced')
    ),
    device_identity_hash TEXT,
    file_identity_hash TEXT,
    safe_label TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    modified_at TEXT,
    parsed_byte_offset INTEGER NOT NULL CHECK (parsed_byte_offset >= 0),
    parsed_line_number INTEGER NOT NULL CHECK (parsed_line_number >= 0),
    trailing_incomplete_bytes INTEGER NOT NULL CHECK (
        trailing_incomplete_bytes >= 0
    ),
    trailing_incomplete_hash TEXT,
    replacement_fingerprint TEXT NOT NULL,
    parser_adapter TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    parser_state_json TEXT NOT NULL,
    first_observed_at TEXT,
    last_observed_at TEXT,
    last_generation INTEGER REFERENCES generations(generation),
    parse_warning_count INTEGER NOT NULL CHECK (parse_warning_count >= 0),
    unsupported_shape_count INTEGER NOT NULL CHECK (
        unsupported_shape_count >= 0
    )
) STRICT;

CREATE TABLE threads (
    thread_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    logical_thread_id TEXT NOT NULL,
    session_identity_hash TEXT NOT NULL,
    display_label TEXT NOT NULL,
    project_label TEXT,
    created_at TEXT,
    updated_at TEXT,
    archived_at TEXT,
    archive_state TEXT NOT NULL CHECK (
        archive_state IN ('active', 'archived', 'unknown')
    ),
    parent_logical_thread_id TEXT,
    subagent_type TEXT,
    subagent_role TEXT,
    subagent_nickname TEXT,
    first_generation INTEGER NOT NULL REFERENCES generations(generation),
    last_generation INTEGER NOT NULL REFERENCES generations(generation),
    identity_basis TEXT NOT NULL,
    identity_confidence TEXT NOT NULL CHECK (
        identity_confidence IN ('exact', 'strong', 'inferred', 'unknown')
    )
) STRICT;

CREATE TABLE turns (
    turn_id TEXT PRIMARY KEY,
    source_turn_id_hash TEXT,
    thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    started_at TEXT,
    ended_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('open', 'completed', 'aborted', 'rolled_back')
    ),
    start_basis TEXT NOT NULL,
    completion_basis TEXT,
    basis_confidence TEXT NOT NULL CHECK (
        basis_confidence IN ('exact', 'strong', 'inferred', 'unknown')
    ),
    first_source_offset INTEGER NOT NULL CHECK (first_source_offset >= 0),
    last_source_offset INTEGER NOT NULL CHECK (
        last_source_offset >= first_source_offset
    ),
    model_call_count INTEGER NOT NULL CHECK (model_call_count >= 0),
    tool_call_count INTEGER NOT NULL CHECK (tool_call_count >= 0),
    skill_count INTEGER NOT NULL CHECK (skill_count >= 0),
    compaction_count INTEGER NOT NULL CHECK (compaction_count >= 0),
    patch_count INTEGER NOT NULL CHECK (patch_count >= 0),
    error_count INTEGER NOT NULL CHECK (error_count >= 0),
    first_generation INTEGER NOT NULL REFERENCES generations(generation),
    last_generation INTEGER NOT NULL REFERENCES generations(generation),
    UNIQUE (thread_id, ordinal)
) STRICT;

CREATE TABLE model_calls (
    model_call_id TEXT PRIMARY KEY,
    canonical_call_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(turn_id) ON DELETE SET NULL,
    event_at TEXT NOT NULL,
    turn_ordinal INTEGER NOT NULL CHECK (turn_ordinal >= 0),
    model TEXT NOT NULL,
    effort TEXT,
    service_tier TEXT,
    origin TEXT NOT NULL,
    context_window INTEGER CHECK (context_window > 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL CHECK (reasoning_tokens >= 0),
    upstream_total_tokens INTEGER CHECK (upstream_total_tokens >= 0),
    upstream_cumulative_tokens INTEGER CHECK (upstream_cumulative_tokens >= 0),
    rate_limit_observation_id TEXT,
    duplicate_state TEXT NOT NULL CHECK (
        duplicate_state IN ('canonical', 'copied', 'excluded', 'unknown')
    ),
    duplicate_reason TEXT,
    fingerprint_version INTEGER NOT NULL CHECK (fingerprint_version > 0),
    source_offset INTEGER NOT NULL CHECK (source_offset >= 0),
    generation INTEGER NOT NULL REFERENCES generations(generation)
) STRICT;

CREATE TABLE tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    upstream_call_id_hash TEXT,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(turn_id) ON DELETE SET NULL,
    nearest_model_call_id TEXT REFERENCES model_calls(model_call_id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    server_name TEXT,
    namespace TEXT,
    tool_category TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    duration_ms REAL CHECK (duration_ms >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('started', 'completed', 'failed', 'incomplete')
    ),
    error_category TEXT,
    output_bytes INTEGER CHECK (output_bytes >= 0),
    argument_shape TEXT,
    first_source_offset INTEGER NOT NULL CHECK (first_source_offset >= 0),
    last_source_offset INTEGER NOT NULL CHECK (
        last_source_offset >= first_source_offset
    ),
    generation INTEGER NOT NULL REFERENCES generations(generation),
    observation_confidence TEXT NOT NULL CHECK (
        observation_confidence IN ('exact', 'strong', 'inferred', 'unknown')
    )
) STRICT;

CREATE TABLE activity_events (
    activity_event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    turn_id TEXT REFERENCES turns(turn_id) ON DELETE SET NULL,
    event_kind TEXT NOT NULL,
    event_at TEXT NOT NULL,
    safe_label TEXT,
    category TEXT,
    source_offset INTEGER NOT NULL CHECK (source_offset >= 0),
    generation INTEGER NOT NULL REFERENCES generations(generation)
) STRICT;

CREATE TABLE allowance_observations (
    allowance_observation_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    window_kind TEXT NOT NULL,
    limit_id TEXT,
    plan_type TEXT,
    used_percent REAL NOT NULL CHECK (used_percent >= 0 AND used_percent <= 100),
    duration_minutes INTEGER CHECK (duration_minutes > 0),
    resets_at TEXT,
    model TEXT,
    service_tier TEXT,
    source_model_call_id TEXT REFERENCES model_calls(model_call_id) ON DELETE SET NULL,
    generation INTEGER NOT NULL REFERENCES generations(generation),
    duplicate_state TEXT NOT NULL CHECK (
        duplicate_state IN ('canonical', 'copied', 'excluded', 'unknown')
    ),
    provenance TEXT NOT NULL,
    validation_warnings TEXT NOT NULL
) STRICT;

CREATE INDEX idx_sources_generation
ON sources(last_generation);
CREATE INDEX idx_threads_source
ON threads(source_id, last_generation);
CREATE INDEX idx_threads_parent
ON threads(parent_logical_thread_id);
CREATE INDEX idx_turns_thread
ON turns(thread_id, ordinal);
CREATE INDEX idx_turns_generation
ON turns(last_generation);
CREATE INDEX idx_model_calls_thread_time
ON model_calls(thread_id, event_at);
CREATE INDEX idx_model_calls_turn
ON model_calls(turn_id, turn_ordinal);
CREATE INDEX idx_model_calls_generation
ON model_calls(generation);
CREATE INDEX idx_model_calls_canonical
ON model_calls(canonical_call_id, duplicate_state);
CREATE INDEX idx_tool_calls_thread_time
ON tool_calls(thread_id, started_at);
CREATE INDEX idx_tool_calls_turn
ON tool_calls(turn_id);
CREATE INDEX idx_tool_calls_generation
ON tool_calls(generation);
CREATE INDEX idx_activity_thread_time
ON activity_events(thread_id, event_at);
CREATE INDEX idx_activity_turn
ON activity_events(turn_id);
CREATE INDEX idx_allowance_time
ON allowance_observations(observed_at);
CREATE INDEX idx_allowance_generation
ON allowance_observations(generation);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the deterministic analytical schema on an empty connection."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.executescript(_SCHEMA_SQL)
