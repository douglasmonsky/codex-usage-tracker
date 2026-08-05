from __future__ import annotations

import sqlite3
from hashlib import sha256

import pytest

from codex_usage_tracker.agent_kernel.storage.lifecycle import (
    LifecycleFoldError,
    LifecycleRepository,
    LifecycleTransition,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DDL,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
)

PUBLICATION_ID = "publication:lifecycle"


def _identity(connection: sqlite3.Connection, logical_id: str, kind: str) -> None:
    payload = logical_id.encode()
    connection.execute(
        """
        INSERT INTO identity_registry (
          logical_id, entity_kind, identity_version, identity_cbor,
          identity_sha256, first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, 'identity-v1', ?, ?, ?, ?)
        """,
        (
            logical_id,
            kind,
            payload,
            sha256(payload).hexdigest(),
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(ANALYTICAL_DDL)
    connection.execute(
        """
        INSERT INTO publications (
          publication_id, operation_id, schema_contract_id,
          schema_contract_sha256, identity_version, adapter_id,
          adapter_version, normalization_version, history_preset,
          committed_at_us, artifact_manifest_sha256, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            PUBLICATION_ID,
            "operation:lifecycle",
            SCHEMA_CONTRACT_ID,
            SCHEMA_CONTRACT_SHA256,
            "identity-v1",
            "adapter:lifecycle",
            "adapter-v1",
            "normalization-v1",
            "all_time",
            1,
            "f" * 64,
            "committed",
        ),
    )
    for logical_id, kind in (
        ("adapter:lifecycle", "adapter"),
        ("producer:lifecycle", "producer"),
        ("source:lifecycle", "source"),
        ("project:lifecycle", "project"),
        ("session:lifecycle", "session"),
        ("manifestation:lifecycle", "source_manifestation"),
        ("tool:lifecycle", "tool_invocation"),
        ("occurrence:start", "source_occurrence"),
        ("occurrence:terminal", "source_occurrence"),
        ("occurrence:conflict", "source_occurrence"),
        ("transition:start", "lifecycle_transition"),
        ("transition:terminal", "lifecycle_transition"),
        ("transition:conflict", "lifecycle_transition"),
    ):
        _identity(connection, logical_id, kind)
    connection.execute(
        """
        INSERT INTO adapters VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "adapter:lifecycle",
            "adapter-v1",
            "synthetic-jsonl",
            1,
            "identity-v1",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        "INSERT INTO source_producers VALUES (?, ?, ?, ?, ?)",
        (
            "producer:lifecycle",
            "local",
            None,
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        """
        INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "source:lifecycle",
            "adapter:lifecycle",
            "producer:lifecycle",
            "synthetic-jsonl",
            "root",
            "all_time",
            None,
            None,
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    connection.execute(
        """
        INSERT INTO source_manifestations VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "manifestation:lifecycle",
            1,
            "source:lifecycle",
            "file",
            "sessions/lifecycle.jsonl",
            "lifecycle.jsonl",
            None,
            100,
            None,
            None,
            None,
            "revision:1",
            0,
            "active",
            None,
            None,
            "unavailable",
            1,
            PUBLICATION_ID,
            PUBLICATION_ID,
            None,
        ),
    )
    for ordinal, occurrence_id in enumerate(
        ("occurrence:start", "occurrence:terminal", "occurrence:conflict"), start=1
    ):
        connection.execute(
            "INSERT INTO source_occurrences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                occurrence_id,
                "tool:lifecycle",
                1,
                "revision:1",
                ordinal,
                ordinal * 10,
                ordinal * 10 + 5,
                "adapter-v1",
                PUBLICATION_ID,
            ),
        )
    connection.execute(
        """
        INSERT INTO projects (
          project_id, workspace_key, label_candidates_json,
          first_event_at_us, last_event_at_us, provenance_json,
          first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, '[]', NULL, NULL, '[]', ?, ?)
        """,
        ("project:lifecycle", "lifecycle", PUBLICATION_ID, PUBLICATION_ID),
    )
    connection.execute(
        """
        INSERT INTO sessions (
          session_id, adapter_native_session_key, identity_version, project_id,
          root_session_id, parent_session_id, relationship_basis,
          delegation_depth, lifecycle_state, state_basis, transition_version,
          start_at_us, end_at_us, observed_duration_us, completion_basis,
          label_candidates_json, primary_occurrence_id,
          first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL,
                  NULL, NULL, '[]', ?, ?, ?)
        """,
        (
            "session:lifecycle",
            "native-lifecycle",
            "identity-v1",
            "project:lifecycle",
            "unknown",
            "synthetic",
            0,
            "occurrence:start",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )
    return connection


def _transition(
    transition_id: str,
    state: str,
    version: int,
    event_at_us: int,
    occurrence_id: str,
) -> LifecycleTransition:
    return LifecycleTransition(
        transition_id,
        "tool:lifecycle",
        "tool_invocation",
        state,
        f"observed_{state}",
        version,
        event_at_us,
        0,
        version,
        1,
        version,
        occurrence_id,
        None,
        1,
        PUBLICATION_ID,
        "session:lifecycle",
    )


def test_late_order_transition_folds_before_an_already_observed_terminal() -> None:
    repository = LifecycleRepository(_connection())
    terminal = _transition("transition:terminal", "succeeded", 2, 300, "occurrence:terminal")
    assert repository.append(terminal).lifecycle_state == "succeeded"

    folded = repository.append(
        _transition("transition:start", "running", 1, 100, "occurrence:start")
    )
    assert folded.lifecycle_state == "succeeded"
    assert folded.state_basis == "observed_succeeded"
    assert folded.start_occurrence_id == "occurrence:start"
    assert folded.terminal_occurrence_id == "occurrence:terminal"
    assert folded.observed_duration_us == 200
    assert folded.transition_count == 2


def test_clock_skew_preserves_evidence_and_records_negative_duration() -> None:
    connection = _connection()
    repository = LifecycleRepository(connection)
    terminal = _transition("transition:terminal", "succeeded", 2, 100, "occurrence:terminal")
    repository.append(terminal)

    folded = repository.append(
        _transition("transition:start", "running", 1, 300, "occurrence:start")
    )

    assert folded.lifecycle_state == "succeeded"
    assert folded.start_at_us == 300
    assert folded.terminal_at_us == 100
    assert folded.observed_duration_us is None
    assert folded.duration_diagnostic == "negative_duration"
    assert folded.transition_count == 2
    assert connection.execute("SELECT COUNT(*) FROM lifecycle_transitions").fetchone()[0] == 2


def test_terminal_state_is_absorbing_and_conflict_does_not_append() -> None:
    connection = _connection()
    repository = LifecycleRepository(connection)
    repository.append(_transition("transition:start", "running", 1, 100, "occurrence:start"))
    repository.append(
        _transition("transition:terminal", "succeeded", 2, 300, "occurrence:terminal")
    )

    with pytest.raises(
        LifecycleFoldError, match="invalid lifecycle transition succeeded -> failed"
    ):
        repository.append(
            _transition("transition:conflict", "failed", 3, 400, "occurrence:conflict")
        )
    assert connection.execute("SELECT COUNT(*) FROM lifecycle_transitions").fetchone()[0] == 2


def test_lifecycle_baseline_read_compiles_to_entity_index() -> None:
    connection = _connection()
    plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT transition_id
        FROM lifecycle_transitions
        WHERE entity_logical_id = ?
        ORDER BY transition_version, (transition_at_us IS NULL), transition_at_us,
                 source_rank, source_order, event_kind_order, entity_logical_id,
                 transition_rank
        """,
        ("tool:lifecycle",),
    ).fetchall()
    details = " ".join(str(row[3]) for row in plan)
    assert "SEARCH" in details
