"""Same-snapshot publication and isolated-artifact validation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.identity import semantic_id
from ..storage.database import (
    DatabaseValidation,
    open_builder,
    open_read_only,
    open_writer,
    validate_database,
)
from ..storage.lifecycle import LifecycleFoldError, LifecycleRepository
from ..storage.schema import SCHEMA_CONTRACT_SHA256


class PublicationValidationError(RuntimeError):
    """An artifact cannot become or remain the analytical authority."""


@dataclass(frozen=True, slots=True)
class PublicationIdentity:
    publication_id: str
    parent_publication_id: str | None
    operation_id: str
    artifact_manifest_sha256: str
    committed_at_us: int


@dataclass(frozen=True, slots=True)
class ArtifactValidation:
    identity: PublicationIdentity
    sqlite: DatabaseValidation
    file_sha256: str | None
    entity_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    path: Path
    artifact_name: str
    publication_id: str
    artifact_manifest_sha256: str
    file_sha256: str


_ENTITY_COUNT_QUERIES = (
    ("activities", "SELECT COUNT(*) FROM activities"),
    ("allowance_limits", "SELECT COUNT(*) FROM allowance_limits"),
    ("allowance_observations", "SELECT COUNT(*) FROM allowance_observations"),
    ("compaction_boundaries", "SELECT COUNT(*) FROM compaction_boundaries"),
    ("model_calls", "SELECT COUNT(*) FROM model_calls_visible"),
    ("projects", "SELECT COUNT(*) FROM projects"),
    ("resources", "SELECT COUNT(*) FROM resources"),
    ("sessions", "SELECT COUNT(*) FROM sessions"),
    ("source_manifestations", "SELECT COUNT(*) FROM source_manifestations"),
    ("source_occurrences", "SELECT COUNT(*) FROM source_occurrences"),
    ("state_changes", "SELECT COUNT(*) FROM state_changes"),
    ("tool_invocations", "SELECT COUNT(*) FROM tool_invocations"),
    ("turns", "SELECT COUNT(*) FROM turns"),
)
_SOURCE_ENTITY_KINDS = frozenset({"source_manifestations", "source_occurrences"})
_IDENTITY_OWNERS = (
    ("adapters", "adapter_id", "adapter"),
    ("source_producers", "producer_id", "producer"),
    ("sources", "source_id", "source"),
    ("source_manifestations", "manifestation_id", "source-manifestation"),
    ("source_occurrences", "occurrence_id", "source-occurrence"),
    ("projects", "project_id", "project"),
    ("resources", "resource_id", "resource"),
    ("model_profiles", "model_profile_id", "model-profile"),
    ("sessions", "session_id", "session"),
    ("turns", "turn_id", "turn"),
    ("lifecycle_transitions", "transition_id", "lifecycle-transition"),
    ("model_call_locations", "call_id", "call"),
    ("tool_invocations", "tool_id", "tool"),
    ("activities", "activity_id", "activity"),
    ("compaction_boundaries", "compaction_id", "compaction"),
    ("state_changes", "change_id", "state-change"),
    ("allowance_limits", "limit_id", "allowance-limit"),
    ("allowance_cycles", "cycle_id", "allowance-cycle"),
    ("allowance_observations", "observation_id", "allowance-observation"),
    ("allowance_intervals", "interval_id", "allowance-interval"),
    ("rate_card_revisions", "rate_card_id", "rate-card"),
)
_EXTERNAL_LOGICAL_ID_KINDS = frozenset({"adapter", "source-manifestation"})
_LIFECYCLE_FOLDS = (
    (
        "session",
        "sessions",
        "session_id",
        (
            ("lifecycle_state", "lifecycle_state"),
            ("state_basis", "state_basis"),
            ("transition_version", "transition_version"),
            ("start_at_us", "start_at_us"),
            ("end_at_us", "terminal_at_us"),
            ("observed_duration_us", "observed_duration_us"),
        ),
    ),
    (
        "turn",
        "turns",
        "turn_id",
        (
            ("lifecycle_state", "lifecycle_state"),
            ("state_basis", "state_basis"),
            ("transition_version", "transition_version"),
            ("start_at_us", "start_at_us"),
            ("end_at_us", "terminal_at_us"),
        ),
    ),
    (
        "model_call",
        "model_calls_visible",
        "call_id",
        (
            ("lifecycle_state", "lifecycle_state"),
            ("state_basis", "state_basis"),
            ("transition_version", "transition_version"),
        ),
    ),
    (
        "tool_invocation",
        "tool_invocations",
        "tool_id",
        (
            ("lifecycle_state", "lifecycle_state"),
            ("state_basis", "state_basis"),
            ("transition_version", "transition_version"),
            ("start_at_us", "start_at_us"),
            ("terminal_at_us", "terminal_at_us"),
            ("terminal_occurrence_id", "terminal_occurrence_id"),
            ("observed_duration_us", "observed_duration_us"),
            ("error_category", "terminal_error_category"),
        ),
    ),
    (
        "activity",
        "activities",
        "activity_id",
        (
            ("lifecycle_state", "lifecycle_state"),
            ("state_basis", "state_basis"),
            ("transition_version", "transition_version"),
        ),
    ),
)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def artifact_manifest_sha256(manifest_without_digest: object) -> str:
    return hashlib.sha256(canonical_json_bytes(manifest_without_digest)).hexdigest()


def file_sha256(path: Path, *, block_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(block_bytes):
            digest.update(block)
    return digest.hexdigest()


def isolated_artifact_name(operation_id: str) -> str:
    opaque = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:32]
    return f"artifact-{opaque}.sqlite3"


def build_isolated_artifact(
    directory: Path,
    operation_id: str,
    build: Callable[[sqlite3.Connection], None],
    *,
    expected_publication_id: str,
    expected_manifest_sha256: str,
    fault: Callable[[str], None] | None = None,
) -> CandidateArtifact:
    """Build and durably validate one unpublished owner-only artifact.

    The callback may stream existing facts or sources, but it runs only against
    the unpublished builder. No active analytical connection is opened here.
    """

    directory = Path(directory)
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise PublicationValidationError("artifact directory must be owner-only 0700")
    artifact_name = isolated_artifact_name(operation_id)
    path = directory / artifact_name
    if path.exists() or path.is_symlink():
        raise PublicationValidationError("candidate artifact name is already owned")
    connection: sqlite3.Connection | None = None
    connection = open_builder(path)
    try:
        build(connection)
        if fault is not None:
            fault("after_build")
        validate_open_artifact(
            connection,
            expected_publication_id=expected_publication_id,
            expected_manifest_sha256=expected_manifest_sha256,
            integrity=True,
        )
        if fault is not None:
            fault("after_validation")
        connection.close()
        connection = open_writer(path)
        checkpoint_cursor = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        checkpoint = checkpoint_cursor.fetchone()
        checkpoint_cursor.close()
        if checkpoint is None or int(checkpoint[0]) != 0:
            raise PublicationValidationError("candidate artifact WAL checkpoint remained busy")
        connection.close()
        connection = None
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        digest = file_sha256(path)
        validate_artifact_path(
            path,
            expected_publication_id=expected_publication_id,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_file_sha256=digest,
            integrity=True,
        )
        if fault is not None:
            fault("after_durability")
        return CandidateArtifact(
            path=path,
            artifact_name=artifact_name,
            publication_id=expected_publication_id,
            artifact_manifest_sha256=expected_manifest_sha256,
            file_sha256=digest,
        )
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _head(connection: sqlite3.Connection) -> PublicationIdentity:
    row = connection.execute(
        """
        SELECT publication.publication_id, publication.parent_publication_id,
               publication.operation_id, publication.artifact_manifest_sha256,
               publication.committed_at_us
        FROM publication_head AS head
        JOIN publications AS publication
          ON publication.publication_id = head.publication_id
        WHERE head.singleton = 1 AND publication.status = 'committed'
        """
    ).fetchone()
    if row is None:
        raise PublicationValidationError("artifact has no committed publication head")
    return PublicationIdentity(
        publication_id=str(row[0]),
        parent_publication_id=None if row[1] is None else str(row[1]),
        operation_id=str(row[2]),
        artifact_manifest_sha256=str(row[3]),
        committed_at_us=int(row[4]),
    )


def _validate_tail(connection: sqlite3.Connection, publication_id: str) -> None:
    state = connection.execute(
        """
        SELECT row_count, minimum_event_at_us, maximum_event_at_us,
               maximum_source_order, base_publication_id, last_fold_publication_id
        FROM model_call_tail_state WHERE singleton = 1
        """
    ).fetchone()
    actual = int(connection.execute("SELECT COUNT(*) FROM model_call_tail").fetchone()[0])
    if state is None:
        if actual:
            raise PublicationValidationError("model-call tail rows exist without tail state")
        return
    if int(state[0]) != actual or actual > 32_000:
        raise PublicationValidationError("model-call tail state does not match physical rows")
    bounds = connection.execute(
        "SELECT MIN(event_at_us), MAX(event_at_us), MAX(source_order) FROM model_call_tail"
    ).fetchone()
    if tuple(state[1:4]) != tuple(bounds):
        raise PublicationValidationError("model-call tail bounds do not reconcile")
    if str(state[5]) not in {
        publication_id,
        str(state[4]),
    }:
        raise PublicationValidationError("model-call tail fold publication is inconsistent")
    duplicates = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM model_calls AS base
            JOIN model_call_tail AS tail USING (call_id)
            """
        ).fetchone()[0]
    )
    if duplicates:
        raise PublicationValidationError("model-call identity exists in base and tail")


