from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

SCHEMA_ID = "codex-usage-tracker.physical-bakeoff.candidate-a.v1"
SCHEMA_VERSION = 1
ValidationMode = Literal["prepublication", "exhaustive"]
PREPUBLICATION_VALIDATION = "quick_check+foreign_key_check+schema_metadata"

# Digest of ordered, non-SQLite-owned sqlite_schema rows. An intentional DDL
# change must update this only alongside schema-contract and corruption tests.
_EXPECTED_SCHEMA_DIGEST = (
    "19b341b7c1d91c16d6ffeda9216eac7f8d95682ab45bea97ab135bb0d79146ee"
)
_HISTORY_SELECTIONS = frozenset(
    {
        "current_session",
        "24_hours",
        "7_days",
        "30_days",
        "90_days",
        "one_year",
        "all_time",
    }
)

SQLITE_SETTINGS = (
    ("cache_size", "-20000"),
    ("journal_mode", "wal"),
    ("mmap_size", "0"),
    ("page_size", "4096"),
    ("synchronous", "normal"),
    ("temp_store", "memory"),
    ("wal_autocheckpoint", "1000"),
)

_UNPUBLISHED_STAGING_SETTINGS = (
    ("page_size", "4096"),
    ("journal_mode", "off"),
    ("synchronous", "off"),
    ("cache_size", "-20000"),
    ("mmap_size", "0"),
    ("temp_store", "memory"),
)

