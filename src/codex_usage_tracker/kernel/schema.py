"""Schema-v3 definition for compact metadata-first analytical facts."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3
APPLICATION_ID = 0x43555431
MAX_INDEX_COUNT = 14
SCHEMA_CAPABILITIES = frozenset(
    {
        "stable-identities",
        "generation-consistent-facts",
        "token-classes",
        "tool-activity",
        "allowance-observations",
        "allowance-efficiency-intervals",
        "compact-integer-foreign-keys",
        "generation-rollups",
        "allowance-state-intervals",
        "observation-trigger-not-causation",
        "metadata-only",
    }
)
ANALYTICAL_TABLES = frozenset(
    {
        "sources",
        "generations",
        "threads",
        "turns",
        "model_profiles",
        "tool_profiles",
        "model_call_facts",
        "tool_call_facts",
        "activity_facts",
        "allowance_states",
        "rollup_global",
        "rollup_thread",
        "rollup_model_effort",
        "rollup_time_band",
        "rollup_cost_credits",
        "rollup_allowance",
        "rollup_tool_operation",
    }
)
REQUIRED_SCHEMA_OBJECTS = frozenset(
    {
        "model_calls",
        "tool_calls",
        "activity_events",
        "allowance_observations",
        "allowance_intervals",
        "idx_allowance_window_time",
        "idx_model_calls_time",
        "idx_model_calls_thread_time",
        "idx_tool_calls_thread_time",
    }
)

SECONDARY_INDEX_SQL = {
    "idx_sources_generation": (
        "CREATE INDEX idx_sources_generation ON sources(last_generation)"
    ),
    "idx_threads_logical": (
        "CREATE INDEX idx_threads_logical "
        "ON threads(logical_thread_id, last_generation)"
    ),
    "idx_turns_thread": (
        "CREATE INDEX idx_turns_thread ON turns(thread_key, ordinal)"
    ),
    "idx_model_calls_thread_time": (
        "CREATE INDEX idx_model_calls_thread_time "
        "ON model_call_facts(thread_key, event_at)"
    ),
    "idx_model_calls_turn": (
        "CREATE INDEX idx_model_calls_turn "
        "ON model_call_facts(turn_key, turn_ordinal)"
    ),
    "idx_model_calls_generation": (
        "CREATE INDEX idx_model_calls_generation ON model_call_facts(generation)"
    ),
    "idx_model_calls_canonical": (
        "CREATE INDEX idx_model_calls_canonical "
        "ON model_call_facts(canonical_call_id, duplicate_state)"
    ),
    "idx_model_calls_time": (
        "CREATE INDEX idx_model_calls_time "
        "ON model_call_facts(event_at, generation, duplicate_state)"
    ),
    "idx_tool_calls_thread_time": (
        "CREATE INDEX idx_tool_calls_thread_time "
        "ON tool_call_facts(thread_key, started_at)"
    ),
    "idx_activity_thread_time": (
        "CREATE INDEX idx_activity_thread_time "
        "ON activity_facts(thread_key, event_at)"
    ),
    "idx_allowance_window_time": (
        "CREATE INDEX idx_allowance_window_time "
        "ON allowance_states("
        "window_kind, COALESCE(limit_id, ''), COALESCE(plan_type, ''), "
        "last_observed_at)"
    ),
}

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
    source_key INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
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
    thread_key INTEGER PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    source_key INTEGER NOT NULL REFERENCES sources(source_key) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
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
    turn_key INTEGER PRIMARY KEY,
    turn_id TEXT NOT NULL UNIQUE,
    source_turn_id_hash TEXT,
    thread_key INTEGER NOT NULL REFERENCES threads(thread_key) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
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
    UNIQUE (thread_key, ordinal)
) STRICT;

CREATE TABLE model_profiles (
    model_profile_key INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    effort_key TEXT NOT NULL,
    service_tier_key TEXT NOT NULL,
    origin TEXT NOT NULL,
    UNIQUE (model, effort_key, service_tier_key, origin)
) STRICT;

CREATE TABLE tool_profiles (
    tool_profile_key INTEGER PRIMARY KEY,
    tool_name TEXT NOT NULL,
    server_name_key TEXT NOT NULL,
    namespace_key TEXT NOT NULL,
    tool_category TEXT NOT NULL,
    operation TEXT NOT NULL,
    UNIQUE (
        tool_name,
        server_name_key,
        namespace_key,
        tool_category,
        operation
    )
) STRICT;

CREATE TABLE model_call_facts (
    model_call_key INTEGER PRIMARY KEY,
    model_call_id BLOB NOT NULL UNIQUE,
    canonical_call_id BLOB NOT NULL,
    source_key INTEGER NOT NULL REFERENCES sources(source_key) ON DELETE CASCADE,
    thread_key INTEGER NOT NULL REFERENCES threads(thread_key) ON DELETE CASCADE,
    turn_key INTEGER REFERENCES turns(turn_key) ON DELETE SET NULL,
    model_profile_key INTEGER NOT NULL REFERENCES model_profiles(
        model_profile_key
    ),
    event_at TEXT NOT NULL,
    turn_ordinal INTEGER NOT NULL CHECK (turn_ordinal >= 0),
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

CREATE TABLE tool_call_facts (
    tool_call_key INTEGER PRIMARY KEY,
    tool_call_id BLOB NOT NULL UNIQUE,
    upstream_call_id_hash TEXT,
    source_key INTEGER NOT NULL REFERENCES sources(source_key) ON DELETE CASCADE,
    thread_key INTEGER NOT NULL REFERENCES threads(thread_key) ON DELETE CASCADE,
    turn_key INTEGER REFERENCES turns(turn_key) ON DELETE SET NULL,
    tool_profile_key INTEGER NOT NULL REFERENCES tool_profiles(tool_profile_key),
    nearest_model_call_key INTEGER REFERENCES model_call_facts(model_call_key)
        ON DELETE SET NULL,
    target_label TEXT,
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

CREATE TABLE activity_facts (
    activity_key INTEGER PRIMARY KEY,
    activity_event_id BLOB NOT NULL UNIQUE,
    source_key INTEGER NOT NULL REFERENCES sources(source_key) ON DELETE CASCADE,
    thread_key INTEGER NOT NULL REFERENCES threads(thread_key) ON DELETE CASCADE,
    turn_key INTEGER REFERENCES turns(turn_key) ON DELETE SET NULL,
    event_kind TEXT NOT NULL,
    event_at TEXT NOT NULL,
    safe_label TEXT,
    category TEXT,
    source_offset INTEGER NOT NULL CHECK (source_offset >= 0),
    generation INTEGER NOT NULL REFERENCES generations(generation)
) STRICT;

CREATE TABLE allowance_states (
    allowance_state_key INTEGER PRIMARY KEY,
    allowance_observation_id BLOB NOT NULL UNIQUE,
    source_key INTEGER NOT NULL REFERENCES sources(source_key) ON DELETE CASCADE,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL CHECK (observation_count > 0),
    window_kind TEXT NOT NULL,
    limit_id TEXT,
    plan_type TEXT,
    used_percent REAL NOT NULL CHECK (used_percent >= 0 AND used_percent <= 100),
    duration_minutes INTEGER CHECK (duration_minutes > 0),
    resets_at TEXT,
    model TEXT,
    service_tier TEXT,
    observation_trigger_call_key INTEGER REFERENCES model_call_facts(model_call_key)
        ON DELETE SET NULL,
    generation INTEGER NOT NULL REFERENCES generations(generation),
    duplicate_state TEXT NOT NULL CHECK (
        duplicate_state IN ('canonical', 'copied', 'excluded', 'unknown')
    ),
    provenance TEXT NOT NULL,
    validation_warnings TEXT NOT NULL
) STRICT;

CREATE TABLE rollup_global (
    generation INTEGER PRIMARY KEY REFERENCES generations(generation)
        ON DELETE CASCADE,
    calls INTEGER NOT NULL CHECK (calls >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL CHECK (reasoning_tokens >= 0)
) STRICT;

CREATE TABLE rollup_thread (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    thread_key INTEGER NOT NULL REFERENCES threads(thread_key) ON DELETE CASCADE,
    calls INTEGER NOT NULL CHECK (calls >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL CHECK (reasoning_tokens >= 0),
    PRIMARY KEY (generation, thread_key)
) STRICT, WITHOUT ROWID;

CREATE TABLE rollup_model_effort (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    model TEXT NOT NULL,
    effort TEXT NOT NULL,
    service_tier TEXT NOT NULL,
    calls INTEGER NOT NULL CHECK (calls >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL CHECK (reasoning_tokens >= 0),
    PRIMARY KEY (generation, model, effort, service_tier)
) STRICT, WITHOUT ROWID;

CREATE TABLE rollup_time_band (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    band_kind TEXT NOT NULL CHECK (band_kind IN ('hour', 'day')),
    band_start TEXT NOT NULL,
    calls INTEGER NOT NULL CHECK (calls >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL CHECK (reasoning_tokens >= 0),
    PRIMARY KEY (generation, band_kind, band_start)
) STRICT, WITHOUT ROWID;

CREATE TABLE rollup_cost_credits (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    scope_kind TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    configured_cost_micros INTEGER NOT NULL CHECK (configured_cost_micros >= 0),
    estimated_credits_micros INTEGER NOT NULL CHECK (
        estimated_credits_micros >= 0
    ),
    covered_calls INTEGER NOT NULL CHECK (covered_calls >= 0),
    uncovered_calls INTEGER NOT NULL CHECK (uncovered_calls >= 0),
    rate_card_digest TEXT,
    PRIMARY KEY (generation, scope_kind, scope_key)
) STRICT, WITHOUT ROWID;

CREATE TABLE rollup_allowance (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    allowance_state_key INTEGER NOT NULL REFERENCES allowance_states(
        allowance_state_key
    ) ON DELETE CASCADE,
    delta_used_percent REAL,
    elapsed_hours REAL,
    local_calls INTEGER NOT NULL CHECK (local_calls >= 0),
    local_turns INTEGER NOT NULL CHECK (local_turns >= 0),
    local_total_tokens INTEGER NOT NULL CHECK (local_total_tokens >= 0),
    PRIMARY KEY (generation, allowance_state_key)
) STRICT, WITHOUT ROWID;

CREATE TABLE rollup_tool_operation (
    generation INTEGER NOT NULL REFERENCES generations(generation)
        ON DELETE CASCADE,
    operation TEXT NOT NULL,
    target_label TEXT NOT NULL,
    calls INTEGER NOT NULL CHECK (calls >= 0),
    duration_ms REAL NOT NULL CHECK (duration_ms >= 0),
    output_bytes INTEGER NOT NULL CHECK (output_bytes >= 0),
    PRIMARY KEY (generation, operation, target_label)
) STRICT, WITHOUT ROWID;

CREATE INDEX idx_sources_generation
ON sources(last_generation);
CREATE INDEX idx_threads_logical
ON threads(logical_thread_id, last_generation);
CREATE INDEX idx_turns_thread
ON turns(thread_key, ordinal);
CREATE INDEX idx_model_calls_thread_time
ON model_call_facts(thread_key, event_at);
CREATE INDEX idx_model_calls_turn
ON model_call_facts(turn_key, turn_ordinal);
CREATE INDEX idx_model_calls_generation
ON model_call_facts(generation);
CREATE INDEX idx_model_calls_canonical
ON model_call_facts(canonical_call_id, duplicate_state);
CREATE INDEX idx_model_calls_time
ON model_call_facts(event_at, generation, duplicate_state);
CREATE INDEX idx_tool_calls_thread_time
ON tool_call_facts(thread_key, started_at);
CREATE INDEX idx_activity_thread_time
ON activity_facts(thread_key, event_at);
CREATE INDEX idx_allowance_window_time
ON allowance_states(
    window_kind,
    COALESCE(limit_id, ''),
    COALESCE(plan_type, ''),
    last_observed_at
);

CREATE VIEW model_calls AS
SELECT
    'call_' || lower(hex(facts.model_call_id)) AS model_call_id,
    'fp_' || lower(hex(facts.canonical_call_id)) AS canonical_call_id,
    sources.source_id,
    threads.thread_id,
    turns.turn_id,
    facts.event_at,
    facts.turn_ordinal,
    model_profiles.model,
    NULLIF(model_profiles.effort_key, '') AS effort,
    NULLIF(model_profiles.service_tier_key, '') AS service_tier,
    model_profiles.origin,
    facts.context_window,
    facts.input_tokens,
    facts.cached_input_tokens,
    facts.output_tokens,
    facts.reasoning_tokens,
    facts.upstream_total_tokens,
    facts.upstream_cumulative_tokens,
    facts.rate_limit_observation_id,
    facts.duplicate_state,
    facts.duplicate_reason,
    facts.fingerprint_version,
    facts.source_offset,
    facts.generation
FROM model_call_facts AS facts
JOIN sources USING (source_key)
JOIN threads USING (thread_key)
LEFT JOIN turns USING (turn_key)
JOIN model_profiles USING (model_profile_key);

CREATE TRIGGER insert_model_calls
INSTEAD OF INSERT ON model_calls
BEGIN
    INSERT INTO model_profiles(
        model,
        effort_key,
        service_tier_key,
        origin
    )
    VALUES (
        NEW.model,
        COALESCE(NEW.effort, ''),
        COALESCE(NEW.service_tier, ''),
        NEW.origin
    )
    ON CONFLICT(model, effort_key, service_tier_key, origin) DO NOTHING;

    INSERT INTO model_call_facts(
        model_call_id,
        canonical_call_id,
        source_key,
        thread_key,
        turn_key,
        model_profile_key,
        event_at,
        turn_ordinal,
        context_window,
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_tokens,
        upstream_total_tokens,
        upstream_cumulative_tokens,
        rate_limit_observation_id,
        duplicate_state,
        duplicate_reason,
        fingerprint_version,
        source_offset,
        generation
    )
    SELECT
        unhex(substr(NEW.model_call_id, 6)),
        unhex(substr(NEW.canonical_call_id, 4)),
        sources.source_key,
        threads.thread_key,
        turns.turn_key,
        model_profiles.model_profile_key,
        NEW.event_at,
        NEW.turn_ordinal,
        NEW.context_window,
        NEW.input_tokens,
        NEW.cached_input_tokens,
        NEW.output_tokens,
        NEW.reasoning_tokens,
        NEW.upstream_total_tokens,
        NEW.upstream_cumulative_tokens,
        NEW.rate_limit_observation_id,
        NEW.duplicate_state,
        NEW.duplicate_reason,
        NEW.fingerprint_version,
        NEW.source_offset,
        NEW.generation
    FROM sources
    JOIN threads ON threads.thread_id = NEW.thread_id
    LEFT JOIN turns ON turns.turn_id = NEW.turn_id
    JOIN model_profiles
      ON model_profiles.model = NEW.model
     AND model_profiles.effort_key = COALESCE(NEW.effort, '')
     AND model_profiles.service_tier_key = COALESCE(NEW.service_tier, '')
     AND model_profiles.origin = NEW.origin
    WHERE sources.source_id = NEW.source_id;
END;

CREATE VIEW tool_calls AS
SELECT
    'tool_' || lower(hex(facts.tool_call_id)) AS tool_call_id,
    facts.upstream_call_id_hash,
    sources.source_id,
    threads.thread_id,
    turns.turn_id,
    CASE
        WHEN nearest.model_call_id IS NULL THEN NULL
        ELSE 'call_' || lower(hex(nearest.model_call_id))
    END AS nearest_model_call_id,
    tool_profiles.tool_name,
    NULLIF(tool_profiles.server_name_key, '') AS server_name,
    NULLIF(tool_profiles.namespace_key, '') AS namespace,
    tool_profiles.tool_category,
    facts.started_at,
    facts.ended_at,
    facts.duration_ms,
    facts.status,
    facts.error_category,
    facts.output_bytes,
    facts.argument_shape,
    facts.first_source_offset,
    facts.last_source_offset,
    facts.generation,
    facts.observation_confidence,
    tool_profiles.operation,
    facts.target_label
FROM tool_call_facts AS facts
JOIN sources USING (source_key)
JOIN threads USING (thread_key)
LEFT JOIN turns USING (turn_key)
JOIN tool_profiles USING (tool_profile_key)
LEFT JOIN model_call_facts AS nearest
    ON nearest.model_call_key = facts.nearest_model_call_key;

CREATE VIEW activity_events AS
SELECT
    'act_' || lower(hex(facts.activity_event_id)) AS activity_event_id,
    sources.source_id,
    threads.thread_id,
    turns.turn_id,
    facts.event_kind,
    facts.event_at,
    facts.safe_label,
    facts.category,
    facts.source_offset,
    facts.generation
FROM activity_facts AS facts
JOIN sources USING (source_key)
JOIN threads USING (thread_key)
LEFT JOIN turns USING (turn_key);

CREATE VIEW allowance_observations AS
SELECT
    'allow_' || lower(hex(states.allowance_observation_id))
        AS allowance_observation_id,
    sources.source_id,
    states.last_observed_at AS observed_at,
    states.window_kind,
    states.limit_id,
    states.plan_type,
    states.used_percent,
    states.duration_minutes,
    states.resets_at,
    states.model,
    states.service_tier,
    CASE
        WHEN trigger_call.model_call_id IS NULL THEN NULL
        ELSE 'call_' || lower(hex(trigger_call.model_call_id))
    END AS source_model_call_id,
    states.generation,
    states.duplicate_state,
    states.provenance,
    states.validation_warnings,
    states.allowance_state_key,
    states.first_observed_at,
    states.last_observed_at,
    states.observation_count,
    states.observation_trigger_call_key
FROM allowance_states AS states
JOIN sources USING (source_key)
LEFT JOIN model_call_facts AS trigger_call
    ON trigger_call.model_call_key = states.observation_trigger_call_key;

CREATE TRIGGER insert_allowance_observations
INSTEAD OF INSERT ON allowance_observations
BEGIN
    INSERT INTO allowance_states(
        allowance_observation_id,
        source_key,
        first_observed_at,
        last_observed_at,
        observation_count,
        window_kind,
        limit_id,
        plan_type,
        used_percent,
        duration_minutes,
        resets_at,
        model,
        service_tier,
        observation_trigger_call_key,
        generation,
        duplicate_state,
        provenance,
        validation_warnings
    )
    SELECT
        unhex(substr(NEW.allowance_observation_id, 7)),
        sources.source_key,
        NEW.observed_at,
        NEW.observed_at,
        1,
        NEW.window_kind,
        NEW.limit_id,
        NEW.plan_type,
        NEW.used_percent,
        NEW.duration_minutes,
        NEW.resets_at,
        NEW.model,
        NEW.service_tier,
        model_call_facts.model_call_key,
        NEW.generation,
        NEW.duplicate_state,
        NEW.provenance,
        NEW.validation_warnings
    FROM sources
    LEFT JOIN model_call_facts
        ON model_call_facts.model_call_id = unhex(
            substr(NEW.source_model_call_id, 6)
        )
    WHERE sources.source_id = NEW.source_id;
END;

CREATE VIEW allowance_intervals AS
WITH ordered AS (
    SELECT
        allowance_observations.*,
        LAG(allowance_state_key) OVER observation_window
            AS previous_state_key,
        LAG(observed_at) OVER observation_window AS previous_observed_at,
        LAG(used_percent) OVER observation_window AS previous_used_percent,
        LAG(duration_minutes) OVER observation_window
            AS previous_duration_minutes,
        LAG(resets_at) OVER observation_window AS previous_resets_at
    FROM allowance_observations
    WHERE duplicate_state = 'canonical'
      AND generation <= (
          SELECT COALESCE(MAX(generation), 0)
          FROM generations
          WHERE integrity_status = 'valid'
      )
    WINDOW observation_window AS (
        PARTITION BY
            window_kind,
            COALESCE(limit_id, ''),
            COALESCE(plan_type, '')
        ORDER BY observed_at, allowance_state_key
    )
),
deltas AS (
    SELECT
        ordered.*,
        CASE
            WHEN previous_state_key IS NOT NULL
             AND previous_resets_at IS resets_at
             AND previous_duration_minutes IS duration_minutes
             AND julianday(observed_at) > julianday(previous_observed_at)
             AND (
                 duration_minutes IS NULL
                 OR (
                     julianday(observed_at) - julianday(previous_observed_at)
                 ) * 1440.0 <= duration_minutes
             )
             AND used_percent > previous_used_percent
            THEN used_percent - previous_used_percent
            ELSE NULL
        END AS delta_used_percent,
        CASE
            WHEN previous_state_key IS NOT NULL
             AND previous_resets_at IS resets_at
             AND previous_duration_minutes IS duration_minutes
             AND julianday(observed_at) > julianday(previous_observed_at)
             AND (
                 duration_minutes IS NULL
                 OR (
                     julianday(observed_at) - julianday(previous_observed_at)
                 ) * 1440.0 <= duration_minutes
             )
             AND used_percent > previous_used_percent
            THEN (
                julianday(observed_at) - julianday(previous_observed_at)
            ) * 24.0
            ELSE NULL
        END AS elapsed_hours
    FROM ordered
),
local_facts AS (
    SELECT
        deltas.*,
        COALESCE((
            SELECT COUNT(*)
            FROM model_call_facts
            WHERE model_call_facts.duplicate_state = 'canonical'
              AND julianday(model_call_facts.event_at)
                    > julianday(deltas.previous_observed_at)
              AND julianday(model_call_facts.event_at)
                    <= julianday(deltas.observed_at)
        ), 0) AS local_calls,
        COALESCE((
            SELECT COUNT(DISTINCT model_call_facts.turn_key)
            FROM model_call_facts
            WHERE model_call_facts.duplicate_state = 'canonical'
              AND julianday(model_call_facts.event_at)
                    > julianday(deltas.previous_observed_at)
              AND julianday(model_call_facts.event_at)
                    <= julianday(deltas.observed_at)
        ), 0) AS local_turns,
        COALESCE((
            SELECT SUM(
                model_call_facts.input_tokens
                + model_call_facts.output_tokens
            )
            FROM model_call_facts
            WHERE model_call_facts.duplicate_state = 'canonical'
              AND julianday(model_call_facts.event_at)
                    > julianday(deltas.previous_observed_at)
              AND julianday(model_call_facts.event_at)
                    <= julianday(deltas.observed_at)
        ), 0) AS local_total_tokens
    FROM deltas
)
SELECT
    local_facts.*,
    100.0 - used_percent AS remaining_percent,
    CASE
        WHEN delta_used_percent IS NULL THEN NULL
        ELSE delta_used_percent / elapsed_hours
    END AS percentage_points_per_hour,
    CASE
        WHEN delta_used_percent IS NULL THEN NULL
        ELSE 1.0 * local_total_tokens / delta_used_percent
    END AS local_tokens_per_percentage_point,
    CASE
        WHEN delta_used_percent IS NULL THEN NULL
        ELSE 1.0 * local_calls / delta_used_percent
    END AS local_calls_per_percentage_point,
    CASE
        WHEN delta_used_percent IS NULL THEN NULL
        ELSE 1.0 * local_turns / delta_used_percent
    END AS local_turns_per_percentage_point
FROM local_facts;
"""


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the deterministic analytical schema on an empty connection."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.executescript(_SCHEMA_SQL)


def drop_secondary_indexes(connection: sqlite3.Connection) -> None:
    """Remove query indexes while an unpublished cold build is loading."""

    for name in SECONDARY_INDEX_SQL:
        connection.execute(f"DROP INDEX IF EXISTS {name}")


def create_secondary_indexes(connection: sqlite3.Connection) -> None:
    """Restore every query index before an analytical artifact is published."""

    for statement in SECONDARY_INDEX_SQL.values():
        connection.execute(statement)