def _validate_coverage(connection: sqlite3.Connection, publication_id: str) -> None:
    expected = {
        str(row[0]): tuple(int(value) for value in row[1:])
        for row in connection.execute(
            """
            SELECT source.source_id,
                   COALESCE(SUM(manifestation.selected), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.selected = 1
                          THEN manifestation.size_bytes ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.selected = 0 THEN 1 ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.selected = 0
                          THEN manifestation.size_bytes ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.state = 'malformed' THEN 1 ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.state = 'malformed'
                          THEN manifestation.size_bytes ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.state = 'missing' THEN 1 ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.state = 'missing'
                          THEN manifestation.size_bytes ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.time_range_confidence <> 'trusted'
                          THEN 1 ELSE 0 END
                   ), 0),
                   COALESCE(SUM(
                     CASE WHEN manifestation.time_range_confidence <> 'trusted'
                          THEN manifestation.size_bytes ELSE 0 END
                   ), 0),
                   (
                     SELECT COUNT(*) FROM source_diagnostics AS diagnostic
                     JOIN source_manifestations AS diagnosed
                       USING (manifestation_key)
                     WHERE diagnosed.source_id = source.source_id
                   ),
                   COALESCE((
                     SELECT SUM(diagnostic.byte_end - diagnostic.byte_start)
                     FROM source_diagnostics AS diagnostic
                     JOIN source_manifestations AS diagnosed
                       USING (manifestation_key)
                     WHERE diagnosed.source_id = source.source_id
                   ), 0),
                   COALESCE((
                     SELECT SUM(cursor.record_ordinal)
                     FROM source_cursors AS cursor
                     JOIN source_manifestations AS cursored
                       USING (manifestation_key)
                     WHERE cursored.source_id = source.source_id
                   ), 0)
            FROM sources AS source
            LEFT JOIN source_manifestations AS manifestation
              ON manifestation.source_id = source.source_id
            GROUP BY source.source_id
            """
        )
    }
    actual = {
        str(row[0]): tuple(int(value) for value in row[1:])
        for row in connection.execute(
            """
            SELECT source_id,
                   selected_manifestation_count, selected_manifestation_bytes,
                   deferred_manifestation_count, deferred_manifestation_bytes,
                   malformed_manifestation_count, malformed_manifestation_bytes,
                   missing_manifestation_count, missing_manifestation_bytes,
                   uncertain_manifestation_count, uncertain_manifestation_bytes,
                   malformed_range_count, malformed_range_bytes,
                   selected_complete_record_count
            FROM publication_source_coverage
            WHERE publication_id = ?
            """,
            (publication_id,),
        )
    }
    if actual != expected:
        raise PublicationValidationError(
            "publication source coverage totals do not reconcile to source inventory"
        )
    _validate_coverage_clocks(connection, publication_id)


