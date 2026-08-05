CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT, WITHOUT ROWID;

CREATE TABLE publications (
  publication_id TEXT PRIMARY KEY,
  parent_publication_id TEXT,
  operation_id TEXT NOT NULL UNIQUE,
  schema_contract_id TEXT NOT NULL
    CHECK (schema_contract_id = 'codex-usage-tracker.agent-kernel.schema-contract.v1'),
  schema_contract_sha256 TEXT NOT NULL
    CHECK (
      length(schema_contract_sha256) = 64
      AND schema_contract_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  identity_version TEXT NOT NULL,
  adapter_id TEXT NOT NULL,
  adapter_version TEXT NOT NULL,
  normalization_version TEXT NOT NULL,
  projection_registry_sha256 TEXT
    CHECK (
      projection_registry_sha256 IS NULL
      OR (
        length(projection_registry_sha256) = 64
        AND projection_registry_sha256 NOT GLOB '*[^0-9a-f]*'
      )
    ),
  rate_card_digest TEXT
    CHECK (
      rate_card_digest IS NULL
      OR (
        length(rate_card_digest) = 64
        AND rate_card_digest NOT GLOB '*[^0-9a-f]*'
      )
    ),
  history_preset TEXT NOT NULL
    CHECK (
      history_preset IN (
        'current_session',
        '24_hours',
        '7_days',
        '30_days',
        '90_days',
        'one_year',
        'all_time'
      )
    ),
  requested_cutoff_us INTEGER,
  committed_at_us INTEGER NOT NULL,
  observed_through_us INTEGER,
  indexed_from_us INTEGER,
  indexed_through_us INTEGER,
  guaranteed_complete_from_us INTEGER,
  artifact_manifest_sha256 TEXT NOT NULL
    CHECK (
      length(artifact_manifest_sha256) = 64
      AND artifact_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  status TEXT NOT NULL CHECK (status IN ('committed', 'rolled_back')),
  CHECK (
    indexed_from_us IS NULL
    OR indexed_through_us IS NULL
    OR indexed_from_us <= indexed_through_us
  ),
  CHECK (
    guaranteed_complete_from_us IS NULL
    OR indexed_through_us IS NULL
    OR guaranteed_complete_from_us <= indexed_through_us
  )
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_head (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  publication_id TEXT NOT NULL UNIQUE,
  activated_at_us INTEGER NOT NULL,
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE identity_registry (
  logical_id TEXT PRIMARY KEY,
  entity_kind TEXT NOT NULL,
  identity_version TEXT NOT NULL,
  identity_cbor BLOB NOT NULL,
  identity_sha256 TEXT NOT NULL
    CHECK (
      length(identity_sha256) = 64
      AND identity_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (entity_kind, identity_version, identity_sha256),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
    DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;

CREATE TABLE selector_aliases (
  alias_selector TEXT PRIMARY KEY,
  canonical_selector TEXT NOT NULL,
  logical_id TEXT NOT NULL,
  reason TEXT NOT NULL
    CHECK (reason IN ('identity_correction', 'recanonicalization')),
  first_seen_publication_id TEXT NOT NULL,
  retired_publication_id TEXT,
  CHECK (alias_selector <> canonical_selector),
  FOREIGN KEY (logical_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (retired_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE adapters (
  adapter_id TEXT PRIMARY KEY,
  adapter_version TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  capability_mask INTEGER NOT NULL CHECK (capability_mask >= 0),
  identity_version TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  FOREIGN KEY (adapter_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_producers (
  producer_id TEXT PRIMARY KEY,
  configured_producer_key TEXT NOT NULL UNIQUE,
  display_label TEXT,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  CHECK (length(configured_producer_key) > 0),
  CHECK (display_label IS NULL OR length(display_label) > 0),
  FOREIGN KEY (producer_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE sources (
  source_id TEXT PRIMARY KEY,
  adapter_id TEXT NOT NULL,
  producer_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  adapter_native_source_key TEXT NOT NULL,
  selected_history_preset TEXT NOT NULL
    CHECK (
      selected_history_preset IN (
        'current_session',
        '24_hours',
        '7_days',
        '30_days',
        '90_days',
        'one_year',
        'all_time'
      )
    ),
  selected_from_us INTEGER,
  selected_through_us INTEGER,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (
    adapter_id,
    producer_id,
    source_kind,
    adapter_native_source_key
  ),
  CHECK (length(adapter_native_source_key) > 0),
  CHECK (
    selected_from_us IS NULL
    OR selected_through_us IS NULL
    OR selected_from_us <= selected_through_us
  ),
  FOREIGN KEY (source_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (adapter_id) REFERENCES adapters(adapter_id),
  FOREIGN KEY (producer_id) REFERENCES source_producers(producer_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_manifestations (
  manifestation_id TEXT PRIMARY KEY,
  manifestation_key INTEGER NOT NULL CHECK (manifestation_key > 0),
  source_id TEXT NOT NULL,
  adapter_native_file_key TEXT NOT NULL,
  technical_path_key TEXT NOT NULL,
  display_label TEXT NOT NULL,
  filesystem_identity_json TEXT,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
  modified_at_us INTEGER,
  prefix_sha256 TEXT
    CHECK (
      prefix_sha256 IS NULL
      OR (
        length(prefix_sha256) = 64
        AND prefix_sha256 NOT GLOB '*[^0-9a-f]*'
      )
    ),
  suffix_sha256 TEXT
    CHECK (
      suffix_sha256 IS NULL
      OR (
        length(suffix_sha256) = 64
        AND suffix_sha256 NOT GLOB '*[^0-9a-f]*'
      )
    ),
  content_revision TEXT NOT NULL,
  source_rank INTEGER NOT NULL UNIQUE CHECK (source_rank >= 0),
  state TEXT NOT NULL
    CHECK (
      state IN (
        'active',
        'archived',
        'replaced',
        'truncated',
        'missing',
        'malformed',
        'deferred'
      )
    ),
  time_range_start_us INTEGER,
  time_range_end_us INTEGER,
  time_range_confidence TEXT NOT NULL
    CHECK (time_range_confidence IN ('trusted', 'uncertain', 'unavailable')),
  selected INTEGER NOT NULL CHECK (selected IN (0, 1)),
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  ended_publication_id TEXT,
  UNIQUE (source_id, adapter_native_file_key),
  CHECK (length(adapter_native_file_key) > 0),
  CHECK (
    length(technical_path_key) > 0
    AND substr(technical_path_key, 1, 1) <> '/'
    AND instr(technical_path_key, char(92)) = 0
    AND instr(technical_path_key, ':') = 0
    AND instr(technical_path_key, '//') = 0
    AND technical_path_key NOT IN ('.', '..')
    AND substr(technical_path_key, 1, 2) <> './'
    AND substr(technical_path_key, 1, 3) <> '../'
    AND instr(technical_path_key, '/./') = 0
    AND instr(technical_path_key, '/../') = 0
    AND substr(technical_path_key, -2) <> '/.'
    AND substr(technical_path_key, -3) <> '/..'
    AND substr(technical_path_key, -1) <> '/'
  ),
  CHECK (
    time_range_start_us IS NULL
    OR time_range_end_us IS NULL
    OR time_range_start_us <= time_range_end_us
  ),
  CHECK (
    time_range_confidence <> 'unavailable'
    OR (time_range_start_us IS NULL AND time_range_end_us IS NULL)
  ),
  FOREIGN KEY (manifestation_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (source_id) REFERENCES sources(source_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (ended_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_cursors (
  manifestation_key INTEGER PRIMARY KEY,
  source_revision TEXT NOT NULL,
  byte_offset INTEGER NOT NULL CHECK (byte_offset >= 0),
  record_ordinal INTEGER NOT NULL CHECK (record_ordinal >= 0),
  source_size_bytes INTEGER NOT NULL CHECK (source_size_bytes >= byte_offset),
  prefix_through_cursor_sha256 TEXT NOT NULL
    CHECK (
      length(prefix_through_cursor_sha256) = 64
      AND prefix_through_cursor_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  suffix_sha256 TEXT NOT NULL
    CHECK (
      length(suffix_sha256) = 64
      AND suffix_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  latest_source_order INTEGER NOT NULL CHECK (latest_source_order >= 0),
  parser_version TEXT NOT NULL,
  adapter_version TEXT NOT NULL,
  committed_publication_id TEXT NOT NULL,
  updated_at_us INTEGER NOT NULL,
  FOREIGN KEY (manifestation_key)
    REFERENCES source_manifestations(manifestation_key),
  FOREIGN KEY (committed_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_diagnostics (
  manifestation_key INTEGER NOT NULL,
  source_revision TEXT NOT NULL,
  byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
  byte_end INTEGER NOT NULL CHECK (byte_end > byte_start),
  diagnostic_code TEXT NOT NULL,
  record_ordinal INTEGER CHECK (record_ordinal IS NULL OR record_ordinal >= 0),
  first_seen_publication_id TEXT NOT NULL,
  PRIMARY KEY (
    manifestation_key,
    source_revision,
    byte_start,
    byte_end,
    diagnostic_code
  ),
  FOREIGN KEY (manifestation_key)
    REFERENCES source_manifestations(manifestation_key),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_occurrences (
  occurrence_id TEXT PRIMARY KEY,
  semantic_logical_id TEXT NOT NULL,
  manifestation_key INTEGER NOT NULL,
  source_revision TEXT NOT NULL,
  record_ordinal INTEGER NOT NULL CHECK (record_ordinal >= 0),
  byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
  byte_end INTEGER NOT NULL CHECK (byte_end > byte_start),
  adapter_version TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  UNIQUE (
    semantic_logical_id,
    manifestation_key,
    source_revision,
    record_ordinal,
    byte_start,
    byte_end
  ),
  FOREIGN KEY (occurrence_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (semantic_logical_id)
    REFERENCES identity_registry(logical_id),
  FOREIGN KEY (manifestation_key)
    REFERENCES source_manifestations(manifestation_key),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE selector_anchors (
  selector TEXT PRIMARY KEY,
  selector_kind TEXT NOT NULL
    CHECK (
      selector_kind IN (
        'project',
        'session',
        'turn',
        'call',
        'tool',
        'resource',
        'state-change',
        'allowance-observation',
        'allowance-interval',
        'publication'
      )
    ),
  logical_id TEXT NOT NULL,
  canonical_occurrence_id TEXT,
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  UNIQUE (selector_kind, logical_id),
  FOREIGN KEY (logical_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (canonical_occurrence_id)
    REFERENCES source_occurrences(occurrence_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  workspace_key TEXT NOT NULL UNIQUE,
  label_candidates_json TEXT NOT NULL DEFAULT '[]',
  first_event_at_us INTEGER,
  last_event_at_us INTEGER,
  provenance_json TEXT NOT NULL DEFAULT '[]',
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  CHECK (
    first_event_at_us IS NULL
    OR last_event_at_us IS NULL
    OR first_event_at_us <= last_event_at_us
  ),
  FOREIGN KEY (project_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE resources (
  resource_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  resource_kind TEXT NOT NULL
    CHECK (
      resource_kind IN (
        'file',
        'directory',
        'repository',
        'command_family',
        'url_origin_path_template',
        'mcp_tool',
        'browser_route',
        'test_target',
        'unknown'
      )
    ),
  normalized_key TEXT NOT NULL,
  normalization_version TEXT NOT NULL,
  display_label TEXT NOT NULL,
  provenance_json TEXT NOT NULL DEFAULT '[]',
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (project_id, resource_kind, normalization_version, normalized_key),
  FOREIGN KEY (resource_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (project_id) REFERENCES projects(project_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE model_profiles (
  model_profile_id TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  reasoning_effort TEXT,
  service_tier TEXT,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  FOREIGN KEY (model_profile_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  adapter_native_session_key TEXT NOT NULL,
  identity_version TEXT NOT NULL,
  project_id TEXT NOT NULL,
  root_session_id TEXT,
  parent_session_id TEXT,
  relationship_basis TEXT,
  delegation_depth INTEGER
    CHECK (delegation_depth IS NULL OR delegation_depth >= 0),
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  start_at_us INTEGER,
  end_at_us INTEGER,
  observed_duration_us INTEGER
    CHECK (observed_duration_us IS NULL OR observed_duration_us >= 0),
  completion_basis TEXT,
  label_candidates_json TEXT NOT NULL DEFAULT '[]',
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (adapter_native_session_key, identity_version),
  CHECK (
    start_at_us IS NULL
    OR end_at_us IS NULL
    OR start_at_us <= end_at_us
  ),
  FOREIGN KEY (session_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (project_id) REFERENCES projects(project_id),
  FOREIGN KEY (root_session_id) REFERENCES sessions(session_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE turns (
  turn_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal > 0),
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  start_at_us INTEGER,
  end_at_us INTEGER,
  start_source_rank INTEGER NOT NULL CHECK (start_source_rank >= 0),
  start_source_order INTEGER NOT NULL CHECK (start_source_order >= 0),
  end_source_order INTEGER CHECK (end_source_order IS NULL OR end_source_order >= 0),
  completion_basis TEXT,
  membership_json TEXT NOT NULL DEFAULT '{}',
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (session_id, ordinal),
  CHECK (
    start_at_us IS NULL
    OR end_at_us IS NULL
    OR start_at_us <= end_at_us
  ),
  CHECK (
    end_source_order IS NULL
    OR start_source_order <= end_source_order
  ),
  FOREIGN KEY (turn_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE late_parent_edges (
  child_session_id TEXT NOT NULL,
  relationship_version INTEGER NOT NULL CHECK (relationship_version > 0),
  parent_session_id TEXT NOT NULL,
  relationship_basis TEXT NOT NULL,
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  PRIMARY KEY (child_session_id, relationship_version),
  CHECK (child_session_id <> parent_session_id),
  FOREIGN KEY (child_session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (occurrence_id) REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE lifecycle_transitions (
  transition_id TEXT PRIMARY KEY,
  entity_logical_id TEXT NOT NULL,
  entity_kind TEXT NOT NULL
    CHECK (
      entity_kind IN (
        'session',
        'turn',
        'model_call',
        'tool_invocation',
        'activity'
      )
    ),
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version > 0),
  transition_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  occurrence_id TEXT NOT NULL,
  terminal_error_category TEXT,
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  first_seen_publication_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  UNIQUE (entity_logical_id, transition_version),
  FOREIGN KEY (transition_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (entity_logical_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (occurrence_id) REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE model_call_locations (
  call_id TEXT PRIMARY KEY,
  storage_class TEXT NOT NULL CHECK (storage_class IN ('base', 'tail')),
  UNIQUE (call_id, storage_class),
  FOREIGN KEY (call_id) REFERENCES identity_registry(logical_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE model_calls (
  call_id TEXT PRIMARY KEY,
  storage_class TEXT NOT NULL DEFAULT 'base' CHECK (storage_class = 'base'),
  adapter_native_call_key TEXT NOT NULL,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  model_profile_id TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  context_window_tokens INTEGER
    CHECK (context_window_tokens IS NULL OR context_window_tokens >= 0),
  uncached_input_tokens INTEGER
    CHECK (uncached_input_tokens IS NULL OR uncached_input_tokens >= 0),
  cached_input_tokens INTEGER
    CHECK (cached_input_tokens IS NULL OR cached_input_tokens >= 0),
  reasoning_tokens INTEGER
    CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
  output_tokens INTEGER
    CHECK (output_tokens IS NULL OR output_tokens >= 0),
  token_basis TEXT NOT NULL,
  finish_category TEXT,
  error_category TEXT,
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (session_id, adapter_native_call_key),
  FOREIGN KEY (call_id, storage_class)
    REFERENCES model_call_locations(call_id, storage_class),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (model_profile_id) REFERENCES model_profiles(model_profile_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE tool_invocations (
  tool_id TEXT PRIMARY KEY,
  adapter_native_invocation_key TEXT NOT NULL,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  transport_name TEXT NOT NULL,
  semantic_operation TEXT NOT NULL
    CHECK (
      semantic_operation IN (
        'read',
        'search',
        'list',
        'execute',
        'write',
        'patch',
        'test',
        'navigate',
        'delegate',
        'wait',
        'unknown'
      )
    ),
  tool_family TEXT NOT NULL,
  primary_resource_id TEXT,
  write_intent INTEGER NOT NULL CHECK (write_intent IN (0, 1)),
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  start_at_us INTEGER,
  start_source_rank INTEGER NOT NULL CHECK (start_source_rank >= 0),
  start_source_order INTEGER NOT NULL CHECK (start_source_order >= 0),
  start_event_kind_order INTEGER NOT NULL CHECK (start_event_kind_order >= 0),
  start_transition_rank INTEGER NOT NULL CHECK (start_transition_rank >= 0),
  start_occurrence_id TEXT NOT NULL,
  terminal_at_us INTEGER,
  terminal_source_rank INTEGER CHECK (terminal_source_rank IS NULL OR terminal_source_rank >= 0),
  terminal_source_order INTEGER CHECK (terminal_source_order IS NULL OR terminal_source_order >= 0),
  terminal_event_kind_order INTEGER CHECK (terminal_event_kind_order IS NULL OR terminal_event_kind_order >= 0),
  terminal_transition_rank INTEGER CHECK (terminal_transition_rank IS NULL OR terminal_transition_rank >= 0),
  terminal_occurrence_id TEXT,
  observed_duration_us INTEGER
    CHECK (observed_duration_us IS NULL OR observed_duration_us >= 0),
  output_bytes INTEGER CHECK (output_bytes IS NULL OR output_bytes >= 0),
  error_category TEXT,
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (session_id, adapter_native_invocation_key),
  CHECK (
    start_at_us IS NULL
    OR terminal_at_us IS NULL
    OR start_at_us <= terminal_at_us
  ),
  CHECK (
    terminal_occurrence_id IS NOT NULL
    OR (
      terminal_at_us IS NULL
      AND terminal_source_rank IS NULL
      AND terminal_source_order IS NULL
      AND terminal_event_kind_order IS NULL
      AND terminal_transition_rank IS NULL
    )
  ),
  FOREIGN KEY (tool_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (primary_resource_id) REFERENCES resources(resource_id),
  FOREIGN KEY (start_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (terminal_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE tool_resources (
  tool_id TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  relationship_role TEXT NOT NULL
    CHECK (
      relationship_role IN (
        'read',
        'searched',
        'listed',
        'executed',
        'written',
        'patched',
        'tested',
        'navigated',
        'delegated',
        'unknown'
      )
    ),
  occurrence_id TEXT NOT NULL,
  PRIMARY KEY (tool_id, resource_id, relationship_role),
  FOREIGN KEY (tool_id) REFERENCES tool_invocations(tool_id),
  FOREIGN KEY (resource_id) REFERENCES resources(resource_id),
  FOREIGN KEY (occurrence_id) REFERENCES source_occurrences(occurrence_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE activities (
  activity_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  turn_id TEXT,
  activity_kind TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  FOREIGN KEY (activity_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE compaction_boundaries (
  compaction_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  before_context_epoch TEXT NOT NULL,
  after_context_epoch TEXT NOT NULL,
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  CHECK (before_context_epoch <> after_context_epoch),
  FOREIGN KEY (compaction_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE context_components (
  component_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  turn_id TEXT,
  call_id TEXT,
  category TEXT NOT NULL
    CHECK (category IN (
      'assistant_message',
      'developer_instruction',
      'memory',
      'other_structural',
      'system_instruction',
      'tool_definition',
      'tool_output',
      'user_message',
      'workspace_context'
    )),
  observed_utf8_bytes INTEGER NOT NULL CHECK (observed_utf8_bytes >= 0),
  observed_event_count INTEGER NOT NULL CHECK (observed_event_count >= 0),
  estimator TEXT,
  estimated_tokens INTEGER CHECK (estimated_tokens IS NULL OR estimated_tokens >= 0),
  total_context_utf8_bytes INTEGER
    CHECK (total_context_utf8_bytes IS NULL OR total_context_utf8_bytes >= 0),
  inclusion_basis TEXT NOT NULL
    CHECK (inclusion_basis IN (
      'inclusion_unknown',
      'known_included_in_call',
      'observed_in_source',
      'selected_by_host'
    )),
  capability_basis TEXT NOT NULL,
  measurement_basis TEXT NOT NULL,
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  CHECK ((estimator IS NULL) = (estimated_tokens IS NULL)),
  FOREIGN KEY (component_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (call_id) REFERENCES model_call_locations(call_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE state_changes (
  change_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  turn_id TEXT,
  resource_id TEXT NOT NULL,
  change_kind TEXT NOT NULL,
  before_revision TEXT,
  after_revision TEXT,
  causal_attribution INTEGER NOT NULL DEFAULT 0
    CHECK (causal_attribution = 0),
  confidence TEXT NOT NULL,
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  FOREIGN KEY (change_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (resource_id) REFERENCES resources(resource_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE allowance_limits (
  limit_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  account_local_identity TEXT NOT NULL,
  plan_identity TEXT NOT NULL,
  window_kind TEXT NOT NULL,
  configured_duration_us INTEGER
    CHECK (configured_duration_us IS NULL OR configured_duration_us > 0),
  capability_basis TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  FOREIGN KEY (limit_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE allowance_cycles (
  cycle_id TEXT PRIMARY KEY,
  limit_id TEXT NOT NULL,
  reset_identity TEXT NOT NULL,
  start_at_us INTEGER,
  end_at_us INTEGER,
  reset_basis TEXT NOT NULL,
  completion_status TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (limit_id, reset_identity),
  CHECK (
    start_at_us IS NULL
    OR end_at_us IS NULL
    OR start_at_us <= end_at_us
  ),
  FOREIGN KEY (cycle_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (limit_id) REFERENCES allowance_limits(limit_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE allowance_observations (
  observation_id TEXT PRIMARY KEY,
  limit_id TEXT NOT NULL,
  cycle_id TEXT NOT NULL,
  plan_identity TEXT NOT NULL,
  window_kind TEXT NOT NULL,
  reset_identity TEXT NOT NULL,
  observation_ordinal INTEGER NOT NULL CHECK (observation_ordinal > 0),
  used_percent TEXT,
  remaining_percent TEXT,
  absolute_fields_json TEXT NOT NULL DEFAULT '{}',
  reset_time_us INTEGER,
  observed_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  UNIQUE (cycle_id, observation_ordinal),
  CHECK (
    used_percent IS NOT NULL
    OR remaining_percent IS NOT NULL
    OR absolute_fields_json <> '{}'
  ),
  FOREIGN KEY (observation_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (limit_id) REFERENCES allowance_limits(limit_id),
  FOREIGN KEY (cycle_id) REFERENCES allowance_cycles(cycle_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE allowance_intervals (
  interval_id TEXT PRIMARY KEY,
  limit_id TEXT NOT NULL,
  cycle_id TEXT NOT NULL,
  start_observation_id TEXT NOT NULL,
  end_observation_id TEXT NOT NULL,
  start_us INTEGER NOT NULL,
  end_us INTEGER NOT NULL,
  percent_delta TEXT,
  compatibility_basis TEXT NOT NULL,
  ratio_eligible INTEGER NOT NULL CHECK (ratio_eligible IN (0, 1)),
  coverage_json TEXT NOT NULL DEFAULT '{}',
  first_seen_publication_id TEXT NOT NULL,
  UNIQUE (start_observation_id, end_observation_id),
  CHECK (start_us <= end_us),
  CHECK (start_observation_id <> end_observation_id),
  FOREIGN KEY (interval_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (limit_id) REFERENCES allowance_limits(limit_id),
  FOREIGN KEY (cycle_id) REFERENCES allowance_cycles(cycle_id),
  FOREIGN KEY (start_observation_id)
    REFERENCES allowance_observations(observation_id),
  FOREIGN KEY (end_observation_id)
    REFERENCES allowance_observations(observation_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE rate_card_revisions (
  rate_card_id TEXT PRIMARY KEY,
  digest TEXT NOT NULL UNIQUE
    CHECK (length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*'),
  predecessor_rate_card_id TEXT,
  source_name TEXT NOT NULL,
  source_url TEXT,
  effective_at_us INTEGER NOT NULL,
  fetched_at_us INTEGER NOT NULL,
  currency TEXT NOT NULL,
  model_match_rules_json TEXT NOT NULL,
  four_class_rates_json TEXT NOT NULL,
  credit_rates_json TEXT NOT NULL,
  reasoning_in_output INTEGER NOT NULL CHECK (reasoning_in_output IN (0, 1)),
  confidence TEXT NOT NULL,
  validation_status TEXT NOT NULL
    CHECK (validation_status IN ('valid', 'invalid')),
  first_seen_publication_id TEXT NOT NULL,
  CHECK (
    predecessor_rate_card_id IS NULL
    OR predecessor_rate_card_id <> rate_card_id
  ),
  FOREIGN KEY (rate_card_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (predecessor_rate_card_id)
    REFERENCES rate_card_revisions(rate_card_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE active_rate_card (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  rate_card_id TEXT NOT NULL UNIQUE,
  selected_at_us INTEGER NOT NULL,
  publication_id TEXT NOT NULL,
  FOREIGN KEY (rate_card_id) REFERENCES rate_card_revisions(rate_card_id),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_source_coverage (
  publication_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  selected_manifestation_count INTEGER NOT NULL
    CHECK (selected_manifestation_count >= 0),
  selected_manifestation_bytes INTEGER NOT NULL
    CHECK (selected_manifestation_bytes >= 0),
  deferred_manifestation_count INTEGER NOT NULL
    CHECK (deferred_manifestation_count >= 0),
  deferred_manifestation_bytes INTEGER NOT NULL
    CHECK (deferred_manifestation_bytes >= 0),
  malformed_manifestation_count INTEGER NOT NULL
    CHECK (malformed_manifestation_count >= 0),
  malformed_manifestation_bytes INTEGER NOT NULL
    CHECK (malformed_manifestation_bytes >= 0),
  missing_manifestation_count INTEGER NOT NULL
    CHECK (missing_manifestation_count >= 0),
  missing_manifestation_bytes INTEGER NOT NULL
    CHECK (missing_manifestation_bytes >= 0),
  uncertain_manifestation_count INTEGER NOT NULL
    CHECK (uncertain_manifestation_count >= 0),
  uncertain_manifestation_bytes INTEGER NOT NULL
    CHECK (uncertain_manifestation_bytes >= 0),
  malformed_range_count INTEGER NOT NULL CHECK (malformed_range_count >= 0),
  malformed_range_bytes INTEGER NOT NULL CHECK (malformed_range_bytes >= 0),
  selected_complete_record_count INTEGER NOT NULL
    CHECK (selected_complete_record_count >= 0),
  tail_pending INTEGER NOT NULL CHECK (tail_pending IN (0, 1)),
  indexed_from_us INTEGER,
  indexed_through_us INTEGER,
  guaranteed_complete_from_us INTEGER,
  guaranteed_complete_through_us INTEGER,
  clock_quality TEXT NOT NULL
    CHECK (clock_quality IN ('unknown', 'unsynchronized', 'bounded')),
  clock_uncertainty_us INTEGER
    CHECK (clock_uncertainty_us IS NULL OR clock_uncertainty_us >= 0),
  inventory_started_at_us INTEGER NOT NULL,
  inventory_completed_at_us INTEGER NOT NULL,
  PRIMARY KEY (publication_id, source_id),
  CHECK (
    (
      indexed_from_us IS NULL
      AND indexed_through_us IS NULL
    )
    OR (
      indexed_from_us IS NOT NULL
      AND indexed_through_us IS NOT NULL
      AND indexed_from_us <= indexed_through_us
    )
  ),
  CHECK (
    (
      guaranteed_complete_from_us IS NULL
      AND guaranteed_complete_through_us IS NULL
    )
    OR (
      guaranteed_complete_from_us IS NOT NULL
      AND guaranteed_complete_through_us IS NOT NULL
      AND guaranteed_complete_from_us <= guaranteed_complete_through_us
    )
  ),
  CHECK (
    guaranteed_complete_from_us IS NULL
    OR (
      indexed_from_us IS NOT NULL
      AND indexed_through_us IS NOT NULL
      AND indexed_from_us <= guaranteed_complete_from_us
      AND guaranteed_complete_through_us <= indexed_through_us
    )
  ),
  CHECK (
    (
      clock_quality = 'bounded'
      AND clock_uncertainty_us IS NOT NULL
    )
    OR (
      clock_quality <> 'bounded'
      AND clock_uncertainty_us IS NULL
    )
  ),
  CHECK (inventory_started_at_us <= inventory_completed_at_us),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
  FOREIGN KEY (source_id) REFERENCES sources(source_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_capability_coverage (
  publication_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  eligible_entity_count INTEGER NOT NULL CHECK (eligible_entity_count >= 0),
  observed_entity_count INTEGER NOT NULL CHECK (observed_entity_count >= 0),
  unavailable_entity_count INTEGER NOT NULL CHECK (unavailable_entity_count >= 0),
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  grade TEXT NOT NULL
    CHECK (grade IN ('exact', 'deterministic', 'configured_estimate')),
  basis TEXT NOT NULL,
  PRIMARY KEY (publication_id, capability_id),
  CHECK (observed_entity_count <= eligible_entity_count),
  CHECK (unavailable_entity_count <= eligible_entity_count),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_entity_counts (
  publication_id TEXT NOT NULL,
  entity_kind TEXT NOT NULL,
  entity_count INTEGER NOT NULL CHECK (entity_count >= 0),
  PRIMARY KEY (publication_id, entity_kind),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_deltas (
  publication_id TEXT PRIMARY KEY,
  parent_publication_id TEXT,
  inserted_count INTEGER NOT NULL CHECK (inserted_count >= 0),
  corrected_count INTEGER NOT NULL CHECK (corrected_count >= 0),
  terminalized_count INTEGER NOT NULL CHECK (terminalized_count >= 0),
  recanonicalized_count INTEGER NOT NULL CHECK (recanonicalized_count >= 0),
  removed_count INTEGER NOT NULL CHECK (removed_count >= 0),
  uncached_input_token_delta INTEGER,
  cached_input_token_delta INTEGER,
  reasoning_token_delta INTEGER,
  output_token_delta INTEGER,
  affected_session_count INTEGER NOT NULL CHECK (affected_session_count >= 0),
  affected_turn_count INTEGER NOT NULL CHECK (affected_turn_count >= 0),
  affected_tool_count INTEGER NOT NULL CHECK (affected_tool_count >= 0),
  affected_resource_count INTEGER NOT NULL CHECK (affected_resource_count >= 0),
  affected_state_change_count INTEGER NOT NULL CHECK (affected_state_change_count >= 0),
  affected_allowance_observation_count INTEGER NOT NULL
    CHECK (affected_allowance_observation_count >= 0),
  source_coverage_changed INTEGER NOT NULL
    CHECK (source_coverage_changed IN (0, 1)),
  sample_truncated INTEGER NOT NULL CHECK (sample_truncated IN (0, 1)),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_delta_entities (
  publication_id TEXT NOT NULL,
  entity_kind TEXT NOT NULL,
  inserted_count INTEGER NOT NULL CHECK (inserted_count >= 0),
  corrected_count INTEGER NOT NULL CHECK (corrected_count >= 0),
  terminalized_count INTEGER NOT NULL CHECK (terminalized_count >= 0),
  recanonicalized_count INTEGER NOT NULL CHECK (recanonicalized_count >= 0),
  removed_count INTEGER NOT NULL CHECK (removed_count >= 0),
  PRIMARY KEY (publication_id, entity_kind),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE publication_delta_samples (
  publication_id TEXT NOT NULL,
  sample_ordinal INTEGER NOT NULL CHECK (sample_ordinal > 0),
  selector TEXT NOT NULL,
  change_kind TEXT NOT NULL
    CHECK (
      change_kind IN (
        'inserted',
        'corrected',
        'terminalized',
        'recanonicalized',
        'removed'
      )
    ),
  PRIMARY KEY (publication_id, sample_ordinal),
  FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE model_call_tail_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  row_count INTEGER NOT NULL CHECK (row_count BETWEEN 0 AND 32000),
  minimum_event_at_us INTEGER,
  maximum_event_at_us INTEGER,
  maximum_source_order INTEGER,
  base_publication_id TEXT NOT NULL,
  last_fold_publication_id TEXT NOT NULL,
  CHECK (
    minimum_event_at_us IS NULL
    OR maximum_event_at_us IS NULL
    OR minimum_event_at_us <= maximum_event_at_us
  ),
  FOREIGN KEY (base_publication_id) REFERENCES publications(publication_id),
  FOREIGN KEY (last_fold_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE model_call_tail (
  call_id TEXT PRIMARY KEY,
  storage_class TEXT NOT NULL DEFAULT 'tail' CHECK (storage_class = 'tail'),
  tail_ordinal INTEGER NOT NULL UNIQUE CHECK (tail_ordinal BETWEEN 1 AND 32000),
  adapter_native_call_key TEXT NOT NULL,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  model_profile_id TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL
    CHECK (
      lifecycle_state IN (
        'pending',
        'running',
        'succeeded',
        'failed',
        'cancelled',
        'rolled_back',
        'open',
        'unknown'
      )
    ),
  state_basis TEXT NOT NULL,
  transition_version INTEGER NOT NULL CHECK (transition_version >= 0),
  event_at_us INTEGER,
  source_rank INTEGER NOT NULL CHECK (source_rank >= 0),
  source_order INTEGER NOT NULL CHECK (source_order >= 0),
  event_kind_order INTEGER NOT NULL CHECK (event_kind_order >= 0),
  transition_rank INTEGER NOT NULL CHECK (transition_rank >= 0),
  context_window_tokens INTEGER
    CHECK (context_window_tokens IS NULL OR context_window_tokens >= 0),
  uncached_input_tokens INTEGER
    CHECK (uncached_input_tokens IS NULL OR uncached_input_tokens >= 0),
  cached_input_tokens INTEGER
    CHECK (cached_input_tokens IS NULL OR cached_input_tokens >= 0),
  reasoning_tokens INTEGER
    CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),
  output_tokens INTEGER
    CHECK (output_tokens IS NULL OR output_tokens >= 0),
  token_basis TEXT NOT NULL,
  finish_category TEXT,
  error_category TEXT,
  measurement_mask INTEGER NOT NULL CHECK (measurement_mask >= 0),
  primary_occurrence_id TEXT NOT NULL,
  first_seen_publication_id TEXT NOT NULL,
  last_seen_publication_id TEXT NOT NULL,
  UNIQUE (session_id, adapter_native_call_key),
  FOREIGN KEY (call_id, storage_class)
    REFERENCES model_call_locations(call_id, storage_class),
  FOREIGN KEY (session_id) REFERENCES sessions(session_id),
  FOREIGN KEY (turn_id) REFERENCES turns(turn_id),
  FOREIGN KEY (model_profile_id) REFERENCES model_profiles(model_profile_id),
  FOREIGN KEY (primary_occurrence_id)
    REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id),
  FOREIGN KEY (last_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;

CREATE VIEW model_calls_visible AS
SELECT
  call_id,
  adapter_native_call_key,
  session_id,
  turn_id,
  model_profile_id,
  lifecycle_state,
  state_basis,
  transition_version,
  event_at_us,
  source_rank,
  source_order,
  event_kind_order,
  transition_rank,
  context_window_tokens,
  uncached_input_tokens,
  cached_input_tokens,
  reasoning_tokens,
  output_tokens,
  token_basis,
  finish_category,
  error_category,
  measurement_mask,
  primary_occurrence_id,
  first_seen_publication_id,
  last_seen_publication_id
FROM model_calls
UNION ALL
SELECT
  call_id,
  adapter_native_call_key,
  session_id,
  turn_id,
  model_profile_id,
  lifecycle_state,
  state_basis,
  transition_version,
  event_at_us,
  source_rank,
  source_order,
  event_kind_order,
  transition_rank,
  context_window_tokens,
  uncached_input_tokens,
  cached_input_tokens,
  reasoning_tokens,
  output_tokens,
  token_basis,
  finish_category,
  error_category,
  measurement_mask,
  primary_occurrence_id,
  first_seen_publication_id,
  last_seen_publication_id
FROM model_call_tail;

CREATE INDEX sources_by_producer
  ON sources(
    producer_id ASC,
    adapter_id ASC,
    source_kind ASC,
    adapter_native_source_key ASC,
    source_id ASC
  );
CREATE UNIQUE INDEX source_manifestations_by_occurrence_key
  ON source_manifestations(manifestation_key ASC);
CREATE INDEX source_manifestations_by_identity
  ON source_manifestations(manifestation_id ASC, content_revision ASC);
CREATE INDEX source_manifestations_by_technical_path
  ON source_manifestations(
    source_id ASC,
    technical_path_key ASC,
    state ASC,
    manifestation_id ASC
  );
CREATE INDEX source_manifestations_by_state
  ON source_manifestations(state ASC, selected ASC, source_rank ASC);
CREATE INDEX source_diagnostics_by_manifestation
  ON source_diagnostics(
    manifestation_key ASC,
    source_revision ASC,
    byte_start ASC,
    byte_end ASC,
    diagnostic_code ASC
  );
CREATE INDEX source_occurrences_by_logical_id
  ON source_occurrences(
    semantic_logical_id ASC,
    manifestation_key ASC,
    source_revision ASC,
    record_ordinal ASC,
    byte_start ASC,
    occurrence_id ASC
  );
CREATE INDEX selector_anchors_timeline
  ON selector_anchors(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    logical_id ASC,
    transition_rank ASC
  );
CREATE INDEX selector_anchors_by_logical_id
  ON selector_anchors(logical_id ASC, selector_kind ASC, selector ASC);
CREATE INDEX sessions_start_timeline
  ON sessions(
    (start_at_us IS NULL) ASC,
    start_at_us ASC,
    session_id ASC
  );
CREATE INDEX sessions_terminal_timeline
  ON sessions(end_at_us ASC, session_id ASC)
  WHERE end_at_us IS NOT NULL;
CREATE INDEX sessions_by_parent
  ON sessions(parent_session_id ASC, session_id ASC);
CREATE INDEX sessions_by_root
  ON sessions(root_session_id ASC, session_id ASC);
CREATE INDEX turns_timeline
  ON turns(
    (start_at_us IS NULL) ASC,
    start_at_us ASC,
    session_id ASC,
    ordinal ASC,
    turn_id ASC
  );
CREATE INDEX turns_by_session
  ON turns(session_id ASC, ordinal ASC, turn_id ASC);
CREATE INDEX late_parent_edges_timeline
  ON late_parent_edges(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    child_session_id ASC,
    transition_rank ASC
  );
CREATE INDEX late_parent_edges_by_parent
  ON late_parent_edges(
    parent_session_id ASC,
    child_session_id ASC,
    relationship_version ASC
  );
CREATE INDEX lifecycle_transitions_timeline
  ON lifecycle_transitions(
    (transition_at_us IS NULL) ASC,
    transition_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    entity_logical_id ASC,
    transition_rank ASC
  );
CREATE INDEX lifecycle_transitions_by_entity
  ON lifecycle_transitions(
    entity_logical_id ASC,
    transition_version ASC,
    transition_id ASC
  );
CREATE INDEX model_calls_timeline
  ON model_calls(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC,
    transition_rank ASC
  );
CREATE INDEX model_calls_by_session
  ON model_calls(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC
  );
CREATE INDEX tools_start_timeline
  ON tool_invocations(
    (start_at_us IS NULL) ASC,
    start_at_us ASC,
    start_source_rank ASC,
    start_source_order ASC,
    start_event_kind_order ASC,
    tool_id ASC,
    start_transition_rank ASC
  );
CREATE INDEX tools_pending_start
  ON tool_invocations(
    (start_at_us IS NULL) ASC,
    start_at_us ASC,
    start_source_rank ASC,
    start_source_order ASC,
    tool_id ASC
  )
  WHERE terminal_occurrence_id IS NULL;
CREATE INDEX tools_terminal_timeline
  ON tool_invocations(
    terminal_at_us ASC,
    terminal_source_rank ASC,
    terminal_source_order ASC,
    terminal_event_kind_order ASC,
    tool_id ASC,
    terminal_transition_rank ASC
  )
  WHERE terminal_occurrence_id IS NOT NULL;
CREATE INDEX tools_by_session
  ON tool_invocations(session_id ASC, start_source_order ASC, tool_id ASC);
CREATE INDEX tools_by_resource
  ON tool_invocations(
    primary_resource_id ASC,
    start_source_order ASC,
    tool_id ASC
  )
  WHERE primary_resource_id IS NOT NULL;
CREATE INDEX tools_by_family
  ON tool_invocations(
    transport_name ASC,
    semantic_operation ASC,
    start_source_order ASC,
    tool_id ASC
  );
CREATE INDEX tool_resources_by_resource
  ON tool_resources(
    resource_id ASC,
    relationship_role ASC,
    tool_id ASC
  );
CREATE INDEX activities_timeline
  ON activities(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    activity_id ASC,
    transition_rank ASC
  );
CREATE INDEX activities_by_session
  ON activities(session_id ASC, source_order ASC, activity_id ASC);
CREATE INDEX state_changes_timeline
  ON state_changes(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    change_id ASC,
    transition_rank ASC
  );
CREATE INDEX state_changes_by_session
  ON state_changes(session_id ASC, source_order ASC, change_id ASC);
CREATE INDEX state_changes_by_resource
  ON state_changes(resource_id ASC, source_order ASC, change_id ASC);
CREATE INDEX compactions_timeline
  ON compaction_boundaries(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    compaction_id ASC,
    transition_rank ASC
  );
CREATE INDEX compactions_by_session
  ON compaction_boundaries(session_id ASC, source_order ASC, compaction_id ASC);
CREATE INDEX context_components_timeline
  ON context_components(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    component_id ASC,
    transition_rank ASC
  );
CREATE INDEX allowance_observations_timeline
  ON allowance_observations(
    (observed_at_us IS NULL) ASC,
    observed_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    observation_id ASC,
    transition_rank ASC
  );
CREATE INDEX allowance_observations_by_compatibility
  ON allowance_observations(
    limit_id ASC,
    plan_identity ASC,
    window_kind ASC,
    cycle_id ASC,
    reset_identity ASC,
    (observed_at_us IS NULL) ASC,
    observed_at_us ASC,
    observation_id ASC
  );
CREATE INDEX allowance_intervals_timeline
  ON allowance_intervals(
    start_us ASC,
    end_us ASC,
    interval_id ASC
  );
CREATE INDEX allowance_intervals_by_cycle
  ON allowance_intervals(cycle_id ASC, start_us ASC, interval_id ASC);
CREATE INDEX publication_source_coverage_by_source
  ON publication_source_coverage(source_id ASC, publication_id ASC);
CREATE INDEX publication_delta_samples_by_selector
  ON publication_delta_samples(
    selector ASC,
    publication_id ASC,
    sample_ordinal ASC
  );
CREATE INDEX model_call_tail_timeline
  ON model_call_tail(
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC,
    transition_rank ASC
  );
CREATE INDEX model_call_tail_by_session
  ON model_call_tail(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    event_at_us ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC
  );

-- CK-08R3A evidence pages use the persisted seven-part order tuple.  Each
-- branch has a covering session/order index so filtering and LIMIT + 1 happen
-- before row decoding; turn boundary constants remain event_kind_order=20 and
-- transition_rank=0 while source rank/order are persisted coordinates.
CREATE INDEX evidence_model_calls_by_session_order
  ON model_calls(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_model_call_tail_by_session_order
  ON model_call_tail(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    call_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_tools_by_session_order
  ON tool_invocations(
    session_id ASC,
    (start_at_us IS NULL) ASC,
    COALESCE(start_at_us, 0) ASC,
    start_source_rank ASC,
    start_source_order ASC,
    start_event_kind_order ASC,
    tool_id ASC,
    start_transition_rank ASC
  );
CREATE INDEX evidence_activities_by_session_order
  ON activities(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    activity_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_state_changes_by_session_order
  ON state_changes(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    change_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_compactions_by_session_order
  ON compaction_boundaries(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    compaction_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_context_components_by_session_order
  ON context_components(
    session_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    component_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_turns_by_session_order
  ON turns(
    session_id ASC,
    (start_at_us IS NULL) ASC,
    COALESCE(start_at_us, 0) ASC,
    start_source_rank ASC,
    start_source_order ASC,
    20 ASC,
    turn_id ASC,
    0 ASC
  );
CREATE INDEX evidence_lifecycle_by_session_order
  ON lifecycle_transitions(
    session_id ASC,
    (transition_at_us IS NULL) ASC,
    COALESCE(transition_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    transition_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_source_occurrences_by_logical_order
  ON source_occurrences(
    semantic_logical_id ASC,
    record_ordinal ASC,
    byte_start ASC,
    byte_end ASC,
    occurrence_id ASC
  );
CREATE INDEX evidence_tools_by_resource_order
  ON tool_invocations(
    primary_resource_id ASC,
    (start_at_us IS NULL) ASC,
    COALESCE(start_at_us, 0) ASC,
    start_source_rank ASC,
    start_source_order ASC,
    start_event_kind_order ASC,
    tool_id ASC,
    start_transition_rank ASC
  )
  WHERE primary_resource_id IS NOT NULL;
CREATE INDEX evidence_state_changes_by_resource_order
  ON state_changes(
    resource_id ASC,
    (event_at_us IS NULL) ASC,
    COALESCE(event_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    change_id ASC,
    transition_rank ASC
  );
CREATE INDEX evidence_allowance_observations_order
  ON allowance_observations(
    (observed_at_us IS NULL) ASC,
    COALESCE(observed_at_us, 0) ASC,
    source_rank ASC,
    source_order ASC,
    event_kind_order ASC,
    observation_id ASC,
    transition_rank ASC
  );
