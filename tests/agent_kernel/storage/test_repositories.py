from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from hashlib import sha256

import pytest

from codex_usage_tracker.agent_kernel.storage.repositories import (
    ConfiguredProducer,
    ConfiguredProducerRepository,
    ConfiguredSource,
    ConfiguredSourceRepository,
    RepositoryConflictError,
    SelectedFactRepository,
    SourceManifestation,
    SourceManifestationRepository,
    validate_storage_scalars,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DDL,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
)

PUBLICATION_ID = "publication:test"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(ANALYTICAL_DDL)
    connection.execute(
        """
        INSERT INTO publications (
          publication_id, parent_publication_id, operation_id,
          schema_contract_id, schema_contract_sha256, identity_version,
          adapter_id, adapter_version, normalization_version,
          projection_registry_sha256, rate_card_digest, history_preset,
          requested_cutoff_us, committed_at_us, observed_through_us,
          indexed_from_us, indexed_through_us, guaranteed_complete_from_us,
          artifact_manifest_sha256, status
        ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?, NULL,
                  NULL, NULL, NULL, ?, ?)
        """,
        (
            PUBLICATION_ID,
            "operation:test",
            SCHEMA_CONTRACT_ID,
            SCHEMA_CONTRACT_SHA256,
            "identity-v1",
            "adapter:test",
            "adapter-v1",
            "normalization-v1",
            "all_time",
            1,
            "f" * 64,
            "committed",
        ),
    )
    return connection


def _identity(connection: sqlite3.Connection, logical_id: str, kind: str) -> None:
    identity_bytes = logical_id.encode()
    connection.execute(
        """
        INSERT INTO identity_registry (
          logical_id, entity_kind, identity_version, identity_cbor,
          identity_sha256, first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            logical_id,
            kind,
            "identity-v1",
            identity_bytes,
            sha256(identity_bytes).hexdigest(),
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )


def _seed_adapter(connection: sqlite3.Connection) -> None:
    _identity(connection, "adapter:test", "adapter")
    connection.execute(
        """
        INSERT INTO adapters (
          adapter_id, adapter_version, source_kind, capability_mask,
          identity_version, first_seen_publication_id, last_seen_publication_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "adapter:test",
            "adapter-v1",
            "synthetic-jsonl",
            15,
            "identity-v1",
            PUBLICATION_ID,
            PUBLICATION_ID,
        ),
    )


def test_configured_source_repositories_bind_values_and_update_observations() -> None:
    connection = _connection()
    _seed_adapter(connection)
    for logical_id, kind in (
        ("producer:test", "producer"),
        ("source:test", "source"),
        ("manifestation:test", "source_manifestation"),
    ):
        _identity(connection, logical_id, kind)

    producer_repository = ConfiguredProducerRepository(connection)
    producer = ConfiguredProducer(
        "producer:test", "local'producer", "Synthetic", PUBLICATION_ID, PUBLICATION_ID
    )
    assert producer_repository.put(producer) == producer
    assert producer_repository.get_by_key("local'producer") == producer
    assert producer_repository.put(replace(producer, display_label="Updated")).display_label == (
        "Updated"
    )

    source_repository = ConfiguredSourceRepository(connection)
    source = ConfiguredSource(
        "source:test",
        "adapter:test",
        "producer:test",
        "synthetic-jsonl",
        "root'one",
        "all_time",
        None,
        None,
        PUBLICATION_ID,
        PUBLICATION_ID,
    )
    source_repository.put(source)
    assert (
        source_repository.get_by_configured_key(
            adapter_id="adapter:test",
            producer_id="producer:test",
            source_kind="synthetic-jsonl",
            adapter_native_source_key="root'one",
        )
        == source
    )

    manifestation_repository = SourceManifestationRepository(connection)
    manifestation = SourceManifestation(
        "manifestation:test",
        1,
        "source:test",
        "file:test",
        "sessions/synthetic.jsonl",
        "synthetic.jsonl",
        None,
        10,
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
    )
    manifestation_repository.put(manifestation)
    updated = replace(manifestation, size_bytes=20, content_revision="revision:2")
    manifestation_repository.put(updated)
    assert (
        manifestation_repository.get_by_file_key(
            source_id="source:test", adapter_native_file_key="file:test"
        )
        == updated
    )


def test_configured_keys_fail_closed_on_identity_conflicts() -> None:
    connection = _connection()
    _seed_adapter(connection)
    _identity(connection, "producer:first", "producer")
    _identity(connection, "producer:second", "producer")
    repository = ConfiguredProducerRepository(connection)
    repository.put(
        ConfiguredProducer("producer:first", "same-key", None, PUBLICATION_ID, PUBLICATION_ID)
    )
    with pytest.raises(RepositoryConflictError, match="different producer identity"):
        repository.put(
            ConfiguredProducer("producer:second", "same-key", None, PUBLICATION_ID, PUBLICATION_ID)
        )