def _validate_counts(
    connection: sqlite3.Connection, publication_id: str
) -> tuple[tuple[str, int], ...]:
    counts = tuple(
        (str(row[0]), int(row[1]))
        for row in connection.execute(
            """
            SELECT entity_kind, entity_count
            FROM publication_entity_counts
            WHERE publication_id = ?
            ORDER BY entity_kind
            """,
            (publication_id,),
        )
    )
    if not counts:
        raise PublicationValidationError("publication entity counts are missing")
    stored = dict(counts)
    physical = {
        entity_kind: int(connection.execute(query).fetchone()[0])
        for entity_kind, query in _ENTITY_COUNT_QUERIES
    }
    if (
        set(stored) - set(physical)
        or any(stored[kind] != physical[kind] for kind in stored)
        or any(count and kind not in stored for kind, count in physical.items())
    ):
        raise PublicationValidationError(
            "publication entity counts do not reconcile to canonical tables"
        )
    return counts


def _validate_coverage_clocks(connection: sqlite3.Connection, publication_id: str) -> None:
    publication = connection.execute(
        """
        SELECT indexed_from_us, indexed_through_us, guaranteed_complete_from_us
        FROM publications WHERE publication_id = ?
        """,
        (publication_id,),
    ).fetchone()
    assert publication is not None
    for row in connection.execute(
        """
        SELECT indexed_from_us, indexed_through_us,
               guaranteed_complete_from_us, guaranteed_complete_through_us,
               clock_quality, clock_uncertainty_us,
               inventory_started_at_us, inventory_completed_at_us
        FROM publication_source_coverage WHERE publication_id = ?
        """,
        (publication_id,),
    ):
        expected_through = publication[1] if publication[2] is not None else None
        if tuple(row[:3]) != tuple(publication) or row[3] != expected_through:
            raise PublicationValidationError(
                "publication source coverage clock bounds differ from publication"
            )
        if (row[4] == "bounded") != (row[5] is not None) or int(row[6]) > int(row[7]):
            raise PublicationValidationError("publication source coverage clock bounds are invalid")


