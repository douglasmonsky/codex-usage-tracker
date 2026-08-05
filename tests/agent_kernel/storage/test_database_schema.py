from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.storage.database import (
    DatabaseContractError,
    DatabaseIdentityError,
    DatabaseValidationError,
    initialize_analytical,
    initialize_operational,
    measure_database_size,
    open_builder,
    open_read_only,
    open_writer,
    validate_database,
)
from codex_usage_tracker.agent_kernel.storage.paths import (
    ANALYTICAL_CACHE_FILENAME,
    OwnerOnlyPathError,
    agent_kernel_cache_path,
    ensure_owner_only_directory,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DATABASE_IDENTITY,
    ANALYTICAL_DDL,
    OPERATIONAL_DDL,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
    canonical_schema_digest,
    schema_objects,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = _ROOT / "docs" / "architecture" / "AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md"
_PREDECESSOR_SCHEMA_DIGEST = (
    "1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5"
)
_SELECTED_SCHEMA_DIGEST = (
    "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295"
)
_CK08R3A_INDEX_NAMES = (
    "evidence_model_calls_by_session_order",
    "evidence_model_call_tail_by_session_order",
    "evidence_tools_by_session_order",
    "evidence_activities_by_session_order",
    "evidence_state_changes_by_session_order",
    "evidence_compactions_by_session_order",
    "evidence_context_components_by_session_order",
    "evidence_turns_by_session_order",
    "evidence_lifecycle_by_session_order",
    "evidence_source_occurrences_by_logical_order",
    "evidence_tools_by_resource_order",
    "evidence_state_changes_by_resource_order",
    "evidence_allowance_observations_order",
)

_PREDECESSOR_TURNS_DDL = """CREATE TABLE turns (
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
  start_source_order INTEGER CHECK (start_source_order IS NULL OR start_source_order >= 0),
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
    start_source_order IS NULL
    OR end_source_order IS NULL
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
"""
_SUCCESSOR_TURNS_DDL = """CREATE TABLE turns (
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
"""
_PREDECESSOR_LIFECYCLE_DDL = """CREATE TABLE lifecycle_transitions (
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
  UNIQUE (entity_logical_id, transition_version),
  FOREIGN KEY (transition_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (entity_logical_id) REFERENCES identity_registry(logical_id),
  FOREIGN KEY (occurrence_id) REFERENCES source_occurrences(occurrence_id),
  FOREIGN KEY (first_seen_publication_id)
    REFERENCES publications(publication_id)
) STRICT, WITHOUT ROWID;
"""
_SUCCESSOR_LIFECYCLE_DDL = """CREATE TABLE lifecycle_transitions (
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
"""
_SUCCESSOR_INDEXES_DDL = """-- CK-08R3A evidence pages use the persisted seven-part order tuple.  Each
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
"""


def _contract_ddl(name: str) -> str:
    markdown = _CONTRACT.read_text(encoding="utf-8")
    match = re.search(
        rf"<!-- {name}-ddl:start -->\n```sql\n(.*?)```\n<!-- {name}-ddl:end -->",
        markdown,
        re.DOTALL,
    )
    assert match is not None
    lines = [
        line.rstrip(" \t")
        for line in match.group(1).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _selected_analytical_ddl() -> str:
    predecessor = _contract_ddl("analytical")
    assert predecessor.count(_PREDECESSOR_TURNS_DDL) == 1
    assert predecessor.count(_PREDECESSOR_LIFECYCLE_DDL) == 1
    return (
        predecessor
        .replace(_PREDECESSOR_TURNS_DDL, _SUCCESSOR_TURNS_DDL)
        .replace(_PREDECESSOR_LIFECYCLE_DDL, _SUCCESSOR_LIFECYCLE_DDL)
        + "\n"
        + _SUCCESSOR_INDEXES_DDL
    )


def _pragma(connection: sqlite3.Connection, name: str) -> object:
    return connection.execute(f"PRAGMA {name}").fetchone()[0]  # noqa: S608


def test_packaged_ddl_is_exact_contract_and_inventory_locked() -> None:
    predecessor = _contract_ddl("analytical")
    selected = _selected_analytical_ddl()
    assert ANALYTICAL_DDL in {predecessor, selected}
    assert OPERATIONAL_DDL == _contract_ddl("operational")
    if ANALYTICAL_DDL == predecessor:
        assert canonical_schema_digest() == SCHEMA_CONTRACT_SHA256 == _PREDECESSOR_SCHEMA_DIGEST
    else:
        assert ANALYTICAL_DDL == selected
        assert canonical_schema_digest() == SCHEMA_CONTRACT_SHA256 == _SELECTED_SCHEMA_DIGEST

    analytical = schema_objects("analytical")
    operational = schema_objects("operational")
    assert sum(item.object_type == "table" for item in analytical) == 42
    expected_index_count = 44 if ANALYTICAL_DDL == predecessor else 57
    assert sum(item.object_type == "index" for item in analytical) == expected_index_count
    assert [item.name for item in analytical if item.object_type == "view"] == [
        "model_calls_visible"
    ]
    assert sum(item.object_type == "table" for item in operational) == 6
    assert sum(item.object_type == "index" for item in operational) == 6


def test_ck08r3a_selected_schema_transition_is_exact_and_fail_closed() -> None:
    predecessor = _contract_ddl("analytical")
    selected = _selected_analytical_ddl()
    assert predecessor != selected
    assert hashlib.sha256(
        (
            "codex-usage-tracker.agent-kernel.schema-contract.v1\n"
            f"analytical\n{selected}"
            f"operational\n{_contract_ddl('operational')}"
        ).encode()
    ).hexdigest() == _SELECTED_SCHEMA_DIGEST

    selected_connection = sqlite3.connect(":memory:")
    try:
        selected_connection.executescript(selected)
        index_names = {
            str(row[0])
            for row in selected_connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
    finally:
        selected_connection.close()
    assert set(_CK08R3A_INDEX_NAMES) <= index_names
    assert len(index_names) == 57


def test_connection_modes_checks_and_database_size(tmp_path: Path) -> None:
    database = tmp_path / "analytical.sqlite3"
    writer = initialize_analytical(database)
    try:
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        assert _pragma(writer, "page_size") == 4096
        assert str(_pragma(writer, "journal_mode")).lower() == "wal"
        assert _pragma(writer, "synchronous") == 1
        assert _pragma(writer, "foreign_keys") == 1
        assert _pragma(writer, "busy_timeout") == 5000
        assert _pragma(writer, "cache_size") == -20000
        assert _pragma(writer, "mmap_size") == 0
        assert _pragma(writer, "temp_store") == 2
        assert _pragma(writer, "wal_autocheckpoint") == 1000
        validation = validate_database(writer, "analytical", integrity=True)
        assert validation.quick_check == "ok"
        assert validation.integrity_check == "ok"
        assert validation.foreign_key_violations == ()
        size = measure_database_size(database, writer)
        assert size.database_bytes > 0
        assert size.page_size == 4096
        assert size.page_count > 0
        assert size.wal_bytes >= 0
        assert size.shm_bytes >= 0
    finally:
        writer.close()

    reader = open_read_only(database)
    try:
        assert _pragma(reader, "query_only") == 1
        assert _pragma(reader, "foreign_keys") == 1
        assert _pragma(reader, "busy_timeout") == 5000
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO metadata(key, value) VALUES (?, ?)", ("x", "y"))
    finally:
        reader.close()

    reopened = open_writer(database)
    reopened.close()


def test_builder_mode_is_isolated_and_owner_only(tmp_path: Path) -> None:
    database = tmp_path / "builder.sqlite3"
    builder = open_builder(database)
    try:
        assert _pragma(builder, "journal_mode") == "off"
        assert _pragma(builder, "synchronous") == 0
        assert _pragma(builder, "foreign_keys") == 1
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
    finally:
        builder.close()


def test_old_foreign_and_swapped_database_are_rejected_without_creation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises((sqlite3.OperationalError, FileNotFoundError)):
        open_writer(missing)
    assert not missing.exists()

    legacy = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(legacy)
    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()
    legacy.chmod(0o600)
    before = legacy.read_bytes()
    with pytest.raises(DatabaseIdentityError):
        open_writer(legacy)
    assert legacy.read_bytes() == before

    operational = tmp_path / "operations.sqlite3"
    initialize_operational(operational).close()
    with pytest.raises(DatabaseIdentityError):
        open_writer(operational, "analytical")


def test_predecessor_schema_is_rejected_before_any_application_use(
    tmp_path: Path,
) -> None:
    predecessor = tmp_path / "predecessor.sqlite3"
    connection = sqlite3.connect(predecessor)
    connection.executescript(_contract_ddl("analytical"))
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        (
            ("database_identity", ANALYTICAL_DATABASE_IDENTITY),
            ("schema_contract_id", SCHEMA_CONTRACT_ID),
            ("schema_contract_sha256", _PREDECESSOR_SCHEMA_DIGEST),
            ("schema_version", SCHEMA_VERSION),
            ("raw_content_stored", "false"),
            ("time_unit", "utc_microseconds"),
            ("interval_semantics", "[start,end)"),
        ),
    )
    connection.commit()
    connection.close()
    predecessor.chmod(0o600)
    before = predecessor.read_bytes()

    for opener in (open_writer, open_read_only):
        with pytest.raises(DatabaseIdentityError):
            opener(predecessor)
        assert predecessor.read_bytes() == before
        assert not Path(f"{predecessor}-wal").exists()
        assert not Path(f"{predecessor}-shm").exists()

    current_metadata = tmp_path / "predecessor-current-digest.sqlite3"
    current_metadata.write_bytes(before)
    current_metadata.chmod(0o600)
    connection = sqlite3.connect(current_metadata)
    connection.execute(
        "UPDATE metadata SET value = ? WHERE key = 'schema_contract_sha256'",
        (SCHEMA_CONTRACT_SHA256,),
    )
    connection.commit()
    connection.close()
    current_before = current_metadata.read_bytes()
    with pytest.raises(DatabaseValidationError):
        open_writer(current_metadata)
    assert current_metadata.read_bytes() == current_before


def test_cache_paths_fail_closed_on_unsafe_existing_paths(tmp_path: Path) -> None:
    resolved = agent_kernel_cache_path(tmp_path)
    assert resolved.name == ANALYTICAL_CACHE_FILENAME
    assert stat.S_IMODE(resolved.parent.stat().st_mode) == 0o700

    permissive = tmp_path / "permissive"
    permissive.mkdir(mode=0o755)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(permissive)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(link)

    database = tmp_path / "unsafe.sqlite3"
    database.write_bytes(b"not sqlite")
    database.chmod(0o644)
    with pytest.raises(DatabaseContractError):
        open_writer(database)

    safe_database = tmp_path / "safe.sqlite3"
    initialize_analytical(safe_database).close()
    database_link = tmp_path / "database-link.sqlite3"
    database_link.symlink_to(safe_database)
    with pytest.raises(DatabaseContractError):
        open_writer(database_link)

    sidecar_target = tmp_path / "sidecar-target"
    sidecar_target.write_bytes(b"untouched")
    Path(f"{safe_database}-wal").symlink_to(sidecar_target)
    with pytest.raises(DatabaseContractError):
        open_writer(safe_database)
    assert sidecar_target.read_bytes() == b"untouched"


def test_cache_directory_owner_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "owner"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: directory.stat().st_uid + 1)
    with pytest.raises(OwnerOnlyPathError):
        ensure_owner_only_directory(directory)
