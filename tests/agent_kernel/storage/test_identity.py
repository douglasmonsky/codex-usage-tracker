from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.agent_kernel.domain.identity import (
    IdentityContractError,
    canonical_cbor,
    semantic_id,
)
from codex_usage_tracker.agent_kernel.domain.measurements import (
    MeasurementValueError,
    validate_nonnegative_measurement,
)
from codex_usage_tracker.agent_kernel.domain.models import (
    AccountingSummary,
    ConfiguredProducer,
    ConfiguredSource,
    LifecycleFold,
    LifecycleTransition,
    MeasurementAggregate,
    ModelCallTokens,
    SourceManifestation,
    SourceOccurrence,
)
from codex_usage_tracker.agent_kernel.domain.time import (
    INT64_MAX,
    INT64_MIN,
    TimeValueError,
    validate_utc_microseconds,
)
from codex_usage_tracker.agent_kernel.storage.identity import (
    IdentityCollisionError,
    IdentityRegistry,
)
from codex_usage_tracker.agent_kernel.storage.occurrences import (
    SourceOccurrenceRepository,
)
from codex_usage_tracker.agent_kernel.storage.schema import (
    ANALYTICAL_DDL,
    SCHEMA_CONTRACT_ID,
    SCHEMA_CONTRACT_SHA256,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_IDENTITY_VECTORS = (
    _REPO_ROOT / "tests" / "agent_kernel" / "contracts" / "vectors" / "identity-v1.json"
)


def _vectors() -> dict[str, Any]:
    payload = json.loads(_IDENTITY_VECTORS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _publication(connection: sqlite3.Connection, publication_id: str) -> None:
    connection.execute(
        """
        INSERT INTO publications (
          publication_id,
          parent_publication_id,
          operation_id,
          schema_contract_id,
          schema_contract_sha256,
          identity_version,
          adapter_id,
          adapter_version,
          normalization_version,
          projection_registry_sha256,
          rate_card_digest,
          history_preset,
          requested_cutoff_us,
          committed_at_us,
          observed_through_us,
          indexed_from_us,
          indexed_through_us,
          guaranteed_complete_from_us,
          artifact_manifest_sha256,
          status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            publication_id,
            None,
            f"operation:{publication_id}",
            SCHEMA_CONTRACT_ID,
            SCHEMA_CONTRACT_SHA256,
            "v1",
            "adapter:test",
            "adapter-test.v1",
            "normalization-test.v1",
            None,
            None,
            "current_session",
            None,
            0,
            None,
            None,
            None,
            None,
            "0" * 64,
            "committed",
        ),
    )


@pytest.fixture
def analytical_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(ANALYTICAL_DDL)
    _publication(connection, "publication:test-1")
    _publication(connection, "publication:test-2")
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def test_production_identity_matches_every_ck02_json_vector() -> None:
    for vector in _vectors()["identity_vectors"]:
        assert semantic_id(vector["kind"], vector["identity_tuple"]) == vector["expected_id"]


def test_canonical_cbor_is_minimal_ordered_and_restricted() -> None:
    assert canonical_cbor(None) == b"\xf6"
    assert canonical_cbor(False) == b"\xf4"
    assert canonical_cbor(True) == b"\xf5"
    assert canonical_cbor(23) == b"\x17"
    assert canonical_cbor(24) == b"\x18\x18"
    assert canonical_cbor(-1) == b"\x20"
    assert canonical_cbor(b"\x01") == b"\x41\x01"
    assert canonical_cbor("a") == b"\x61a"
    assert canonical_cbor({"aa": 1, "b": 2}) == b"\xa2\x61b\x02\x62aa\x01"

    for invalid in (1.0, object(), 1 << 65, -(1 << 65)):
        with pytest.raises(IdentityContractError):
            canonical_cbor(invalid)
    with pytest.raises(IdentityContractError):
        semantic_id("Invalid_kind", ["value"])


@pytest.mark.parametrize("value", [INT64_MIN, -1, 0, 1, INT64_MAX])
def test_utc_microseconds_accept_signed_int64_values(value: int) -> None:
    assert validate_utc_microseconds(value) == value


@pytest.mark.parametrize("value", [False, True, 1.0, INT64_MIN - 1, INT64_MAX + 1])
def test_utc_microseconds_reject_non_integer_or_out_of_range_values(value: object) -> None:
    with pytest.raises(TimeValueError):
        validate_utc_microseconds(value)


def test_missing_utc_microseconds_remains_none() -> None:
    assert validate_utc_microseconds(None) is None
    with pytest.raises(TimeValueError):
        validate_utc_microseconds(None, allow_none=False)


@pytest.mark.parametrize("value", [0, 1, INT64_MAX])
def test_nonnegative_measurements_accept_int64_values(value: int) -> None:
    assert validate_nonnegative_measurement(value) == value


@pytest.mark.parametrize("value", [-1, False, True, 1.0, INT64_MAX + 1])
def test_nonnegative_measurements_reject_invalid_values(value: object) -> None:
    with pytest.raises(MeasurementValueError):
        validate_nonnegative_measurement(value)


def test_missing_measurement_remains_none() -> None:
    assert validate_nonnegative_measurement(None) is None
    with pytest.raises(MeasurementValueError):
        validate_nonnegative_measurement(None, allow_none=False)


def test_repository_domain_models_expose_exact_selected_row_fields() -> None:
    expected = {
        ConfiguredProducer: (
            "producer_id",
            "configured_producer_key",
            "display_label",
            "first_seen_publication_id",
            "last_seen_publication_id",
        ),
        ConfiguredSource: (
            "source_id",
            "adapter_id",
            "producer_id",
            "source_kind",
            "adapter_native_source_key",
            "selected_history_preset",
            "selected_from_us",
            "selected_through_us",
            "first_seen_publication_id",
            "last_seen_publication_id",
        ),
        SourceManifestation: (
            "manifestation_id",
            "manifestation_key",
            "source_id",
            "adapter_native_file_key",
            "technical_path_key",
            "display_label",
            "filesystem_identity_json",
            "size_bytes",
            "modified_at_us",
            "prefix_sha256",
            "suffix_sha256",
            "content_revision",
            "source_rank",
            "state",
            "time_range_start_us",
            "time_range_end_us",
            "time_range_confidence",
            "selected",
            "first_seen_publication_id",
            "last_seen_publication_id",
            "ended_publication_id",
        ),
        SourceOccurrence: (
            "occurrence_id",
            "semantic_logical_id",
            "manifestation_key",
            "source_revision",
            "record_ordinal",
            "byte_start",
            "byte_end",
            "adapter_version",
            "first_seen_publication_id",
        ),
        LifecycleTransition: (
            "transition_id",
            "entity_logical_id",
            "entity_kind",
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "transition_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "occurrence_id",
            "terminal_error_category",
            "measurement_mask",
            "first_seen_publication_id",
            "session_id",
        ),
        LifecycleFold: (
            "entity_logical_id",
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "start_at_us",
            "start_occurrence_id",
            "terminal_at_us",
            "terminal_occurrence_id",
            "observed_duration_us",
            "duration_diagnostic",
            "terminal_error_category",
            "transition_count",
        ),
        ModelCallTokens: (
            "call_id",
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        ),
    }
    for model, names in expected.items():
        assert tuple(field.name for field in fields(model)) == names


def test_domain_models_validate_times_coordinates_and_four_token_values() -> None:
    source = ConfiguredSource(
        "source:test",
        "adapter:test",
        "producer:test",
        "synthetic",
        "root:test",
        "all_time",
        INT64_MIN,
        INT64_MAX,
        "publication:first",
        "publication:last",
    )
    assert source.selected_from_us == INT64_MIN

    occurrence = SourceOccurrence(
        "occurrence:test",
        "call:test",
        1,
        "revision:test",
        0,
        0,
        INT64_MAX,
        "adapter.v1",
        "publication:test",
    )
    assert occurrence.byte_end == INT64_MAX
    with pytest.raises(ValueError, match="manifestation_key"):
        replace(occurrence, manifestation_key=0)
    with pytest.raises(ValueError, match="byte_end"):
        replace(occurrence, byte_end=occurrence.byte_start)

    manifestation = SourceManifestation(
        "manifestation:test",
        1,
        "source:test",
        "file:test",
        "synthetic/file.jsonl",
        "synthetic",
        None,
        1,
        None,
        None,
        None,
        "revision:test",
        0,
        "active",
        None,
        None,
        "unknown",
        1,
        "publication:first",
        "publication:last",
        None,
    )
    with pytest.raises(ValueError, match="manifestation_key"):
        replace(manifestation, manifestation_key=0)

    tokens = ModelCallTokens("call:test", 1, None, 2, 3)
    assert (
        tokens.uncached_input_tokens,
        tokens.cached_input_tokens,
        tokens.reasoning_tokens,
        tokens.output_tokens,
    ) == (1, None, 2, 3)

    for invalid in (False, 1.0, -1, INT64_MAX + 1):
        with pytest.raises(MeasurementValueError):
            replace(tokens, output_tokens=invalid)  # type: ignore[arg-type]
    for invalid_time in (False, 1.0, INT64_MAX + 1):
        with pytest.raises(TimeValueError):
            replace(source, selected_from_us=invalid_time)  # type: ignore[arg-type]
    for invalid_coordinate in (False, 1.0, -1, INT64_MAX + 1):
        with pytest.raises(MeasurementValueError):
            replace(occurrence, byte_start=invalid_coordinate)  # type: ignore[arg-type]


def test_domain_aggregate_and_lifecycle_models_preserve_missing_values() -> None:
    transition = LifecycleTransition(
        "transition:test",
        "tool:test",
        "tool_invocation",
        "running",
        "observed_running",
        1,
        None,
        0,
        0,
        0,
        0,
        "occurrence:test",
        None,
        0,
        "publication:test",
        "session:test",
    )
    fold = LifecycleFold(
        "tool:test",
        "running",
        "observed_running",
        1,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
    )
    missing = MeasurementAggregate(None, 0, 1)
    exact = MeasurementAggregate(0, 1, 0)
    summary = AccountingSummary(1, 2, missing, exact, missing, exact)

    assert transition.transition_at_us is None
    assert fold.observed_duration_us is None
    assert not missing.complete
    assert exact.complete
    assert summary.cached_input_tokens.value == 0

    with pytest.raises(MeasurementValueError):
        replace(transition, measurement_mask=True)  # type: ignore[arg-type]
    with pytest.raises(MeasurementValueError):
        replace(fold, observed_duration_us=-1)
    with pytest.raises(MeasurementValueError):
        replace(summary, canonical_model_calls=INT64_MAX + 1)


def test_sqlite_registry_persists_every_identity_vector_and_updates_last_seen(
    analytical_connection: sqlite3.Connection,
) -> None:
    registry = IdentityRegistry(analytical_connection)

    for vector in _vectors()["identity_vectors"]:
        record = registry.register(
            vector["expected_id"],
            vector["kind"],
            vector["identity_tuple"],
            "publication:test-1",
        )
        assert record.logical_id == vector["expected_id"]
        assert record.entity_kind == vector["kind"]
        assert record.identity_version == "v1"
        assert record.identity_cbor == canonical_cbor(vector["identity_tuple"])

    first = _vectors()["identity_vectors"][0]
    record = registry.register(
        first["expected_id"],
        first["kind"],
        first["identity_tuple"],
        "publication:test-2",
    )
    assert record.first_seen_publication_id == "publication:test-1"
    assert record.last_seen_publication_id == "publication:test-2"
    analytical_connection.commit()

    assert analytical_connection.execute("SELECT count(*) FROM identity_registry").fetchone()[
        0
    ] == len(_vectors()["identity_vectors"])


def test_production_storage_preserves_ck02_occurrence_coordinates() -> None:
    """The CK-02 copy vector must remain one logical entity and two physical rows."""

    vector = _vectors()["occurrence_vectors"][0]
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(ANALYTICAL_DDL)
    _publication(connection, "publication:occurrence-vectors")
    registry = IdentityRegistry(connection)
    repository = SourceOccurrenceRepository(connection)
    try:
        logical_id = vector["expected_logical_id"]
        registry.register(
            logical_id,
            "session",
            vector["occurrences"][0]["identity_tuple"],
            "publication:occurrence-vectors",
        )
        adapter_id = semantic_id("adapter", ["occurrence-vectors", "adapter-v1"])
        registry.register(
            adapter_id,
            "adapter",
            ["occurrence-vectors", "adapter-v1"],
            "publication:occurrence-vectors",
        )
        connection.execute(
            "INSERT INTO adapters VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                adapter_id,
                "adapter-v1",
                "synthetic",
                1,
                "v1",
                "publication:occurrence-vectors",
                "publication:occurrence-vectors",
            ),
        )
        for index, occurrence in enumerate(vector["occurrences"], start=1):
            coordinate = occurrence["coordinate"]
            producer_id = semantic_id("producer", ["occurrence-vectors", index])
            source_id = semantic_id("source", [adapter_id, producer_id, index])
            manifestation_id = coordinate["source_manifestation_id"]
            registry.register(
                producer_id,
                "producer",
                ["occurrence-vectors", index],
                "publication:occurrence-vectors",
            )
            registry.register(
                source_id,
                "source",
                [adapter_id, producer_id, index],
                "publication:occurrence-vectors",
            )
            # Manifestation identities are fixture preconditions here; the
            # semantic vector above separately qualifies their production
            # derivation. This occurrence vector owns the exact physical
            # coordinates, including both frozen manifestation IDs.
            identity_bytes = manifestation_id.encode()
            connection.execute(
                """
                INSERT INTO identity_registry (
                  logical_id, entity_kind, identity_version, identity_cbor,
                  identity_sha256, first_seen_publication_id,
                  last_seen_publication_id
                ) VALUES (?, 'source_manifestation', 'v1', ?, ?, ?, ?)
                """,
                (
                    manifestation_id,
                    identity_bytes,
                    sha256(identity_bytes).hexdigest(),
                    "publication:occurrence-vectors",
                    "publication:occurrence-vectors",
                ),
            )
            occurrence_id = semantic_id(
                "source-occurrence",
                [logical_id, coordinate],
            )
            registry.register(
                occurrence_id,
                "source-occurrence",
                [logical_id, coordinate],
                "publication:occurrence-vectors",
            )
            connection.execute(
                "INSERT INTO source_producers VALUES (?, ?, ?, ?, ?)",
                (
                    producer_id,
                    f"producer-key:{index}",
                    f"Producer {index}",
                    "publication:occurrence-vectors",
                    "publication:occurrence-vectors",
                ),
            )
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    adapter_id,
                    producer_id,
                    "synthetic",
                    f"source-key:{index}",
                    "all_time",
                    None,
                    None,
                    "publication:occurrence-vectors",
                    "publication:occurrence-vectors",
                ),
            )
            connection.execute(
                """
                INSERT INTO source_manifestations (
                  manifestation_id, manifestation_key, source_id,
                  adapter_native_file_key, technical_path_key, display_label,
                  filesystem_identity_json, size_bytes, modified_at_us,
                  prefix_sha256, suffix_sha256, content_revision, source_rank,
                  state, time_range_start_us, time_range_end_us,
                  time_range_confidence, selected, first_seen_publication_id,
                  last_seen_publication_id, ended_publication_id
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?, ?,
                          'active', NULL, NULL, 'unavailable', 1, ?, ?, NULL)
                """,
                (
                    manifestation_id,
                    index,
                    source_id,
                    manifestation_id,
                    f"synthetic/{index}.jsonl",
                    f"Synthetic {index}",
                    1,
                    coordinate["source_revision"],
                    index,
                    "publication:occurrence-vectors",
                    "publication:occurrence-vectors",
                ),
            )
            repository.add(
                SourceOccurrence(
                    occurrence_id,
                    logical_id,
                    index,
                    coordinate["source_revision"],
                    coordinate["record_ordinal"],
                    index * 100,
                    index * 100 + 50,
                    coordinate["adapter_version"],
                    "publication:occurrence-vectors",
                )
            )

        rows = repository.for_semantic_id(logical_id)
        assert len(rows) == 2
        persisted_coordinates = connection.execute(
            """
            SELECT manifestation.manifestation_id, occurrence.source_revision,
                   occurrence.record_ordinal, occurrence.adapter_version
            FROM source_occurrences AS occurrence
            JOIN source_manifestations AS manifestation
              ON manifestation.manifestation_key = occurrence.manifestation_key
            WHERE occurrence.semantic_logical_id = ?
            ORDER BY manifestation.manifestation_id
            """,
            (logical_id,),
        ).fetchall()
        assert [
            {
                "source_manifestation_id": row[0],
                "source_revision": row[1],
                "record_ordinal": row[2],
                "adapter_version": row[3],
            }
            for row in persisted_coordinates
        ] == sorted(
            vector["expected_coordinates"],
            key=lambda coordinate: coordinate["source_manifestation_id"],
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM identity_registry WHERE logical_id = ?", (logical_id,)
            ).fetchone()[0]
            == vector["expected_entity_count"]
        )
    finally:
        connection.close()


def test_production_storage_exercises_ck02_publication_derivation_vector(
    analytical_connection: sqlite3.Connection,
) -> None:
    vector = _vectors()["publication_derivation_vectors"][0]
    registry = IdentityRegistry(analytical_connection)
    record = registry.register(
        vector["expected_publication_id"],
        "publication",
        [vector["publication_key"]],
        "publication:test-1",
    )
    artifact = vector["artifact_without_digest"]
    artifact_bytes = (
        json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    assert record.logical_id == vector["expected_publication_id"]
    assert sha256(artifact_bytes).hexdigest() == vector["expected_artifact_digest"]
    assert vector["derivation_order"] == [
        "allocate_publication_key",
        "derive_publication_id",
        "assemble_canonical_artifact_without_artifact_digest",
        "derive_artifact_digest",
    ]


def test_full_cbor_collision_fails_closed_and_caller_can_rollback(
    analytical_connection: sqlite3.Connection,
) -> None:
    vector = _vectors()["collision_vectors"][0]
    registry = IdentityRegistry(analytical_connection)

    analytical_connection.execute("BEGIN")
    registry.register(
        vector["logical_id"],
        "session",
        vector["first_tuple"],
        "publication:test-1",
    )
    with pytest.raises(IdentityCollisionError) as raised:
        registry.register(
            vector["logical_id"],
            "session",
            vector["second_tuple"],
            "publication:test-1",
        )
    assert raised.value.logical_id == vector["logical_id"]
    analytical_connection.rollback()

    assert registry.get(vector["logical_id"]) is None