def _validate_identity_registry(connection: sqlite3.Connection) -> None:
    for row in connection.execute(
        """
        SELECT logical_id, entity_kind, identity_version,
               identity_cbor, identity_sha256
        FROM identity_registry
        """
    ):
        logical_id, entity_kind, version = map(str, row[:3])
        identity_digest = hashlib.sha256(bytes(row[3])).hexdigest()
        if version != "v1" or identity_digest != str(row[4]):
            raise PublicationValidationError("identity registry digest does not reconcile")
        if entity_kind in _EXTERNAL_LOGICAL_ID_KINDS:
            continue
        encoded = base64.b32encode(bytes.fromhex(identity_digest)).decode("ascii")
        expected_id = f"{entity_kind}:v1:{encoded.rstrip('=').lower()}"
        if logical_id != expected_id:
            raise PublicationValidationError("identity registry logical ID collides with its tuple")
    _validate_identity_owners(connection)
    _validate_source_ownership(connection)


def _validate_identity_owners(connection: sqlite3.Connection) -> None:
    for table, key, entity_kind in _IDENTITY_OWNERS:
        invalid = connection.execute(
            f"""
            SELECT owner.{key}
            FROM {table} AS owner
            JOIN identity_registry AS identity
              ON identity.logical_id = owner.{key}
            WHERE identity.entity_kind <> ?
            LIMIT 1
            """,
            (entity_kind,),
        ).fetchone()
        if invalid is not None:
            raise PublicationValidationError(
                f"{table} identity ownership differs from the registry"
            )


