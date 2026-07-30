CREATE TABLE operational_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT, WITHOUT ROWID;

CREATE TABLE operation_jobs (
  operation_id TEXT PRIMARY KEY,
  request_sha256 TEXT NOT NULL
    CHECK (
      length(request_sha256) = 64
      AND request_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  compatibility_key TEXT NOT NULL,
  parent_publication_id TEXT,
  operation_class TEXT NOT NULL
    CHECK (
      operation_class IN (
        'no_change',
        'append_safe_small',
        'append_safe_large',
        'valuation_only',
        'source_replace',
        'recanonicalize',
        'schema_upgrade',
        'projection_upgrade',
        'history_expand'
      )
    ),
  state TEXT NOT NULL
    CHECK (
      state IN (
        'planned',
        'parsing',
        'ready_to_write',
        'writing',
        'building',
        'catching_up',
        'validating',
        'promoting',
        'reconciling',
        'recovery_required',
        'completed',
        'failed',
        'rolled_back'
      )
    ),
  stage TEXT NOT NULL,
  created_at_us INTEGER NOT NULL,
  updated_at_us INTEGER NOT NULL,
  progress_numerator INTEGER
    CHECK (progress_numerator IS NULL OR progress_numerator >= 0),
  progress_denominator INTEGER
    CHECK (progress_denominator IS NULL OR progress_denominator >= 0),
  progress_basis TEXT,
  worker_pid INTEGER CHECK (worker_pid IS NULL OR worker_pid > 0),
  worker_start_token TEXT,
  heartbeat_at_us INTEGER,
  candidate_artifact_name TEXT,
  candidate_artifact_sha256 TEXT
    CHECK (
      candidate_artifact_sha256 IS NULL
      OR (
        length(candidate_artifact_sha256) = 64
        AND candidate_artifact_sha256 NOT GLOB '*[^0-9a-f]*'
      )
    ),
  terminal_publication_id TEXT,
  error_code TEXT,
  error_detail TEXT,
  CHECK (created_at_us <= updated_at_us),
  CHECK (
    progress_denominator IS NULL
    OR progress_numerator IS NULL
    OR progress_numerator <= progress_denominator
  ),
  CHECK (
    (worker_pid IS NULL AND worker_start_token IS NULL)
    OR (worker_pid IS NOT NULL AND worker_start_token IS NOT NULL)
  ),
  CHECK (
    candidate_artifact_name IS NULL
    OR (
      length(candidate_artifact_name) BETWEEN 1 AND 255
      AND instr(candidate_artifact_name, '/') = 0
      AND instr(candidate_artifact_name, char(92)) = 0
      AND instr(candidate_artifact_name, '..') = 0
    )
  ),
  CHECK (error_detail IS NULL OR length(error_detail) <= 1024)
) STRICT, WITHOUT ROWID;

CREATE TABLE writer_leases (
  lease_name TEXT PRIMARY KEY
    CHECK (lease_name IN ('analytical_writer', 'artifact_promotion')),
  operation_id TEXT NOT NULL,
  owner_nonce TEXT NOT NULL,
  fencing_token INTEGER NOT NULL CHECK (fencing_token > 0),
  worker_pid INTEGER NOT NULL CHECK (worker_pid > 0),
  worker_start_token TEXT NOT NULL,
  acquired_at_us INTEGER NOT NULL,
  heartbeat_at_us INTEGER NOT NULL,
  expires_at_us INTEGER NOT NULL,
  CHECK (acquired_at_us <= heartbeat_at_us),
  CHECK (heartbeat_at_us < expires_at_us),
  FOREIGN KEY (operation_id) REFERENCES operation_jobs(operation_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE artifact_pointers (
  pointer_generation INTEGER NOT NULL CHECK (pointer_generation > 0),
  pointer_role TEXT NOT NULL CHECK (pointer_role IN ('active', 'rollback')),
  artifact_name TEXT NOT NULL,
  publication_id TEXT NOT NULL,
  artifact_manifest_sha256 TEXT NOT NULL
    CHECK (
      length(artifact_manifest_sha256) = 64
      AND artifact_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  file_sha256 TEXT
    CHECK (
      file_sha256 IS NULL
      OR (
        length(file_sha256) = 64
        AND file_sha256 NOT GLOB '*[^0-9a-f]*'
      )
    ),
  schema_contract_sha256 TEXT NOT NULL
    CHECK (
      length(schema_contract_sha256) = 64
      AND schema_contract_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  owner_operation_id TEXT NOT NULL,
  activated_at_us INTEGER NOT NULL,
  PRIMARY KEY (pointer_generation, pointer_role),
  CHECK (
    length(artifact_name) BETWEEN 1 AND 255
    AND instr(artifact_name, '/') = 0
    AND instr(artifact_name, char(92)) = 0
    AND instr(artifact_name, '..') = 0
  ),
  FOREIGN KEY (owner_operation_id)
    REFERENCES operation_jobs(operation_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE recovery_intents (
  recovery_id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL,
  expected_pointer_generation INTEGER NOT NULL
    CHECK (expected_pointer_generation >= 0),
  target_pointer_generation INTEGER NOT NULL
    CHECK (target_pointer_generation > expected_pointer_generation),
  expected_active_publication_id TEXT,
  candidate_publication_id TEXT NOT NULL,
  candidate_artifact_name TEXT NOT NULL,
  candidate_artifact_sha256 TEXT NOT NULL
    CHECK (
      length(candidate_artifact_sha256) = 64
      AND candidate_artifact_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
  state TEXT NOT NULL
    CHECK (
      state IN (
        'prepared',
        'pointer_written',
        'verified',
        'reconciled',
        'rolled_back',
        'failed'
      )
    ),
  created_at_us INTEGER NOT NULL,
  updated_at_us INTEGER NOT NULL,
  error_code TEXT,
  CHECK (created_at_us <= updated_at_us),
  CHECK (
    length(candidate_artifact_name) BETWEEN 1 AND 255
    AND instr(candidate_artifact_name, '/') = 0
    AND instr(candidate_artifact_name, char(92)) = 0
    AND instr(candidate_artifact_name, '..') = 0
  ),
  FOREIGN KEY (operation_id) REFERENCES operation_jobs(operation_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE source_dirty_hints (
  source_id TEXT NOT NULL,
  technical_path_key TEXT NOT NULL,
  first_observed_at_us INTEGER NOT NULL,
  last_observed_at_us INTEGER NOT NULL,
  observation_count INTEGER NOT NULL CHECK (observation_count > 0),
  reason_mask INTEGER NOT NULL CHECK (reason_mask > 0),
  PRIMARY KEY (source_id, technical_path_key),
  CHECK (first_observed_at_us <= last_observed_at_us)
) STRICT, WITHOUT ROWID;

CREATE UNIQUE INDEX operation_jobs_one_active_compatible
  ON operation_jobs(compatibility_key ASC)
  WHERE state IN (
    'planned',
    'parsing',
    'ready_to_write',
    'writing',
    'building',
    'catching_up',
    'validating',
    'promoting',
    'reconciling',
    'recovery_required'
  );
CREATE INDEX operation_jobs_by_state
  ON operation_jobs(state ASC, updated_at_us ASC, operation_id ASC);
CREATE INDEX operation_jobs_by_parent
  ON operation_jobs(parent_publication_id ASC, created_at_us ASC, operation_id ASC);
CREATE INDEX artifact_pointers_by_role
  ON artifact_pointers(
    pointer_role ASC,
    pointer_generation DESC,
    publication_id ASC
  );
CREATE INDEX recovery_intents_by_state
  ON recovery_intents(state ASC, updated_at_us ASC, recovery_id ASC);
CREATE INDEX source_dirty_hints_by_observed
  ON source_dirty_hints(
    last_observed_at_us ASC,
    source_id ASC,
    technical_path_key ASC
  );