def test_primary_ids_fail_closed_when_stable_tuples_change() -> None:
    connection = _connection()
    _seed_adapter(connection)
    for logical_id, kind in (
        ("producer:test", "producer"),
        ("source:test", "source"),
        ("manifestation:test", "source_manifestation"),
    ):
        _identity(connection, logical_id, kind)

    producer_repository = ConfiguredProducerRepository(connection)
    producer = ConfiguredProducer(
        "producer:test", "producer-key", "original", PUBLICATION_ID, PUBLICATION_ID
    )
    assert producer_repository.put(producer) == producer
    assert (
        producer_repository.put(replace(producer, display_label="persisted")).display_label
        == "persisted"
    )
    with pytest.raises(RepositoryConflictError, match="producer ID maps"):
        producer_repository.put(replace(producer, configured_producer_key="other-producer-key"))

    source_repository = ConfiguredSourceRepository(connection)
    source = ConfiguredSource(
        "source:test",
        "adapter:test",
        "producer:test",
        "synthetic-jsonl",
        "root:test",
        "all_time",
        None,
        None,
        PUBLICATION_ID,
        PUBLICATION_ID,
    )
    assert source_repository.put(source) == source
    assert source_repository.put(replace(source, selected_from_us=1)).selected_from_us == 1
    with pytest.raises(RepositoryConflictError, match="source ID maps"):
        source_repository.put(replace(source, adapter_native_source_key="other-root"))

    manifestation_repository = SourceManifestationRepository(connection)
    manifestation = SourceManifestation(
        "manifestation:test",
        1,
        "source:test",
        "file:test",
        "path/test",
        "test.jsonl",
        None,
        1,
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
    )
    assert manifestation_repository.put(manifestation) == manifestation
    assert manifestation_repository.put(replace(manifestation, size_bytes=2)).size_bytes == 2
    with pytest.raises(RepositoryConflictError, match="manifestation ID maps"):
        manifestation_repository.put(replace(manifestation, manifestation_key=2))
    with pytest.raises(RepositoryConflictError, match="manifestation ID maps"):
        manifestation_repository.put(replace(manifestation, technical_path_key="path/other"))


@dataclass(frozen=True)
class _ModelProfile:
    model_profile_id: str
    model: str
    reasoning_effort: str | None
    service_tier: str | None
    first_seen_publication_id: str
    last_seen_publication_id: str


@dataclass(frozen=True)
class _IncompleteModelProfile:
    model_profile_id: str
    model: str


def test_selected_fact_repository_coalesces_only_identical_canonical_rows() -> None:
    connection = _connection()
    _identity(connection, "model-profile:test", "model_profile")
    repository = SelectedFactRepository(
        connection,
        table="model_profiles",
        key_column="model_profile_id",
        row_type=_ModelProfile,
    )
    row = _ModelProfile(
        "model-profile:test",
        "synthetic-model",
        None,
        None,
        PUBLICATION_ID,
        PUBLICATION_ID,
    )
    assert repository.add(row) == row
    assert repository.add(row) == row
    assert repository.get("model-profile:test") == row
    with pytest.raises(RepositoryConflictError, match="canonical key conflicts"):
        repository.add(replace(row, model="different-model"))


def test_selected_fact_repository_requires_exact_table_column_inventory() -> None:
    with pytest.raises(ValueError, match="inventory must exactly match"):
        SelectedFactRepository(
            _connection(),
            table="model_profiles",
            key_column="model_profile_id",
            row_type=_IncompleteModelProfile,
        )


def test_storage_scalar_validation_is_field_aware_and_fail_closed() -> None:
    validate_storage_scalars(
        {
            "reset_time_us": -(2**63),
            "observed_at_us": 2**63 - 1,
            "selected": 1,
            "ratio_eligible": 0,
            "write_intent": 1,
            "reasoning_in_output": 0,
            "source_order": 0,
            "absolute_fields_json": '{"a":[1,2]}',
            "used_percent": "12.5",
            "remaining_percent": "0",
            "percent_delta": "-1.25",
        }
    )
    invalid_values = (
        ({"reset_time_us": True}, TypeError),
        ({"reset_time_us": 2**63}, ValueError),
        ({"selected": True}, TypeError),
        ({"ratio_eligible": 2}, TypeError),
        ({"write_intent": True}, TypeError),
        ({"reasoning_in_output": -1}, TypeError),
        ({"source_order": -1}, ValueError),
        ({"absolute_fields_json": '{"b": 1}'}, ValueError),
        ({"absolute_fields_json": "not-json"}, ValueError),
        ({"used_percent": "01"}, ValueError),
        ({"remaining_percent": "1.0"}, ValueError),
        ({"percent_delta": "NaN"}, ValueError),
    )
    for values, exception in invalid_values:
        with pytest.raises(exception):
            validate_storage_scalars(values)


def test_fixed_parameterized_baseline_reads_compile_to_declared_indexes() -> None:
    connection = _connection()
    plans = {
        "producer": connection.execute(
            "EXPLAIN QUERY PLAN SELECT producer_id FROM source_producers "
            "WHERE configured_producer_key = ?",
            ("producer-key",),
        ).fetchall(),
        "source": connection.execute(
            "EXPLAIN QUERY PLAN SELECT source_id FROM sources "
            "WHERE adapter_id = ? AND producer_id = ? AND source_kind = ? "
            "AND adapter_native_source_key = ?",
            ("adapter:test", "producer:test", "synthetic-jsonl", "root:test"),
        ).fetchall(),
        "manifestation": connection.execute(
            "EXPLAIN QUERY PLAN SELECT manifestation_id FROM source_manifestations "
            "WHERE source_id = ? AND adapter_native_file_key = ?",
            ("source:test", "file:test"),
        ).fetchall(),
        "occurrence": connection.execute(
            "EXPLAIN QUERY PLAN SELECT occurrence_id FROM source_occurrences "
            "WHERE semantic_logical_id = ? ORDER BY manifestation_key, source_revision, "
            "record_ordinal, byte_start, occurrence_id",
            ("call:test",),
        ).fetchall(),
    }
    for plan in plans.values():
        details = " ".join(str(row[3]) for row in plan)
        assert "SEARCH" in details
        assert "SCAN" not in details