def _validate_source_ownership(connection: sqlite3.Connection) -> None:
    for producer_id, configured_key in connection.execute(
        "SELECT producer_id, configured_producer_key FROM source_producers"
    ):
        if str(producer_id) != semantic_id("producer", [str(configured_key)]):
            raise PublicationValidationError("configured producer identity ownership is invalid")
    for row in connection.execute(
        """
        SELECT source_id, adapter_id, producer_id, source_kind,
               adapter_native_source_key
        FROM sources
        """
    ):
        if str(row[0]) != semantic_id("source", list(row[1:])):
            raise PublicationValidationError("source-root identity ownership is invalid")
    for row in connection.execute(
        """
        SELECT occurrence.occurrence_id, occurrence.semantic_logical_id,
               manifestation.manifestation_id, occurrence.source_revision,
               occurrence.byte_start, occurrence.byte_end,
               occurrence.record_ordinal, occurrence.adapter_version
        FROM source_occurrences AS occurrence
        JOIN source_manifestations AS manifestation USING (manifestation_key)
        """
    ):
        identity = (row[1], row[2], row[3], [row[4], row[5]], row[6], row[7])
        if str(row[0]) != semantic_id("source-occurrence", identity):
            raise PublicationValidationError("source occurrence identity ownership is invalid")