_DDL = """
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT, WITHOUT ROWID;

CREATE TABLE publications (
    publication_id TEXT PRIMARY KEY,
    parent_publication_id TEXT,
    fixture_manifest_digest TEXT NOT NULL,
    fixture_oracle_digest TEXT NOT NULL,
    committed_at_us INTEGER NOT NULL,
    observed_through_us INTEGER,
    status TEXT NOT NULL CHECK (status IN ('committed', 'rolled_back'))
) STRICT, WITHOUT ROWID;

CREATE TABLE source_manifestations (
    source_path TEXT PRIMARY KEY,
    occurrence_source_key INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_rank INTEGER NOT NULL,
    state TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL,
    logical_source TEXT NOT NULL,
    duplicate_of TEXT,
    selected INTEGER NOT NULL CHECK (selected IN (0, 1)),
    UNIQUE (source_rank, occurrence_source_key)
) STRICT, WITHOUT ROWID;
CREATE UNIQUE INDEX source_manifestations_by_occurrence_key
    ON source_manifestations(occurrence_source_key);
CREATE INDEX source_manifestations_by_identity
    ON source_manifestations(manifestation_id, revision, source_path);

CREATE TABLE source_diagnostics (
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    diagnostic_code TEXT NOT NULL,
    PRIMARY KEY (source_path, record_ordinal)
) STRICT, WITHOUT ROWID;

CREATE TABLE selector_anchors (
    selector TEXT PRIMARY KEY,
    selector_kind TEXT NOT NULL,
    logical_id TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX selector_anchors_timeline
    ON selector_anchors(
        event_at_us, source_rank, source_order, event_kind_order, logical_id
    );
CREATE INDEX selector_anchors_by_logical_id
    ON selector_anchors(logical_id, selector_kind);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT,
    parent_session_id TEXT,
    state TEXT NOT NULL,
    start_at_us INTEGER NOT NULL,
    start_source_rank INTEGER NOT NULL,
    start_source_order INTEGER NOT NULL,
    start_event_kind_order INTEGER NOT NULL,
    start_manifestation_id TEXT NOT NULL,
    start_source_revision TEXT NOT NULL,
    start_adapter_version TEXT NOT NULL,
    start_source_path TEXT NOT NULL,
    start_record_ordinal INTEGER NOT NULL,
    start_byte_start INTEGER NOT NULL,
    start_byte_end INTEGER NOT NULL,
    terminal_at_us INTEGER,
    terminal_source_rank INTEGER,
    terminal_source_order INTEGER,
    terminal_event_kind_order INTEGER,
    terminal_manifestation_id TEXT,
    terminal_source_revision TEXT,
    terminal_adapter_version TEXT,
    terminal_source_path TEXT,
    terminal_record_ordinal INTEGER,
    terminal_byte_start INTEGER,
    terminal_byte_end INTEGER,
    completion_basis TEXT
) STRICT, WITHOUT ROWID;
CREATE INDEX sessions_start_timeline
    ON sessions(
        start_at_us, start_source_rank, start_source_order,
        start_event_kind_order, session_id
    );
CREATE INDEX sessions_terminal_timeline
    ON sessions(
        terminal_at_us, terminal_source_rank, terminal_source_order,
        terminal_event_kind_order, session_id
    ) WHERE terminal_at_us IS NOT NULL;
CREATE INDEX sessions_by_parent ON sessions(parent_session_id, session_id);

CREATE TABLE turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    state TEXT NOT NULL,
    start_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    occurrence_source_key INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    FOREIGN KEY (source_rank, occurrence_source_key)
        REFERENCES source_manifestations(source_rank, occurrence_source_key)
) STRICT, WITHOUT ROWID;
CREATE INDEX turns_timeline
    ON turns(start_at_us, source_rank, source_order, event_kind_order, turn_id);
CREATE INDEX turns_by_session
    ON turns(session_id, start_at_us, source_rank, source_order, turn_id);

CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    model TEXT NOT NULL,
    reasoning_effort TEXT,
    context_window_tokens INTEGER,
    uncached_input_tokens INTEGER,
    cached_input_tokens INTEGER,
    reasoning_tokens INTEGER,
    output_tokens INTEGER,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    occurrence_source_key INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL,
    FOREIGN KEY (source_rank, occurrence_source_key)
        REFERENCES source_manifestations(source_rank, occurrence_source_key)
) STRICT, WITHOUT ROWID;
CREATE INDEX model_calls_timeline
    ON model_calls(
        event_at_us, source_rank, source_order, event_kind_order, call_id
    );
CREATE INDEX model_calls_by_session
    ON model_calls(
        session_id, event_at_us, source_rank, source_order,
        event_kind_order, call_id
    );
CREATE INDEX model_calls_by_turn
    ON model_calls(turn_id, event_at_us, call_id);
CREATE INDEX model_calls_by_model_effort
    ON model_calls(model, reasoning_effort, event_at_us, call_id);

CREATE TABLE tool_invocations (
    tool_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    transport_name TEXT NOT NULL,
    semantic_operation TEXT NOT NULL,
    resource_id TEXT,
    write_intent INTEGER NOT NULL CHECK (write_intent IN (0, 1)),
    state TEXT NOT NULL,
    start_at_us INTEGER NOT NULL,
    start_source_rank INTEGER NOT NULL,
    start_occurrence_source_key INTEGER NOT NULL,
    start_source_order INTEGER NOT NULL,
    start_event_kind_order INTEGER NOT NULL,
    start_record_ordinal INTEGER NOT NULL,
    start_byte_start INTEGER NOT NULL,
    start_byte_end INTEGER NOT NULL,
    terminal_at_us INTEGER,
    terminal_source_rank INTEGER,
    terminal_occurrence_source_key INTEGER,
    terminal_source_order INTEGER,
    terminal_event_kind_order INTEGER,
    terminal_record_ordinal INTEGER,
    terminal_byte_start INTEGER,
    terminal_byte_end INTEGER,
    duration_us INTEGER,
    output_bytes INTEGER,
    FOREIGN KEY (start_source_rank, start_occurrence_source_key)
        REFERENCES source_manifestations(source_rank, occurrence_source_key),
    FOREIGN KEY (terminal_source_rank, terminal_occurrence_source_key)
        REFERENCES source_manifestations(source_rank, occurrence_source_key)
) STRICT, WITHOUT ROWID;
CREATE INDEX tools_start_timeline
    ON tool_invocations(
        start_at_us, start_source_rank, start_source_order,
        start_event_kind_order, tool_id
    );
CREATE INDEX tools_terminal_timeline
    ON tool_invocations(
        terminal_at_us, terminal_source_rank, terminal_source_order,
        terminal_event_kind_order, tool_id
    ) WHERE terminal_at_us IS NOT NULL;
CREATE INDEX tools_by_session
    ON tool_invocations(
        session_id, start_at_us, start_source_rank, start_source_order, tool_id
    );
CREATE INDEX tools_by_resource
    ON tool_invocations(resource_id, start_at_us, tool_id);
CREATE INDEX tools_by_family
    ON tool_invocations(transport_name, semantic_operation, state, tool_id);

CREATE TABLE activities (
    activity_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT,
    activity_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX activities_timeline
    ON activities(
        event_at_us, source_rank, source_order, event_kind_order, activity_id
    );
CREATE INDEX activities_by_session
    ON activities(session_id, event_at_us, activity_id);

CREATE TABLE state_changes (
    change_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT,
    resource_id TEXT NOT NULL,
    change_kind TEXT NOT NULL,
    preceding_activity_count INTEGER NOT NULL,
    causal_attribution TEXT,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX state_changes_timeline
    ON state_changes(
        event_at_us, source_rank, source_order, event_kind_order, change_id
    );
CREATE INDEX state_changes_by_session
    ON state_changes(session_id, event_at_us, change_id);
CREATE INDEX state_changes_by_resource
    ON state_changes(resource_id, event_at_us, change_id);

CREATE TABLE compaction_boundaries (
    compaction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    before_context_epoch TEXT NOT NULL,
    after_context_epoch TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX compactions_timeline
    ON compaction_boundaries(
        event_at_us, source_rank, source_order, event_kind_order, compaction_id
    );
CREATE INDEX compactions_by_session
    ON compaction_boundaries(session_id, event_at_us, compaction_id);

CREATE TABLE allowance_observations (
    observation_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    limit_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    plan_identity TEXT NOT NULL,
    window_kind TEXT NOT NULL,
    reset_identity TEXT NOT NULL,
    observation_ordinal INTEGER NOT NULL,
    used_percent TEXT,
    remaining_percent TEXT,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX allowance_observations_timeline
    ON allowance_observations(
        event_at_us, source_rank, source_order, event_kind_order, observation_id
    );
CREATE INDEX allowance_observations_by_compatibility
    ON allowance_observations(
        provider, limit_id, plan_identity, window_kind, reset_identity,
        event_at_us, observation_id
    );

CREATE TABLE allowance_compatibility (
    compatibility_id TEXT PRIMARY KEY,
    start_observation_id TEXT NOT NULL,
    end_observation_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    limit_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    plan_identity TEXT NOT NULL,
    window_kind TEXT NOT NULL,
    reset_identity TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX allowance_compatibility_timeline
    ON allowance_compatibility(
        event_at_us, source_rank, source_order, event_kind_order, compatibility_id
    );

CREATE TABLE late_parent_edges (
    child_session_id TEXT PRIMARY KEY,
    parent_session_id TEXT NOT NULL,
    transition TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX late_parent_edges_timeline
    ON late_parent_edges(
        event_at_us, source_rank, source_order, event_kind_order, child_session_id
    );
CREATE INDEX late_parent_edges_by_parent
    ON late_parent_edges(parent_session_id, child_session_id);

CREATE TABLE question_cases (
    oracle_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL,
    variant TEXT NOT NULL,
    expected_digest TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_rank INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    manifestation_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    byte_start INTEGER NOT NULL,
    byte_end INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX question_cases_by_question
    ON question_cases(question_id, oracle_id);

CREATE TABLE source_phase_occurrences (
    phase_id TEXT NOT NULL,
    occurrence_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    structural_case TEXT NOT NULL,
    event_at_us INTEGER NOT NULL,
    source_order INTEGER NOT NULL,
    event_kind_order INTEGER NOT NULL,
    PRIMARY KEY (phase_id, occurrence_id, revision)
) STRICT, WITHOUT ROWID;
CREATE INDEX source_phase_occurrences_timeline
    ON source_phase_occurrences(
        event_at_us, source_order, event_kind_order, occurrence_id
    );

CREATE TABLE session_usage_current (
    session_id TEXT PRIMARY KEY,
    calls INTEGER NOT NULL,
    uncached_input_tokens INTEGER NOT NULL,
    cached_input_tokens INTEGER NOT NULL,
    reasoning_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL
) STRICT, WITHOUT ROWID;
CREATE INDEX session_usage_current_rank
    ON session_usage_current(
        uncached_input_tokens DESC, cached_input_tokens DESC,
        output_tokens DESC, session_id
    );

CREATE TABLE tool_family_current (
    transport_name TEXT NOT NULL,
    semantic_operation TEXT NOT NULL,
    calls INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    duration_us INTEGER,
    output_bytes INTEGER,
    PRIMARY KEY (transport_name, semantic_operation)
) STRICT, WITHOUT ROWID;
CREATE INDEX tool_family_current_rank
    ON tool_family_current(calls DESC, transport_name, semantic_operation);
"""