def _validate_lifecycle_folds(connection: sqlite3.Connection) -> None:
    repository = LifecycleRepository(connection)
    for entity_kind, table, key, columns in _LIFECYCLE_FOLDS:
        column_sql = ", ".join((key, *(column for column, _ in columns)))
        typed_rows = {
            str(row[0]): tuple(row[1:])
            for row in connection.execute(f"SELECT {column_sql} FROM {table}")
        }
        transition_ids = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT entity_logical_id
                FROM lifecycle_transitions WHERE entity_kind = ?
                """,
                (entity_kind,),
            )
        }
        if set(typed_rows) != transition_ids:
            raise PublicationValidationError("lifecycle transition ownership is incomplete")
        for logical_id, persisted in typed_rows.items():
            transitions = repository.transitions_for(logical_id)
            if {item.entity_kind for item in transitions} != {entity_kind}:
                raise PublicationValidationError("lifecycle transition kind ownership is invalid")
            try:
                fold = repository.fold(logical_id)
            except LifecycleFoldError as error:
                raise PublicationValidationError("lifecycle transition fold is invalid") from error
            expected = tuple(getattr(fold, attribute) for _, attribute in columns)
            if persisted != expected:
                raise PublicationValidationError("typed lifecycle fold does not reconcile")


def _validate_model_call_ownership(connection: sqlite3.Connection) -> None:
    duplicate = connection.execute(
        """
        SELECT base.call_id FROM model_calls AS base
        JOIN model_call_tail AS tail
          ON tail.call_id = base.call_id
          OR (
            tail.session_id = base.session_id
            AND tail.adapter_native_call_key = base.adapter_native_call_key
          )
        LIMIT 1
        """
    ).fetchone()
    if duplicate is not None:
        raise PublicationValidationError("model-call identity exists in base and tail")
    invalid_location = connection.execute(
        """
        SELECT location.call_id
        FROM model_call_locations AS location
        LEFT JOIN model_calls AS base ON base.call_id = location.call_id
        LEFT JOIN model_call_tail AS tail ON tail.call_id = location.call_id
        WHERE (location.storage_class = 'base') <> (base.call_id IS NOT NULL)
           OR (location.storage_class = 'tail') <> (tail.call_id IS NOT NULL)
        LIMIT 1
        """
    ).fetchone()
    if invalid_location is not None:
        raise PublicationValidationError("model-call location ownership is invalid")
    located = int(connection.execute("SELECT COUNT(*) FROM model_call_locations").fetchone()[0])
    visible = int(connection.execute("SELECT COUNT(*) FROM model_calls_visible").fetchone()[0])
    if located != visible:
        raise PublicationValidationError("model-call location count does not reconcile")


def _publication_count_map(
    connection: sqlite3.Connection, publication_id: str | None
) -> dict[str, int]:
    if publication_id is None:
        return {}
    return {
        str(row[0]): int(row[1])
        for row in connection.execute(
            """
            SELECT entity_kind, entity_count
            FROM publication_entity_counts WHERE publication_id = ?
            """,
            (publication_id,),
        )
    }


def _validate_publication_delta(
    connection: sqlite3.Connection,
    identity: PublicationIdentity,
    counts: tuple[tuple[str, int], ...],
) -> None:
    delta = connection.execute(
        """
        SELECT parent_publication_id, inserted_count, corrected_count,
               terminalized_count, recanonicalized_count, removed_count
        FROM publication_deltas WHERE publication_id = ?
        """,
        (identity.publication_id,),
    ).fetchone()
    if delta is None or delta[0] != identity.parent_publication_id:
        raise PublicationValidationError("publication delta parent does not reconcile")
    entities = {
        str(row[0]): tuple(int(value) for value in row[1:])
        for row in connection.execute(
            """
            SELECT entity_kind, inserted_count, corrected_count,
                   terminalized_count, recanonicalized_count, removed_count
            FROM publication_delta_entities WHERE publication_id = ?
            """,
            (identity.publication_id,),
        )
    }
    aggregate = tuple(sum(values[index] for values in entities.values()) for index in range(5))
    if aggregate != tuple(int(value) for value in delta[1:]):
        raise PublicationValidationError("publication delta aggregate does not reconcile")
    current = dict(counts)
    parent = _publication_count_map(connection, identity.parent_publication_id)
    for entity_kind, values in entities.items():
        if entity_kind not in current or current[entity_kind] - parent.get(entity_kind, 0) != (
            values[0] - values[4]
        ):
            raise PublicationValidationError("publication delta entity count does not reconcile")
    for entity_kind in set(current) | set(parent):
        count_delta = current.get(entity_kind, 0) - parent.get(entity_kind, 0)
        if entity_kind not in _SOURCE_ENTITY_KINDS and count_delta and entity_kind not in entities:
            raise PublicationValidationError("publication delta omits a changed entity count")


def _validate_manifest(connection: sqlite3.Connection, identity: PublicationIdentity) -> None:
    compatibility = connection.execute(
        """
        SELECT projection_registry_sha256, rate_card_digest
        FROM publications WHERE publication_id = ?
        """,
        (identity.publication_id,),
    ).fetchone()
    assert compatibility is not None
    actual = artifact_manifest_sha256(
        manifest_from_database(
            connection,
            identity.publication_id,
            projection_registry_sha256=compatibility[0],
            active_rate_card_digest=compatibility[1],
        )
    )
    if actual != identity.artifact_manifest_sha256:
        raise PublicationValidationError(
            "canonical artifact manifest differs from the publication digest"
        )


def validate_open_artifact(
    connection: sqlite3.Connection,
    *,
    expected_publication_id: str | None = None,
    expected_manifest_sha256: str | None = None,
    integrity: bool = False,
) -> ArtifactValidation:
    """Validate one already-open artifact entirely inside its read snapshot."""

    connection.execute("BEGIN")
    try:
        sqlite_validation = validate_database(connection, "analytical", integrity=integrity)
        identity = _head(connection)
        if (
            expected_publication_id is not None
            and identity.publication_id != expected_publication_id
        ):
            raise PublicationValidationError("pointer publication differs from artifact head")
        if (
            expected_manifest_sha256 is not None
            and identity.artifact_manifest_sha256 != expected_manifest_sha256
        ):
            raise PublicationValidationError("pointer manifest differs from artifact head")
        _validate_tail(connection, identity.publication_id)
        _validate_model_call_ownership(connection)
        _validate_identity_registry(connection)
        _validate_lifecycle_folds(connection)
        _validate_coverage(connection, identity.publication_id)
        counts = _validate_counts(connection, identity.publication_id)
        _validate_publication_delta(connection, identity, counts)
        _validate_manifest(connection, identity)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ArtifactValidation(identity, sqlite_validation, None, counts)


def validate_artifact_path(
    path: Path,
    *,
    expected_publication_id: str | None = None,
    expected_manifest_sha256: str | None = None,
    expected_file_sha256: str | None = None,
    integrity: bool = False,
) -> ArtifactValidation:
    path = Path(path)
    if expected_file_sha256 is not None:
        actual_file_sha256 = file_sha256(path)
        if actual_file_sha256 != expected_file_sha256:
            raise PublicationValidationError("artifact file digest differs from pointer")
    connection = open_read_only(path)
    try:
        result = validate_open_artifact(
            connection,
            expected_publication_id=expected_publication_id,
            expected_manifest_sha256=expected_manifest_sha256,
            integrity=integrity,
        )
    finally:
        connection.close()
    return ArtifactValidation(
        result.identity,
        result.sqlite,
        expected_file_sha256,
        result.entity_counts,
    )


def reopen_validated_artifact(
    path: Path,
    *,
    expected_publication_id: str,
    expected_manifest_sha256: str,
) -> PublicationIdentity:
    """Reopen the already fully validated, hash-fenced promotion candidate.

    ``build_isolated_artifact`` owns the expensive complete reconciliation
    before checkpoint, digest, and fsync.  Promotion repeats the finalized
    file digest under both leases immediately before the pointer swap.  This
    bounded post-swap check therefore verifies owner-only SQLite identity,
    schema metadata, quick/FK checks (via ``open_read_only``), and the
    committed publication/head manifest agreement without re-running every
    logical aggregate against the same immutable bytes in the fence.
    """

    connection = open_read_only(path)
    try:
        identity = _head(connection)
        if identity.publication_id != expected_publication_id:
            raise PublicationValidationError("pointer publication differs from artifact head")
        if identity.artifact_manifest_sha256 != expected_manifest_sha256:
            raise PublicationValidationError("pointer manifest differs from artifact head")
        return identity
    finally:
        connection.close()


def manifest_from_database(
    connection: sqlite3.Connection,
    publication_id: str,
    *,
    projection_registry_sha256: str | None,
    active_rate_card_digest: str | None,
) -> dict[str, Any]:
    """Assemble the nonrecursive canonical artifact manifest payload."""

    publication = connection.execute(
        """
        SELECT parent_publication_id, schema_contract_sha256
        FROM publications WHERE publication_id = ?
        """,
        (publication_id,),
    ).fetchone()
    if publication is None:
        raise PublicationValidationError("publication does not exist")
    cursor_rows = [
        list(row)
        for row in connection.execute(
            """
            SELECT manifestation_key, source_revision, byte_offset, record_ordinal,
                   source_size_bytes, prefix_through_cursor_sha256, suffix_sha256,
                   latest_source_order, parser_version, adapter_version
            FROM source_cursors ORDER BY manifestation_key
            """
        )
    ]
    coverage_rows = [
        list(row)
        for row in connection.execute(
            """
            SELECT * FROM publication_source_coverage
            WHERE publication_id = ? ORDER BY source_id
            """,
            (publication_id,),
        )
    ]
    entity_counts = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            """
            SELECT entity_kind, entity_count FROM publication_entity_counts
            WHERE publication_id = ? ORDER BY entity_kind
            """,
            (publication_id,),
        )
    }
    delta = connection.execute(
        "SELECT * FROM publication_deltas WHERE publication_id = ?",
        (publication_id,),
    ).fetchone()
    return {
        "publication_id": publication_id,
        "parent_publication_id": publication[0],
        "schema_contract_sha256": str(publication[1]),
        "source_cursor_inventory_sha256": hashlib.sha256(
            canonical_json_bytes(cursor_rows)
        ).hexdigest(),
        "coverage": coverage_rows,
        "entity_counts": entity_counts,
        "publication_delta": None if delta is None else list(delta),
        "projection_registry_sha256": projection_registry_sha256,
        "active_rate_card_digest": active_rate_card_digest,
        "database_identity": "codex-usage-tracker.agent-kernel.v1",
        "schema_contract": SCHEMA_CONTRACT_SHA256,
    }