def _apply_pragmas(connection: sqlite3.Connection) -> None:
    for name, value in SQLITE_SETTINGS:
        connection.execute(f"PRAGMA {name}={value}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")


def _apply_unpublished_staging_pragmas(connection: sqlite3.Connection) -> None:
    for name, value in _UNPUBLISHED_STAGING_SETTINGS:
        connection.execute(f"PRAGMA {name}={value}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")


def create_database(
    path: Path,
    *,
    unpublished_staging: bool = False,
) -> sqlite3.Connection:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if unpublished_staging:
        _apply_unpublished_staging_pragmas(connection)
    else:
        _apply_pragmas(connection)
    connection.executescript(_DDL)
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        (
            ("schema_id", SCHEMA_ID),
            ("schema_version", str(SCHEMA_VERSION)),
            ("candidate_id", "A"),
        ),
    )
    connection.commit()
    return connection


def finalize_unpublished_database(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise ValueError("candidate A staging transaction must commit before finalization")
    _apply_pragmas(connection)
    if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
        raise ValueError("candidate A failed to restore WAL before publication")
    if int(connection.execute("PRAGMA synchronous").fetchone()[0]) != 1:
        raise ValueError("candidate A failed to restore NORMAL sync before publication")
    checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
    if checkpoint != (0, 0, 0):
        raise ValueError(f"candidate A final WAL checkpoint was incomplete: {checkpoint}")


def open_database(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if read_only:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
    else:
        _apply_pragmas(connection)
    return connection


@contextmanager
def database(path: Path, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    connection = open_database(path, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()


def _validate_sqlite_pages(
    connection: sqlite3.Connection,
    *,
    mode: ValidationMode,
) -> None:
    pragma = "quick_check" if mode == "prepublication" else "integrity_check"
    results = tuple(str(row[0]) for row in connection.execute(f"PRAGMA {pragma}"))
    if results != ("ok",):
        raise ValueError(f"candidate A SQLite {pragma} failed")


def _validate_schema_contract(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    encoded = "\n".join(
        "\x1f".join(str(value) for value in row)
        for row in rows
    ).encode()
    if hashlib.sha256(encoded).hexdigest() != _EXPECTED_SCHEMA_DIGEST:
        raise ValueError("candidate A schema contract mismatch")


def _is_sha256(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_metadata_contract(connection: sqlite3.Connection) -> None:
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    if metadata.get("schema_id") != SCHEMA_ID:
        raise ValueError("candidate A schema identity mismatch")
    if metadata.get("schema_version") != str(SCHEMA_VERSION):
        raise ValueError("candidate A schema version mismatch")
    if metadata.get("candidate_id") != "A":
        raise ValueError("candidate A identity metadata mismatch")
    if metadata.get("raw_content_stored") != "false":
        raise ValueError("candidate A raw-content metadata mismatch")
    if metadata.get("history_selection") not in _HISTORY_SELECTIONS:
        raise ValueError("candidate A history-selection metadata mismatch")
    if metadata.get("prepublication_validation") != PREPUBLICATION_VALIDATION:
        raise ValueError("candidate A prepublication-validation metadata mismatch")
    if not metadata.get("fixture_revision") or not metadata.get("fixture_profile"):
        raise ValueError("candidate A fixture metadata is incomplete")
    manifest_digest = metadata.get("fixture_manifest_digest")
    oracle_digest = metadata.get("fixture_oracle_digest")
    if not _is_sha256(manifest_digest) or not _is_sha256(oracle_digest):
        raise ValueError("candidate A fixture digest metadata is invalid")
    try:
        projection_rows = int(metadata.get("projection_rows", ""))
    except ValueError as error:
        raise ValueError("candidate A projection-row metadata is invalid") from error
    if projection_rows < 0:
        raise ValueError("candidate A projection-row metadata is invalid")
    publications = connection.execute(
        """
        SELECT publication_id, fixture_manifest_digest, fixture_oracle_digest
        FROM publications
        WHERE status = 'committed'
        """
    ).fetchall()
    if len(publications) != 1:
        raise ValueError("candidate A must contain exactly one committed publication")
    publication = publications[0]
    if not str(publication["publication_id"]).startswith("publication:candidate-a:"):
        raise ValueError("candidate A publication identity mismatch")
    if (
        publication["fixture_manifest_digest"] != manifest_digest
        or publication["fixture_oracle_digest"] != oracle_digest
    ):
        raise ValueError("candidate A publication digest metadata mismatch")


def validate_database(
    connection: sqlite3.Connection,
    *,
    mode: ValidationMode = "exhaustive",
) -> None:
    """Validate a candidate artifact without making the fast mode implicit.

    The disposable staging artifact gets the bounded prepublication mode.
    Deep/read validation defaults to exhaustive SQLite index-consistency
    checking. Both modes independently enforce relationship, schema, metadata,
    and committed-publication invariants.
    """
    if mode not in {"prepublication", "exhaustive"}:
        raise ValueError(f"candidate A validation mode is invalid: {mode}")
    _validate_sqlite_pages(connection, mode=mode)
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("candidate A foreign-key check failed")
    _validate_schema_contract(connection)
    _validate_metadata_contract(connection)
