"""Bounded atomic writer for planner-proven CK-07 small publications.

All source discovery, parsing, canonicalization, and whole-artifact work must
finish before this module is called.  The writer deliberately accepts a fully
materialized write set, rechecks its parent/source assumptions, and performs
only bounded point writes in one ``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from ..adapters.codex_jsonl.canonicalize import ProposedChangeSet, ProposedOccurrence
from ..adapters.contracts import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    IDENTITY_VERSION,
    AdapterObservation,
    SourceCursor,
    SourceInventory,
)
from ..domain.identity import canonical_cbor, semantic_id
from ..domain.models import LifecycleTransition, SourceOccurrence
from ..domain.valuation import RateCardFrontier
from ..storage.lifecycle import LifecycleRepository
from ..storage.rate_cards import (
    RateCardFrontierError,
    validate_publication_rate_card_frontier,
)
from ..storage.repositories import validate_storage_scalars
from ..storage.schema import SCHEMA_CONTRACT_ID, SCHEMA_CONTRACT_SHA256
from ..storage.source_progress import (
    SourceCursorRecord,
    SourceCursorRepository,
    SourceDiagnosticRecord,
    SourceDiagnosticRepository,
)
from .planner import OperationClass, PublicationPlan
from .validation import artifact_manifest_sha256, manifest_from_database

if TYPE_CHECKING:
    from ..storage.operational import OperationalStore, WorkerProbe
    from .recovery import ArtifactValidator, FaultHook, SmallPublicationRequest

FaultInjector = Callable[[str], None]


class PublicationWriteError(RuntimeError):
    """A proposed small publication cannot be committed safely."""


class PublicationConflictError(PublicationWriteError):
    """The parent publication or a planned source revision changed."""


class PublicationLimitError(PublicationWriteError):
    """The supplied write set exceeded its planner-proven bounds."""


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    publication_id: str
    operation_id: str
    committed_at_us: int
    history_preset: str
    artifact_manifest_sha256: str
    parent_publication_id: str | None = None
    observed_through_us: int | None = None
    requested_cutoff_us: int | None = None
    indexed_from_us: int | None = None
    indexed_through_us: int | None = None
    guaranteed_complete_from_us: int | None = None
    projection_registry_sha256: str | None = None
    rate_card_digest: str | None = None
    adapter_id: str = ADAPTER_ID
    adapter_version: str = ADAPTER_VERSION
    identity_version: str = IDENTITY_VERSION
    normalization_version: str = "codex-jsonl-normalization.v1"

    def __post_init__(self) -> None:
        if not self.publication_id or not self.operation_id:
            raise ValueError("publication and operation IDs are required")
        if self.history_preset not in {
            "current_session",
            "24_hours",
            "7_days",
            "30_days",
            "90_days",
            "one_year",
            "all_time",
        }:
            raise ValueError("unknown history preset")
        _digest(self.artifact_manifest_sha256, "artifact_manifest_sha256")
        if self.projection_registry_sha256 is not None:
            _digest(self.projection_registry_sha256, "projection_registry_sha256")
        if self.rate_card_digest is not None:
            _digest(self.rate_card_digest, "rate_card_digest")
        validate_storage_scalars(
            {
                "committed_at_us": self.committed_at_us,
                "observed_through_us": self.observed_through_us,
                "requested_cutoff_us": self.requested_cutoff_us,
                "indexed_from_us": self.indexed_from_us,
                "indexed_through_us": self.indexed_through_us,
                "guaranteed_complete_from_us": self.guaranteed_complete_from_us,
            }
        )


@dataclass(frozen=True, slots=True)
class IdentityMutation:
    logical_id: str
    entity_kind: str
    identity_tuple: object
    enforce_semantic_id: bool = True


@dataclass(frozen=True, slots=True)
class PreparedRow:
    """One schema-exact canonical row prepared without the writer lock."""

    table: str
    values: Mapping[str, Any]
    update_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class ModelCallTailState:
    row_count: int
    minimum_event_at_us: int | None
    maximum_event_at_us: int | None
    maximum_source_order: int | None
    base_publication_id: str
    last_fold_publication_id: str

    def __post_init__(self) -> None:
        if not 0 <= self.row_count <= 32_000:
            raise ValueError("model-call tail row count must be between 0 and 32000")


@dataclass(frozen=True, slots=True)
class PriorPublicationSnapshot:
    """Bounded values captured by the planner's read snapshot."""

    entity_counts: Mapping[str, int] = field(default_factory=dict)
    lifecycle: Mapping[str, tuple[LifecycleTransition, ...]] = field(default_factory=dict)
    tail_state: ModelCallTailState | None = None
    unaffected_tail_state: ModelCallTailState | None = None
    source_revisions: Mapping[int, str] = field(default_factory=dict)
    source_coverage: tuple[PreparedRow, ...] = ()
    source_cursors: tuple[SourceCursor, ...] = ()
    source_manifestations: Mapping[int, PreparedRow] = field(default_factory=dict)
    source_diagnostic_keys: frozenset[tuple[int, str, int, int, str]] = frozenset()
    entity_rows: Mapping[str, PreparedRow] = field(default_factory=dict)
    occurrence_ids: frozenset[str] = frozenset()
    late_parent_versions: Mapping[str, int] = field(default_factory=dict)
    late_parent_edges: Mapping[tuple[str, str, str], PreparedRow] = field(default_factory=dict)
    allowance_predecessors: Mapping[tuple[str, ...], PreparedRow] = field(default_factory=dict)
    allowance_intervals: Mapping[str, PreparedRow] = field(default_factory=dict)
    rate_card_frontier: RateCardFrontier | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_counts", MappingProxyType(dict(self.entity_counts)))
        object.__setattr__(
            self,
            "lifecycle",
            MappingProxyType({key: tuple(value) for key, value in self.lifecycle.items()}),
        )
        object.__setattr__(
            self,
            "source_revisions",
            MappingProxyType(dict(self.source_revisions)),
        )
        object.__setattr__(
            self,
            "source_manifestations",
            MappingProxyType(dict(self.source_manifestations)),
        )
        object.__setattr__(
            self,
            "source_diagnostic_keys",
            frozenset(self.source_diagnostic_keys),
        )
        object.__setattr__(
            self,
            "entity_rows",
            MappingProxyType(dict(self.entity_rows)),
        )
        object.__setattr__(self, "occurrence_ids", frozenset(self.occurrence_ids))
        object.__setattr__(
            self,
            "late_parent_versions",
            MappingProxyType(dict(self.late_parent_versions)),
        )
        object.__setattr__(
            self,
            "late_parent_edges",
            MappingProxyType(dict(self.late_parent_edges)),
        )
        object.__setattr__(
            self,
            "allowance_predecessors",
            MappingProxyType(dict(self.allowance_predecessors)),
        )
        object.__setattr__(
            self,
            "allowance_intervals",
            MappingProxyType(dict(self.allowance_intervals)),
        )


@dataclass(frozen=True, slots=True)
class PublicationWriteSet:
    changes: ProposedChangeSet
    identities: tuple[IdentityMutation, ...]
    rows: tuple[PreparedRow, ...]
    lifecycle_transitions: tuple[LifecycleTransition, ...] = ()
    tail_state: ModelCallTailState | None = None
    expected_source_revisions: Mapping[int, str] = field(default_factory=dict)
    cursor_snapshot: tuple[SourceCursor, ...] = ()
    existing_occurrence_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_source_revisions",
            MappingProxyType(dict(self.expected_source_revisions)),
        )
        object.__setattr__(
            self,
            "existing_occurrence_ids",
            frozenset(self.existing_occurrence_ids),
        )


@dataclass(frozen=True, slots=True)
class PublicationResult:
    publication_id: str | None
    operation_id: str
    no_change: bool
    idempotent_replay: bool
    inserted_occurrences: int
    elapsed_ns: int
    transaction_elapsed_ns: int | None = None


@dataclass(frozen=True, slots=True)
class _EncodedIdentity:
    logical_id: str
    entity_kind: str
    identity_cbor: bytes
    identity_sha256: str


@dataclass(frozen=True, slots=True)
class _TableSpec:
    columns: tuple[str, ...]
    primary: tuple[str, ...]


_ROW_ORDER = (
    "adapters",
    "source_producers",
    "sources",
    "source_manifestations",
    "projects",
    "resources",
    "model_profiles",
    "sessions",
    "turns",
    "late_parent_edges",
    "model_call_locations",
    "model_call_tail",
    "tool_invocations",
    "tool_resources",
    "activities",
    "compaction_boundaries",
    "context_components",
    "state_changes",
    "allowance_limits",
    "allowance_cycles",
    "allowance_observations",
    "allowance_intervals",
    "rate_card_revisions",
    "selector_anchors",
    "publication_source_coverage",
    "publication_capability_coverage",
    "publication_entity_counts",
    "publication_deltas",
    "publication_delta_entities",
    "publication_delta_samples",
)
_ALLOWED_TABLES = frozenset(_ROW_ORDER)
_MUTABLE_COLUMNS = {
    "adapters": frozenset({"adapter_version", "capability_mask", "last_seen_publication_id"}),
    "source_producers": frozenset({"display_label", "last_seen_publication_id"}),
    "sources": frozenset(
        {
            "selected_history_preset",
            "selected_from_us",
            "selected_through_us",
            "last_seen_publication_id",
        }
    ),
    "source_manifestations": frozenset(
        {
            "size_bytes",
            "modified_at_us",
            "prefix_sha256",
            "suffix_sha256",
            "content_revision",
            "state",
            "time_range_start_us",
            "time_range_end_us",
            "time_range_confidence",
            "selected",
            "last_seen_publication_id",
            "ended_publication_id",
        }
    ),
    "projects": frozenset(
        {
            "label_candidates_json",
            "first_event_at_us",
            "last_event_at_us",
            "provenance_json",
            "last_seen_publication_id",
        }
    ),
    "resources": frozenset({"display_label", "provenance_json", "last_seen_publication_id"}),
    "model_profiles": frozenset({"last_seen_publication_id"}),
    "sessions": frozenset(
        {
            "root_session_id",
            "parent_session_id",
            "relationship_basis",
            "delegation_depth",
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "start_at_us",
            "end_at_us",
            "observed_duration_us",
            "completion_basis",
            "label_candidates_json",
            "primary_occurrence_id",
            "last_seen_publication_id",
        }
    ),
    "turns": frozenset(
        {
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "start_at_us",
            "end_at_us",
            "start_source_rank",
            "start_source_order",
            "end_source_order",
            "completion_basis",
            "membership_json",
            "primary_occurrence_id",
            "last_seen_publication_id",
        }
    ),
    "model_call_tail": frozenset(
        {
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "event_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "context_window_tokens",
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
            "token_basis",
            "finish_category",
            "error_category",
            "measurement_mask",
            "primary_occurrence_id",
            "last_seen_publication_id",
        }
    ),
    "tool_invocations": frozenset(
        {
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "terminal_at_us",
            "terminal_source_rank",
            "terminal_source_order",
            "terminal_event_kind_order",
            "terminal_transition_rank",
            "terminal_occurrence_id",
            "observed_duration_us",
            "output_bytes",
            "error_category",
            "measurement_mask",
            "last_seen_publication_id",
        }
    ),
    "activities": frozenset(
        {
            "lifecycle_state",
            "state_basis",
            "transition_version",
            "event_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "primary_occurrence_id",
            "last_seen_publication_id",
        }
    ),
    "context_components": frozenset(
        {
            "observed_utf8_bytes",
            "observed_event_count",
            "estimator",
            "estimated_tokens",
            "total_context_utf8_bytes",
            "inclusion_basis",
            "capability_basis",
            "measurement_basis",
            "event_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "measurement_mask",
            "primary_occurrence_id",
            "last_seen_publication_id",
        }
    ),
    "allowance_limits": frozenset({"last_seen_publication_id"}),
    "allowance_cycles": frozenset(
        {
            "start_at_us",
            "end_at_us",
            "completion_status",
            "last_seen_publication_id",
        }
    ),
    "allowance_observations": frozenset(
        {
            "plan_identity",
            "window_kind",
            "reset_identity",
            "used_percent",
            "remaining_percent",
            "absolute_fields_json",
            "reset_time_us",
            "observed_at_us",
            "source_rank",
            "source_order",
            "event_kind_order",
            "transition_rank",
            "measurement_mask",
            "primary_occurrence_id",
        }
    ),
}
_OBSERVATION_KINDS = {
    "ProjectObserved": "project",
    "SessionObserved": "session",
    "SessionRelationshipObserved": "session-relationship",
    "TurnBoundaryObserved": "turn",
    "ModelCallObserved": "call",
    "ToolLifecycleObserved": "tool",
    "ActivityLifecycleObserved": "activity",
    "CompactionObserved": "compaction",
    "ContextComponentObserved": "context-component",
    "ResourceObserved": "resource",
    "ToolResourceLinkObserved": "tool-resource-link",
    "StateChangeObserved": "state-change",
    "AllowanceObservationObserved": "allowance-observation",
    "AllowanceLimitObserved": "allowance-limit",
    "AdapterDiagnosticObserved": "diagnostic",
}
_LIFECYCLE_KINDS = {
    "SessionObserved": "session",
    "TurnBoundaryObserved": "turn",
    "ModelCallObserved": "model_call",
    "ToolLifecycleObserved": "tool_invocation",
    "ActivityLifecycleObserved": "activity",
}
_ENTITY_COUNT_NAMES = {
    "ProjectObserved": "projects",
    "SessionObserved": "sessions",
    "TurnBoundaryObserved": "turns",
    "ModelCallObserved": "model_calls",
    "ToolLifecycleObserved": "tool_invocations",
    "ActivityLifecycleObserved": "activities",
    "CompactionObserved": "compaction_boundaries",
    "ContextComponentObserved": "context_components",
    "ResourceObserved": "resources",
    "StateChangeObserved": "state_changes",
    "AllowanceObservationObserved": "allowance_observations",
    "AllowanceLimitObserved": "allowance_limits",
}
_ENTITY_TABLES = {
    "ProjectObserved": ("projects", "project_id"),
    "SessionObserved": ("sessions", "session_id"),
    "TurnBoundaryObserved": ("turns", "turn_id"),
    "ModelCallObserved": ("model_call_tail", "call_id"),
    "ToolLifecycleObserved": ("tool_invocations", "tool_id"),
    "ActivityLifecycleObserved": ("activities", "activity_id"),
    "CompactionObserved": ("compaction_boundaries", "compaction_id"),
    "ContextComponentObserved": ("context_components", "component_id"),
    "ResourceObserved": ("resources", "resource_id"),
    "StateChangeObserved": ("state_changes", "change_id"),
    "AllowanceObservationObserved": (
        "allowance_observations",
        "observation_id",
    ),
    "AllowanceLimitObserved": ("allowance_limits", "limit_id"),
}


def _digest(value: str, name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _state(observation: AdapterObservation) -> str:
    value = observation.payload.get("state")
    if value in {
        "pending",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "rolled_back",
        "open",
        "unknown",
    }:
        return str(value)
    if observation.observation_type == "ModelCallObserved":
        return "succeeded"
    return "unknown"


def _occurrence_tuple(logical_id: str, observation: AdapterObservation) -> tuple[object, ...]:
    source = observation.source_range
    return (
        logical_id,
        source.manifestation_id,
        source.source_revision,
        [source.byte_start, source.byte_end],
        source.record_ordinal,
        source.adapter_version,
    )


def _source_ids(inventory: SourceInventory, configured_producer_key: str) -> tuple[str, str]:
    producer_id = semantic_id("producer", [configured_producer_key])
    source_id = semantic_id(
        "source",
        [ADAPTER_ID, producer_id, inventory.source_kind, inventory.source_key],
    )
    return producer_id, source_id


def _prepared_rows(
    cursor: sqlite3.Cursor,
    table: str,
) -> tuple[PreparedRow, ...]:
    columns = tuple(str(item[0]) for item in cursor.description)
    return tuple(PreparedRow(table, dict(zip(columns, row, strict=True))) for row in cursor)


def _read_source_coverage(
    connection: sqlite3.Connection,
    publication_id: str,
) -> tuple[PreparedRow, ...]:
    return _prepared_rows(
        connection.execute(
            """
            SELECT *
            FROM publication_source_coverage
            WHERE publication_id = ?
            ORDER BY source_id
            """,
            (publication_id,),
        ),
        "publication_source_coverage",
    )


def _read_source_cursors(
    connection: sqlite3.Connection,
) -> tuple[SourceCursor, ...]:
    rows = connection.execute(
        """
        SELECT sm.manifestation_id, cursor.manifestation_key,
               cursor.source_revision, cursor.byte_offset,
               cursor.record_ordinal, cursor.source_size_bytes,
               cursor.prefix_through_cursor_sha256, cursor.suffix_sha256,
               cursor.latest_source_order, cursor.parser_version,
               cursor.adapter_version
        FROM source_cursors AS cursor
        JOIN source_manifestations AS sm
          ON sm.manifestation_key = cursor.manifestation_key
        ORDER BY cursor.manifestation_key
        """
    )
    return tuple(SourceCursor(*row) for row in rows)


def _read_affected_source_manifestations(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[int, PreparedRow]:
    result: dict[int, PreparedRow] = {}
    keys = sorted(
        {item.manifestation_key for item in (*changes.selected_sources, *changes.deferred_sources)}
    )
    for manifestation_key in keys:
        rows = _prepared_rows(
            connection.execute(
                """
                SELECT *
                FROM source_manifestations
                WHERE manifestation_key = ?
                """,
                (manifestation_key,),
            ),
            "source_manifestations",
        )
        if rows:
            result[manifestation_key] = rows[0]
    return result


def _read_existing_source_diagnostic_keys(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> frozenset[tuple[int, str, int, int, str]]:
    existing: set[tuple[int, str, int, int, str]] = set()
    for diagnostic in changes.diagnostics:
        source = diagnostic.source_range
        if source is None:
            continue
        key = (
            source.manifestation_key,
            source.source_revision,
            source.byte_start,
            source.byte_end,
            diagnostic.code,
        )
        row = connection.execute(
            """
            SELECT 1
            FROM source_diagnostics
            WHERE manifestation_key = ? AND source_revision = ?
              AND byte_start = ? AND byte_end = ? AND diagnostic_code = ?
            """,
            key,
        ).fetchone()
        if row is not None:
            existing.add(key)
    return frozenset(existing)


def _read_affected_entity_rows(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[str, PreparedRow]:
    result: dict[str, PreparedRow] = {}
    affected: set[tuple[str, str, str]] = set()
    for observation in changes.observations:
        table_spec = _ENTITY_TABLES.get(observation.observation_type)
        if table_spec is not None:
            affected.add((*table_spec, observation.logical_id))
        if observation.observation_type == "SessionObserved":
            native_project = str(observation.payload.get("project_id") or "unknown-project")
            affected.add(("projects", "project_id", semantic_id("project", [native_project])))
        elif observation.observation_type == "ResourceObserved":
            affected.add(
                (
                    "projects",
                    "project_id",
                    semantic_id("project", [str(observation.identity_tuple[0])]),
                )
            )
        elif observation.observation_type == "SessionRelationshipObserved":
            for session_id in (
                observation.payload.get("session_id"),
                observation.payload.get("parent_session_id"),
            ):
                if isinstance(session_id, str):
                    affected.add(("sessions", "session_id", session_id))
    for table, id_column, logical_id in sorted(affected):
        rows = _prepared_rows(
            connection.execute(
                f"SELECT * FROM {table} WHERE {id_column} = ?",
                (logical_id,),
            ),
            table,
        )
        if rows:
            result[logical_id] = rows[0]
    return result


def _read_existing_occurrence_ids(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> frozenset[str]:
    existing: set[str] = set()
    for occurrence in changes.occurrences:
        row = connection.execute(
            """
            SELECT occurrence_id
            FROM source_occurrences
            WHERE occurrence_id = ?
            """,
            (occurrence.occurrence_id,),
        ).fetchone()
        if row is not None:
            existing.add(str(row[0]))
    return frozenset(existing)


def _read_late_parent_versions(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[str, int]:
    child_ids = sorted(
        {
            str(observation.payload["session_id"])
            for observation in changes.observations
            if observation.observation_type == "SessionRelationshipObserved"
        }
    )
    result: dict[str, int] = {}
    for child_id in child_ids:
        row = connection.execute(
            """
            SELECT MAX(relationship_version)
            FROM late_parent_edges
            WHERE child_session_id = ?
            """,
            (child_id,),
        ).fetchone()
        if row is not None and row[0] is not None:
            result[child_id] = int(row[0])
    return result


def _read_late_parent_edges(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[tuple[str, str, str], PreparedRow]:
    child_ids = sorted(
        {
            str(observation.payload["session_id"])
            for observation in changes.observations
            if observation.observation_type == "SessionRelationshipObserved"
        }
    )
    result: dict[tuple[str, str, str], PreparedRow] = {}
    for child_id in child_ids:
        rows = _prepared_rows(
            connection.execute(
                """
                SELECT *
                FROM late_parent_edges
                WHERE child_session_id = ?
                ORDER BY relationship_version
                """,
                (child_id,),
            ),
            "late_parent_edges",
        )
        for row in rows:
            key = (
                child_id,
                str(row.values["parent_session_id"]),
                str(row.values["relationship_basis"]),
            )
            result[key] = row
    return result


def _read_allowance_predecessors(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[tuple[str, ...], PreparedRow]:
    keys = sorted(
        {
            tuple(
                str(observation.payload[field])
                for field in (
                    "provider",
                    "limit_id",
                    "plan_identity",
                    "window_kind",
                    "cycle_id",
                    "reset_identity",
                )
            )
            for observation in changes.observations
            if observation.observation_type == "AllowanceObservationObserved"
        }
    )
    result: dict[tuple[str, ...], PreparedRow] = {}
    for key in keys:
        row = connection.execute(
            """
            SELECT ao.observation_id, al.provider, ao.limit_id,
                   ao.plan_identity, ao.window_kind, ao.cycle_id,
                   ao.reset_identity, ao.observed_at_us, ao.source_rank,
                   ao.source_order, ao.event_kind_order, ao.transition_rank,
                   ao.used_percent, ao.remaining_percent
            FROM allowance_observations AS ao
            JOIN allowance_limits AS al ON al.limit_id = ao.limit_id
            WHERE al.provider = ? AND ao.limit_id = ?
              AND ao.plan_identity = ? AND ao.window_kind = ?
              AND ao.cycle_id = ? AND ao.reset_identity = ?
              AND ao.observed_at_us IS NOT NULL
            ORDER BY (ao.observed_at_us IS NULL) DESC,
                     ao.observed_at_us DESC, ao.source_rank DESC,
                     ao.source_order DESC, ao.event_kind_order DESC,
                     ao.observation_id DESC, ao.transition_rank DESC
            LIMIT 1
            """,
            key,
        ).fetchone()
        if row is not None:
            columns = (
                "observation_id",
                "provider",
                "limit_id",
                "plan_identity",
                "window_kind",
                "cycle_id",
                "reset_identity",
                "observed_at_us",
                "source_rank",
                "source_order",
                "event_kind_order",
                "transition_rank",
                "used_percent",
                "remaining_percent",
            )
            result[key] = PreparedRow(
                "allowance_observations",
                dict(zip(columns, row, strict=True)),
            )
    return result


def _read_allowance_intervals(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> dict[str, PreparedRow]:
    observation_ids = sorted(
        {
            observation.logical_id
            for observation in changes.observations
            if observation.observation_type == "AllowanceObservationObserved"
        }
    )
    if not observation_ids:
        return {}
    placeholders = ", ".join("?" for _ in observation_ids)
    rows = _prepared_rows(
        connection.execute(
            f"""
            SELECT *
            FROM allowance_intervals
            WHERE start_observation_id IN ({placeholders})
               OR end_observation_id IN ({placeholders})
            ORDER BY interval_id
            """,
            (*observation_ids, *observation_ids),
        ),
        "allowance_intervals",
    )
    return {str(row.values["interval_id"]): row for row in rows}


def _read_unaffected_tail_state(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
    tail_state: ModelCallTailState | None,
) -> ModelCallTailState | None:
    if tail_state is None:
        return None
    affected_ids = sorted(
        {
            observation.logical_id
            for observation in changes.observations
            if observation.observation_type == "ModelCallObserved"
        }
    )
    if not affected_ids:
        return tail_state
    placeholders = ", ".join("?" for _ in affected_ids)
    row = connection.execute(
        f"""
        SELECT COUNT(*), MIN(event_at_us), MAX(event_at_us),
               MAX(source_order)
        FROM model_call_tail
        WHERE call_id NOT IN ({placeholders})
        """,
        tuple(affected_ids),
    ).fetchone()
    assert row is not None
    return ModelCallTailState(
        row_count=int(row[0]),
        minimum_event_at_us=row[1],
        maximum_event_at_us=row[2],
        maximum_source_order=row[3],
        base_publication_id=tail_state.base_publication_id,
        last_fold_publication_id=tail_state.last_fold_publication_id,
    )


def read_prior_publication_snapshot(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
) -> PriorPublicationSnapshot:
    """Read the bounded prior state needed for pure write-set preparation.

    Callers take this snapshot before entering the short writer transaction.
    Lifecycle history is fetched only for logical entities affected by the
    proposed change set.
    """

    head = connection.execute(
        "SELECT publication_id FROM publication_head WHERE singleton = 1"
    ).fetchone()
    if head is None:
        return PriorPublicationSnapshot()
    publication_id = str(head[0])
    rate_card_frontier = validate_publication_rate_card_frontier(
        connection,
        publication_id,
    )
    entity_counts = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            """
            SELECT entity_kind, entity_count
            FROM publication_entity_counts
            WHERE publication_id = ?
            ORDER BY entity_kind
            """,
            (publication_id,),
        )
    }
    affected_lifecycle_ids = sorted(
        {
            observation.logical_id
            for observation in changes.observations
            if observation.observation_type in _LIFECYCLE_KINDS
        }
    )
    repository = LifecycleRepository(connection)
    lifecycle = {
        logical_id: transitions
        for logical_id in affected_lifecycle_ids
        if (transitions := repository.transitions_for(logical_id))
    }
    tail_row = connection.execute(
        """
        SELECT row_count, minimum_event_at_us, maximum_event_at_us,
               maximum_source_order, base_publication_id,
               last_fold_publication_id
        FROM model_call_tail_state
        WHERE singleton = 1
        """
    ).fetchone()
    tail_state = None if tail_row is None else ModelCallTailState(*tail_row)
    unaffected_tail_state = _read_unaffected_tail_state(connection, changes, tail_state)
    source_revisions: dict[int, str] = {}
    manifestation_keys = sorted(
        {
            item.manifestation_key
            for item in (
                *changes.selected_sources,
                *changes.deferred_sources,
            )
        }
    )
    for manifestation_key in manifestation_keys:
        row = connection.execute(
            """
            SELECT content_revision
            FROM source_manifestations
            WHERE manifestation_key = ?
            """,
            (manifestation_key,),
        ).fetchone()
        if row is not None:
            source_revisions[manifestation_key] = str(row[0])
    return PriorPublicationSnapshot(
        entity_counts=entity_counts,
        lifecycle=lifecycle,
        tail_state=tail_state,
        unaffected_tail_state=unaffected_tail_state,
        source_revisions=source_revisions,
        source_coverage=_read_source_coverage(connection, publication_id),
        source_cursors=_read_source_cursors(connection),
        source_manifestations=_read_affected_source_manifestations(connection, changes),
        source_diagnostic_keys=_read_existing_source_diagnostic_keys(connection, changes),
        entity_rows=_read_affected_entity_rows(connection, changes),
        occurrence_ids=_read_existing_occurrence_ids(connection, changes),
        late_parent_versions=_read_late_parent_versions(connection, changes),
        late_parent_edges=_read_late_parent_edges(connection, changes),
        allowance_predecessors=_read_allowance_predecessors(connection, changes),
        allowance_intervals=_read_allowance_intervals(connection, changes),
        rate_card_frontier=rate_card_frontier,
    )


def prepare_write_set_from_changes(
    changes: ProposedChangeSet,
    request: PublicationRequest,
    *,
    configured_producer_key: str = "local-codex",
    prior: PriorPublicationSnapshot | None = None,
    inventory_started_at_us: int | None = None,
    inventory_completed_at_us: int | None = None,
) -> PublicationWriteSet:
    """Purely prepare CK-06 observations for the short writer transaction."""

    changes.assert_body_free()
    prior_was_provided = prior is not None
    if prior is None:
        prior = PriorPublicationSnapshot()
    if not (
        changes.observations
        or changes.occurrences
        or changes.cursor_updates
        or changes.diagnostics
        or changes.selected_sources
        or changes.deferred_sources
    ) and not prior_was_provided:
        return PublicationWriteSet(changes, (), ())
    # Imported lazily so preparation can use the public writer value types
    # without introducing a new public module dependency.
    from .preparation import prepare_write_set  # noqa: PLC0415

    return prepare_write_set(
        changes,
        request,
        configured_producer_key=configured_producer_key,
        prior=prior,
        inventory_started_at_us=inventory_started_at_us,
        inventory_completed_at_us=inventory_completed_at_us,
    )


def planned_artifact_manifest_sha256(
    plan: PublicationPlan,
    request: PublicationRequest,
    write_set: PublicationWriteSet,
) -> str:
    """Compute the exact nonrecursive manifest digest before taking the lock."""

    coverage = sorted(
        (
            list(row.values.values())
            for row in write_set.rows
            if row.table == "publication_source_coverage"
        ),
        key=lambda values: str(values[1]),
    )
    entity_counts = {
        str(row.values["entity_kind"]): int(row.values["entity_count"])
        for row in write_set.rows
        if row.table == "publication_entity_counts"
    }
    delta_rows = [
        list(row.values.values()) for row in write_set.rows if row.table == "publication_deltas"
    ]
    cursor_rows = [
        [
            cursor.manifestation_key,
            cursor.source_revision,
            cursor.byte_offset,
            cursor.record_ordinal,
            cursor.source_size_bytes,
            cursor.prefix_through_cursor_sha256,
            cursor.suffix_sha256,
            cursor.latest_source_order,
            cursor.parser_version,
            cursor.adapter_version,
        ]
        for cursor in sorted(
            write_set.cursor_snapshot,
            key=lambda item: item.manifestation_key,
        )
    ]
    manifest = {
        "publication_id": request.publication_id,
        "parent_publication_id": plan.parent_publication_id,
        "schema_contract_sha256": SCHEMA_CONTRACT_SHA256,
        "source_cursor_inventory_sha256": hashlib.sha256(
            json.dumps(
                cursor_rows,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "coverage": coverage,
        "entity_counts": dict(sorted(entity_counts.items())),
        "publication_delta": None if not delta_rows else delta_rows[0],
        "projection_registry_sha256": request.projection_registry_sha256,
        "active_rate_card_digest": request.rate_card_digest,
        "database_identity": "codex-usage-tracker.agent-kernel.v1",
        "schema_contract": SCHEMA_CONTRACT_SHA256,
    }
    return artifact_manifest_sha256(manifest)


class PublicationWriter:
    """Commit one planner-proven small change set atomically."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._table_specs: dict[str, _TableSpec] = {}

    def publish(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PublicationResult:
        started = time.perf_counter_ns()
        injector = fault_injector or (lambda _stage: None)
        if plan.operation_class is OperationClass.NO_CHANGE:
            return self._no_change_result(plan, request, write_set, started)
        self._validate_append_request(plan, request, write_set)
        replay = self._replay_result(request, started)
        if replay is not None:
            return replay
        result = self._publish_transaction(plan, request, write_set, injector, started)
        if isinstance(result, PublicationResult):
            return result
        inserted_occurrences, transaction_elapsed_ns = result
        return PublicationResult(
            request.publication_id,
            request.operation_id,
            False,
            False,
            inserted_occurrences,
            time.perf_counter_ns() - started,
            transaction_elapsed_ns,
        )

    def publish_with_pointer(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
        *,
        pointer_path: Path,
        operational_store: OperationalStore,
        pointer_request: SmallPublicationRequest,
        worker_is_alive: WorkerProbe,
        validate_open: ArtifactValidator,
        fault_injector: FaultInjector | None = None,
        recovery_fault: FaultHook | None = None,
    ) -> PublicationResult:
        """Commit a small publication through the fenced pointer coordinator."""

        if (
            plan.operation_class
            not in {OperationClass.APPEND_SAFE_SMALL, OperationClass.VALUATION_ONLY}
            or not plan.analytical_write_required
        ):
            raise PublicationWriteError(
                "pointer coordination accepts append-safe-small or valuation-only "
                "publications only"
            )
        if (
            pointer_request.operation_id != request.operation_id
            or pointer_request.expected_active_publication_id != plan.parent_publication_id
            or request.parent_publication_id != plan.parent_publication_id
        ):
            raise PublicationConflictError(
                "pointer coordination request differs from the analytical publication"
            )

        from .recovery import AnalyticalHead, publish_small_with_pointer  # noqa: PLC0415

        committed: PublicationResult | None = None

        def commit() -> AnalyticalHead:
            nonlocal committed
            committed = self.publish(
                plan,
                request,
                write_set,
                fault_injector=fault_injector,
            )
            if committed.no_change or committed.publication_id != request.publication_id:
                raise PublicationWriteError(
                    "small pointer coordination requires one committed publication"
                )
            return AnalyticalHead(
                publication_id=request.publication_id,
                parent_publication_id=request.parent_publication_id,
                operation_id=request.operation_id,
                artifact_manifest_sha256=request.artifact_manifest_sha256,
                schema_contract_sha256=SCHEMA_CONTRACT_SHA256,
            )

        publish_small_with_pointer(
            pointer_path,
            store=operational_store,
            request=pointer_request,
            worker_is_alive=worker_is_alive,
            validate_open=validate_open,
            commit_analytical=commit,
            fault=recovery_fault,
        )
        assert committed is not None
        return committed

    def _no_change_result(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
        started: int,
    ) -> PublicationResult:
        if plan.analytical_write_required:
            raise PublicationWriteError("no-change plan cannot require an analytical write")
        if (
            write_set.changes.observations
            or write_set.changes.occurrences
            or write_set.changes.cursor_updates
            or write_set.rows
            or write_set.lifecycle_transitions
        ):
            raise PublicationWriteError("no-change plan contains analytical mutations")
        head = self._connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()
        return PublicationResult(
            None if head is None else str(head[0]),
            request.operation_id,
            True,
            False,
            0,
            time.perf_counter_ns() - started,
        )

    def _validate_append_request(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
    ) -> None:
        if (
            plan.operation_class
            not in {OperationClass.APPEND_SAFE_SMALL, OperationClass.VALUATION_ONLY}
            or not plan.analytical_write_required
        ):
            raise PublicationWriteError(
                "short writer accepts append_safe_small or valuation_only plans only"
            )
        if plan.parent_publication_id != request.parent_publication_id:
            raise PublicationWriteError("publication request and plan disagree on parent")
        self._validate_write_set(plan, request, write_set)

    def _replay_result(
        self,
        request: PublicationRequest,
        started: int,
    ) -> PublicationResult | None:
        replay = self._operation_publication(request.operation_id)
        if replay is None:
            return None
        if replay != request.publication_id:
            raise PublicationConflictError("operation ID already belongs to another publication")
        return PublicationResult(
            replay,
            request.operation_id,
            False,
            True,
            0,
            time.perf_counter_ns() - started,
        )

    def _publish_transaction(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
        injector: FaultInjector,
        started: int,
    ) -> tuple[int, int] | PublicationResult:
        identities = self._encode_identities(write_set.identities)
        early_rows = self._ordered_rows(write_set.rows, before_occurrences=True)
        late_rows = self._ordered_rows(write_set.rows, before_occurrences=False)
        occurrences = self._occurrence_values(write_set, request)
        lifecycle = tuple(
            self._lifecycle_values(transition) for transition in write_set.lifecycle_transitions
        )
        transaction_started = time.perf_counter_ns()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            injector("after_begin")
            replay = self._replay_result(request, started)
            if replay is not None:
                self._connection.rollback()
                return replay
            self._recheck_parent(plan.parent_publication_id)
            self._recheck_sources(write_set)
            injector("after_recheck")
            self._insert_publication(plan, request)
            injector("after_publication")
            self._register_identities(identities, request.publication_id)
            self._apply_rows(early_rows)
            inserted_occurrences = self._write_occurrences(occurrences)
            injector("after_occurrences")
            self._write_facts(lifecycle, late_rows)
            injector("after_facts")
            self._write_metadata(plan, request, write_set)
            injector("after_metadata")
            self._activate_head(request)
            injector("after_head")
            injector("before_commit")
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return (
            inserted_occurrences,
            time.perf_counter_ns() - transaction_started,
        )

    def _write_occurrences(
        self,
        occurrences: tuple[tuple[object, ...], ...],
    ) -> int:
        if not occurrences:
            return 0
        before = self._connection.total_changes
        self._execute_values(
            """
            INSERT INTO source_occurrences (
              occurrence_id, semantic_logical_id, manifestation_key,
              source_revision, record_ordinal, byte_start, byte_end,
              adapter_version, first_seen_publication_id
            ) VALUES
            """,
            occurrences,
            " ON CONFLICT DO NOTHING",
        )
        inserted = self._connection.total_changes - before
        if inserted != len(occurrences):
            self._validate_existing_occurrences(occurrences)
        return inserted

    def _write_facts(
        self,
        lifecycle: tuple[tuple[object, ...], ...],
        rows: tuple[PreparedRow, ...],
    ) -> None:
        self._apply_rows(rows)
        self._insert_lifecycle_many(lifecycle)

    def _write_metadata(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
    ) -> None:
        self._write_progress(write_set, request)
        self._write_tail_state(write_set.tail_state)
        self._reconcile_local(plan, write_set)
        self._activate_rate_card(request)
        try:
            validate_publication_rate_card_frontier(
                self._connection,
                request.publication_id,
            )
        except RateCardFrontierError as error:
            raise PublicationWriteError(
                f"publication rate-card frontier invalid: {error}"
            ) from error
        actual_manifest = artifact_manifest_sha256(
            manifest_from_database(
                self._connection,
                request.publication_id,
                projection_registry_sha256=request.projection_registry_sha256,
                active_rate_card_digest=request.rate_card_digest,
            )
        )
        if actual_manifest != request.artifact_manifest_sha256:
            raise PublicationWriteError("artifact manifest differs from the planner-proven digest")

    def _activate_rate_card(self, request: PublicationRequest) -> None:
        if request.rate_card_digest is None:
            return
        row = self._connection.execute(
            "SELECT rate_card_id FROM rate_card_revisions WHERE digest = ?",
            (request.rate_card_digest,),
        ).fetchone()
        if row is None:
            raise PublicationWriteError("publication rate-card head revision is missing")
        self._connection.execute(
            """
            INSERT INTO active_rate_card(
                singleton,
                rate_card_id,
                selected_at_us,
                publication_id
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
              rate_card_id = excluded.rate_card_id,
              selected_at_us = CASE
                WHEN active_rate_card.rate_card_id = excluded.rate_card_id
                THEN active_rate_card.selected_at_us
                ELSE excluded.selected_at_us
              END,
              publication_id = excluded.publication_id
            """,
            (row[0], request.committed_at_us, request.publication_id),
        )

    def _activate_head(self, request: PublicationRequest) -> None:
        self._connection.execute(
            """
            INSERT INTO publication_head(singleton, publication_id, activated_at_us)
            VALUES (1, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
              publication_id = excluded.publication_id,
              activated_at_us = excluded.activated_at_us
            """,
            (request.publication_id, request.committed_at_us),
        )

    def _operation_publication(self, operation_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT publication_id FROM publications WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def _validate_write_set(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: PublicationWriteSet,
    ) -> None:
        foreign_keys = self._connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or int(foreign_keys[0]) != 1:
            raise PublicationWriteError("short writer requires SQLite foreign-key enforcement")
        write_set.changes.assert_body_free()
        if len(write_set.changes.observations) > plan.estimate.observations:
            raise PublicationLimitError("observations exceed the planner estimate")
        if len(write_set.changes.occurrences) > plan.estimate.occurrences:
            raise PublicationLimitError("occurrences exceed the planner estimate")
        occurrence_ids = {item.occurrence_id for item in write_set.changes.occurrences}
        if any(item.occurrence_id not in occurrence_ids for item in write_set.changes.observations):
            raise PublicationWriteError("an observation lost its physical occurrence")
        if write_set.tail_state is not None and write_set.tail_state.row_count > 32_000:
            raise PublicationLimitError("model-call tail exceeds 32000 rows")
        if plan.estimate.projection_rows:
            raise PublicationLimitError("CK-07 short writer has no admitted projection rows")
        for prepared in write_set.rows:
            if prepared.table not in _ALLOWED_TABLES:
                raise PublicationWriteError(f"writer table is not admitted: {prepared.table}")
            if tuple(prepared.values) != self._table_spec(prepared.table).columns:
                raise PublicationWriteError(
                    f"{prepared.table} row does not match the schema-exact column inventory"
                )
            if not set(prepared.update_columns) <= _MUTABLE_COLUMNS.get(
                prepared.table, frozenset()
            ):
                raise PublicationWriteError(
                    f"{prepared.table} attempts to update immutable columns"
                )
            validate_storage_scalars(dict(prepared.values))
        for mutation in write_set.identities:
            if (
                mutation.enforce_semantic_id
                and semantic_id(mutation.entity_kind, mutation.identity_tuple)
                != mutation.logical_id
            ):
                raise PublicationWriteError(
                    f"identity does not reproduce logical ID: {mutation.logical_id}"
                )
        if request.publication_id == plan.parent_publication_id:
            raise PublicationWriteError("publication cannot parent itself")
        self._validate_turn_provenance(write_set)

    def _validate_turn_provenance(self, write_set: PublicationWriteSet) -> None:
        """Validate the persisted turn coordinate before any writer mutation.

        A turn's primary occurrence is the only admissible bridge to its source
        manifestation.  The check stays on the prepared write set so an
        invalid or mixed cohort cannot reach the transaction and rely on a
        deferred foreign-key error after partial work.
        """

        turn_rows = [row for row in write_set.rows if row.table == "turns"]
        if not turn_rows:
            return

        observations: dict[str, list[AdapterObservation]] = {}
        for observation in write_set.changes.observations:
            if observation.observation_type == "TurnBoundaryObserved":
                observations.setdefault(observation.logical_id, []).append(observation)

        occurrences: dict[str, ProposedOccurrence] = {}
        for occurrence in write_set.changes.occurrences:
            occurrence_id = occurrence.occurrence_id
            previous = occurrences.get(occurrence_id)
            if previous is not None and previous != occurrence:
                raise PublicationWriteError(
                    f"primary occurrence is ambiguous: {occurrence_id}"
                )
            occurrences[occurrence_id] = occurrence

        inventories: dict[int, SourceInventory] = {}
        for inventory in (
            *write_set.changes.selected_sources,
            *write_set.changes.deferred_sources,
        ):
            previous_inventory = inventories.get(inventory.manifestation_key)
            if previous_inventory is not None and previous_inventory != inventory:
                raise PublicationWriteError(
                    "source manifestation is ambiguous: "
                    f"{inventory.manifestation_key}"
                )
            inventories[inventory.manifestation_key] = inventory

        for row in turn_rows:
            turn_id = str(row.values["turn_id"])
            candidates = observations.get(turn_id, [])
            if not candidates:
                raise PublicationWriteError(
                    f"turn primary occurrence has no source observation: {turn_id}"
                )
            selected = max(candidates, key=lambda item: item.sort_key)
            tied = [item for item in candidates if item.sort_key == selected.sort_key]
            if len(tied) != 1:
                raise PublicationWriteError(
                    f"turn primary occurrence is ambiguous: {turn_id}"
                )

            occurrence_id = str(row.values["primary_occurrence_id"])
            if occurrence_id != selected.occurrence_id:
                raise PublicationWriteError(
                    f"turn primary occurrence does not match observation: {turn_id}"
                )
            resolved_occurrence = occurrences.get(occurrence_id)
            if resolved_occurrence is None:
                raise PublicationWriteError(
                    f"turn primary occurrence is unresolved: {occurrence_id}"
                )
            if resolved_occurrence.semantic_logical_id != turn_id:
                raise PublicationWriteError(
                    f"turn primary occurrence belongs to another entity: {turn_id}"
                )

            source = resolved_occurrence.source_range
            resolved_inventory = inventories.get(source.manifestation_key)
            if resolved_inventory is None:
                raise PublicationWriteError(
                    "turn primary occurrence has no source manifestation: "
                    f"{occurrence_id}"
                )
            if (
                resolved_inventory.manifestation_id != source.manifestation_id
                or resolved_inventory.content_revision != source.source_revision
            ):
                raise PublicationWriteError(
                    f"turn occurrence/manifestation provenance mismatches: {turn_id}"
                )

            expected_order = selected.source_order
            if expected_order is None:
                expected_order = source.record_ordinal
            if expected_order is None:
                raise PublicationWriteError(
                    f"turn source order provenance is missing: {turn_id}"
                )
            if selected.source_rank != resolved_inventory.source_rank:
                raise PublicationWriteError(
                    f"turn source rank mismatches its manifestation: {turn_id}"
                )
            if row.values["start_source_rank"] != resolved_inventory.source_rank:
                raise PublicationWriteError(
                    f"turn persisted source rank mismatches provenance: {turn_id}"
                )
            if row.values["start_source_order"] != expected_order:
                raise PublicationWriteError(
                    f"turn persisted source order mismatches provenance: {turn_id}"
                )

            start_at_us = row.values["start_at_us"]
            end_at_us = row.values["end_at_us"]
            end_source_order = row.values["end_source_order"]
            if end_at_us is not None and start_at_us is not None and start_at_us > end_at_us:
                raise PublicationWriteError(
                    f"turn lifecycle times are reversed: {turn_id}"
                )
            if end_source_order is not None and end_source_order < expected_order:
                raise PublicationWriteError(
                    f"turn lifecycle source order is reversed: {turn_id}"
                )
            if end_at_us is not None and end_source_order is None:
                raise PublicationWriteError(
                    f"terminal turn is missing end source order: {turn_id}"
                )

    def _recheck_parent(self, expected: str | None) -> None:
        row = self._connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()
        actual = None if row is None else str(row[0])
        if actual != expected:
            raise PublicationConflictError(
                f"publication parent changed: expected={expected!r}, actual={actual!r}"
            )

    def _recheck_sources(self, write_set: PublicationWriteSet) -> None:
        for item in (*write_set.changes.selected_sources, *write_set.changes.deferred_sources):
            row = self._connection.execute(
                "SELECT content_revision FROM source_manifestations WHERE manifestation_key = ?",
                (item.manifestation_key,),
            ).fetchone()
            actual = None if row is None else str(row[0])
            expected = write_set.expected_source_revisions.get(item.manifestation_key)
            if actual != expected:
                raise PublicationConflictError(
                    f"source revision changed for manifestation {item.manifestation_key}"
                )

    def _insert_publication(self, plan: PublicationPlan, request: PublicationRequest) -> None:
        self._connection.execute(
            """
            INSERT INTO publications (
              publication_id, parent_publication_id, operation_id,
              schema_contract_id, schema_contract_sha256, identity_version,
              adapter_id, adapter_version, normalization_version,
              projection_registry_sha256, rate_card_digest, history_preset,
              requested_cutoff_us, committed_at_us, observed_through_us,
              indexed_from_us, indexed_through_us, guaranteed_complete_from_us,
              artifact_manifest_sha256, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'committed')
            """,
            (
                request.publication_id,
                plan.parent_publication_id,
                request.operation_id,
                SCHEMA_CONTRACT_ID,
                SCHEMA_CONTRACT_SHA256,
                request.identity_version,
                request.adapter_id,
                request.adapter_version,
                request.normalization_version,
                request.projection_registry_sha256,
                request.rate_card_digest,
                request.history_preset,
                request.requested_cutoff_us,
                request.committed_at_us,
                request.observed_through_us,
                request.indexed_from_us,
                request.indexed_through_us,
                request.guaranteed_complete_from_us,
                request.artifact_manifest_sha256,
            ),
        )

    def _table_spec(self, table: str) -> _TableSpec:
        cached = self._table_specs.get(table)
        if cached is not None:
            return cached
        information = tuple(self._connection.execute(f"PRAGMA table_info({table})"))
        spec = _TableSpec(
            tuple(str(row[1]) for row in information),
            tuple(
                str(row[1])
                for row in sorted(information, key=lambda row: int(row[5]))
                if int(row[5]) > 0
            ),
        )
        self._table_specs[table] = spec
        return spec

    @staticmethod
    def _encode_identities(
        identities: Iterable[IdentityMutation],
    ) -> tuple[_EncodedIdentity, ...]:
        by_logical_id: dict[str, _EncodedIdentity] = {}
        by_digest: dict[tuple[str, str], str] = {}
        for mutation in identities:
            encoded = canonical_cbor(mutation.identity_tuple)
            prepared = _EncodedIdentity(
                mutation.logical_id,
                mutation.entity_kind,
                encoded,
                hashlib.sha256(encoded).hexdigest(),
            )
            existing = by_logical_id.get(mutation.logical_id)
            if existing is not None and existing != prepared:
                raise PublicationWriteError(
                    f"identity conflicts within write set: {mutation.logical_id}"
                )
            digest_key = (prepared.entity_kind, prepared.identity_sha256)
            digest_owner = by_digest.get(digest_key)
            if digest_owner is not None and digest_owner != prepared.logical_id:
                raise PublicationWriteError("identity tuple belongs to multiple logical IDs")
            by_logical_id[prepared.logical_id] = prepared
            by_digest[digest_key] = prepared.logical_id
        return tuple(by_logical_id[key] for key in sorted(by_logical_id))

    @staticmethod
    def _occurrence_values(
        write_set: PublicationWriteSet,
        request: PublicationRequest,
    ) -> tuple[tuple[object, ...], ...]:
        result: list[tuple[object, ...]] = []
        for occurrence in write_set.changes.occurrences:
            if occurrence.occurrence_id in write_set.existing_occurrence_ids:
                continue
            source = occurrence.source_range
            record = SourceOccurrence(
                occurrence.occurrence_id,
                occurrence.semantic_logical_id,
                source.manifestation_key,
                source.source_revision,
                source.record_ordinal,
                source.byte_start,
                source.byte_end,
                source.adapter_version,
                request.publication_id,
            )
            values = (
                record.occurrence_id,
                record.semantic_logical_id,
                record.manifestation_key,
                record.source_revision,
                record.record_ordinal,
                record.byte_start,
                record.byte_end,
                record.adapter_version,
                record.first_seen_publication_id,
            )
            validate_storage_scalars(
                dict(
                    zip(
                        (
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
                        values,
                        strict=True,
                    )
                )
            )
            result.append(values)
        return tuple(result)

    @staticmethod
    def _lifecycle_values(
        transition: LifecycleTransition,
    ) -> tuple[object, ...]:
        return (
            transition.transition_id,
            transition.entity_logical_id,
            transition.entity_kind,
            transition.lifecycle_state,
            transition.state_basis,
            transition.transition_version,
            transition.transition_at_us,
            transition.source_rank,
            transition.source_order,
            transition.event_kind_order,
            transition.transition_rank,
            transition.occurrence_id,
            transition.terminal_error_category,
            transition.measurement_mask,
            transition.first_seen_publication_id,
            transition.session_id,
        )

    def _validate_existing_identities(
        self,
        identities: tuple[_EncodedIdentity, ...],
    ) -> None:
        placeholders = ", ".join("?" for _ in identities)
        existing = {
            str(row[0]): (str(row[1]), bytes(row[2]), str(row[3]))
            for row in self._connection.execute(
                f"""
                SELECT logical_id, entity_kind, identity_cbor, identity_sha256
                FROM identity_registry
                WHERE logical_id IN ({placeholders})
                """,
                tuple(item.logical_id for item in identities),
            )
        }
        for item in identities:
            current = existing.get(item.logical_id)
            expected = (
                item.entity_kind,
                item.identity_cbor,
                item.identity_sha256,
            )
            if current is not None and current != expected:
                raise PublicationWriteError(f"stable identity conflicts: {item.logical_id}")

    def _register_identities(
        self,
        identities: tuple[_EncodedIdentity, ...],
        publication_id: str,
    ) -> None:
        if not identities:
            return
        self._validate_existing_identities(identities)
        values = tuple(
            (
                item.logical_id,
                item.entity_kind,
                "v1",
                item.identity_cbor,
                item.identity_sha256,
                publication_id,
                publication_id,
            )
            for item in identities
        )
        try:
            self._execute_values(
                """
                INSERT INTO identity_registry (
                  logical_id, entity_kind, identity_version, identity_cbor,
                  identity_sha256, first_seen_publication_id,
                  last_seen_publication_id
                ) VALUES
                """,
                values,
                """
                ON CONFLICT(logical_id) DO UPDATE SET
                  last_seen_publication_id = excluded.last_seen_publication_id
                """,
            )
        except sqlite3.IntegrityError as error:
            raise PublicationWriteError(
                "identity tuple collides with another logical ID"
            ) from error

    def _ordered_rows(
        self, rows: tuple[PreparedRow, ...], *, before_occurrences: bool
    ) -> tuple[PreparedRow, ...]:
        early = {"adapters", "source_producers", "sources", "source_manifestations"}
        selected = [row for row in rows if (row.table in early) is before_occurrences]
        rank = {table: index for index, table in enumerate(_ROW_ORDER)}
        return tuple(
            sorted(
                selected, key=lambda row: (rank[row.table], tuple(map(str, row.values.values())))
            )
        )

    @staticmethod
    def _deduplicate_rows(
        rows: tuple[PreparedRow, ...],
    ) -> tuple[PreparedRow, ...]:
        unique: dict[tuple[tuple[str, object], ...], PreparedRow] = {}
        for row in rows:
            unique.setdefault(tuple(row.values.items()), row)
        return tuple(unique.values())

    def _apply_rows(self, rows: tuple[PreparedRow, ...]) -> None:
        index = 0
        while index < len(rows):
            prepared = rows[index]
            end = index + 1
            while (
                end < len(rows)
                and rows[end].table == prepared.table
                and rows[end].update_columns == prepared.update_columns
            ):
                end += 1
            self._apply_row_batch(self._deduplicate_rows(rows[index:end]))
            index = end

    def _apply_row_batch(self, rows: tuple[PreparedRow, ...]) -> None:
        if not rows:
            return
        prepared = rows[0]
        columns = tuple(prepared.values)
        columns_sql = ", ".join(columns)
        spec = self._table_spec(prepared.table)
        primary = spec.primary
        if prepared.update_columns:
            target = ", ".join(primary)
            assignments = ", ".join(
                f"{column} = excluded.{column}" for column in prepared.update_columns
            )
            conflict = f" ON CONFLICT({target}) DO UPDATE SET {assignments}"
        else:
            conflict = " ON CONFLICT DO NOTHING"
        before = self._connection.total_changes
        values = tuple(tuple(row.values[column] for column in columns) for row in rows)
        self._execute_values(
            f"INSERT INTO {prepared.table} ({columns_sql}) VALUES",
            values,
            conflict,
        )
        changed = self._connection.total_changes - before
        if not prepared.update_columns and changed != len(rows):
            self._validate_existing_rows(rows, spec)

    def _insert_lifecycle_many(
        self,
        lifecycle: tuple[tuple[object, ...], ...],
    ) -> None:
        if not lifecycle:
            return
        before = self._connection.total_changes
        self._execute_values(
            """
            INSERT INTO lifecycle_transitions
            VALUES
            """,
            lifecycle,
            " ON CONFLICT DO NOTHING",
        )
        if self._connection.total_changes - before != len(lifecycle):
            self._validate_existing_lifecycle(lifecycle)

    def _validate_existing_rows(
        self,
        rows: tuple[PreparedRow, ...],
        spec: _TableSpec,
    ) -> None:
        columns_sql = ", ".join(spec.columns)
        where = " AND ".join(f"{column} IS ?" for column in spec.primary)
        for prepared in rows:
            existing = self._connection.execute(
                f"SELECT {columns_sql} FROM {prepared.table} WHERE {where}",
                tuple(prepared.values[column] for column in spec.primary),
            ).fetchone()
            if existing is None or tuple(existing) != tuple(prepared.values.values()):
                raise PublicationConflictError(f"canonical row conflicts in {prepared.table}")

    def _validate_existing_occurrences(
        self,
        occurrences: tuple[tuple[object, ...], ...],
    ) -> None:
        for values in occurrences:
            existing = self._connection.execute(
                """
                SELECT occurrence_id, semantic_logical_id, manifestation_key,
                       source_revision, record_ordinal, byte_start, byte_end,
                       adapter_version, first_seen_publication_id
                FROM source_occurrences
                WHERE occurrence_id = ?
                """,
                (values[0],),
            ).fetchone()
            if existing is None or tuple(existing) != values:
                raise PublicationConflictError(f"source occurrence conflicts: {values[0]}")

    def _validate_existing_lifecycle(
        self,
        lifecycle: tuple[tuple[object, ...], ...],
    ) -> None:
        for values in lifecycle:
            existing = self._connection.execute(
                """
                SELECT *
                FROM lifecycle_transitions
                WHERE transition_id = ?
                """,
                (values[0],),
            ).fetchone()
            if existing is None or tuple(existing) != values:
                raise PublicationConflictError(f"lifecycle transition conflicts: {values[0]}")

    def _execute_values(
        self,
        prefix: str,
        rows: tuple[tuple[object, ...], ...],
        suffix: str,
    ) -> None:
        """Execute bounded multi-row inserts with SQLite's variable limit."""

        if not rows:
            return
        width = len(rows[0])
        getlimit = cast(
            Callable[[int], int] | None,
            getattr(self._connection, "getlimit", None),
        )
        sqlite_variable_limit = (
            getlimit(9)  # SQLITE_LIMIT_VARIABLE_NUMBER
            if callable(getlimit)
            else 999
        )
        variable_limit = min(sqlite_variable_limit, 30_000)
        per_statement = max(1, variable_limit // width)
        placeholders = f"({', '.join('?' for _ in range(width))})"
        for start in range(0, len(rows), per_statement):
            batch = rows[start : start + per_statement]
            values_sql = ", ".join(placeholders for _ in batch)
            parameters = tuple(value for row in batch for value in row)
            self._connection.execute(
                f"{prefix} {values_sql}{suffix}",
                parameters,
            )

    def _write_progress(self, write_set: PublicationWriteSet, request: PublicationRequest) -> None:
        cursor_repository = SourceCursorRepository(self._connection)
        for cursor in write_set.changes.cursor_updates:
            cursor_repository.put(
                SourceCursorRecord(
                    cursor.manifestation_key,
                    cursor.source_revision,
                    cursor.byte_offset,
                    cursor.record_ordinal,
                    cursor.source_size_bytes,
                    cursor.prefix_through_cursor_sha256,
                    cursor.suffix_sha256,
                    cursor.latest_source_order,
                    cursor.parser_version,
                    cursor.adapter_version,
                    request.publication_id,
                    request.committed_at_us,
                )
            )
        diagnostic_repository = SourceDiagnosticRepository(self._connection)
        for diagnostic in write_set.changes.diagnostics:
            if diagnostic.source_range is None:
                continue
            source = diagnostic.source_range
            diagnostic_repository.add(
                SourceDiagnosticRecord(
                    source.manifestation_key,
                    source.source_revision,
                    source.byte_start,
                    source.byte_end,
                    diagnostic.code,
                    source.record_ordinal,
                    request.publication_id,
                )
            )

    def _write_tail_state(self, state: ModelCallTailState | None) -> None:
        if state is None:
            return
        self._connection.execute(
            """
            INSERT INTO model_call_tail_state (
              singleton, row_count, minimum_event_at_us, maximum_event_at_us,
              maximum_source_order, base_publication_id, last_fold_publication_id
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton) DO UPDATE SET
              row_count = excluded.row_count,
              minimum_event_at_us = excluded.minimum_event_at_us,
              maximum_event_at_us = excluded.maximum_event_at_us,
              maximum_source_order = excluded.maximum_source_order,
              base_publication_id = excluded.base_publication_id,
              last_fold_publication_id = excluded.last_fold_publication_id
            """,
            (
                state.row_count,
                state.minimum_event_at_us,
                state.maximum_event_at_us,
                state.maximum_source_order,
                state.base_publication_id,
                state.last_fold_publication_id,
            ),
        )

    def _reconcile_local(self, plan: PublicationPlan, write_set: PublicationWriteSet) -> None:
        """Validate bounded local accounting without scanning canonical facts."""

        delta = next(
            (row for row in write_set.rows if row.table == "publication_deltas"),
            None,
        )
        entity_deltas = [row for row in write_set.rows if row.table == "publication_delta_entities"]
        if delta is not None and int(delta.values["inserted_count"]) != sum(
            int(row.values["inserted_count"]) for row in entity_deltas
        ):
            raise PublicationWriteError("publication delta does not reconcile with entity deltas")
        if len(write_set.changes.occurrences) > plan.estimate.occurrences:
            raise PublicationLimitError("accepted occurrences exceed the plan")
        state = write_set.tail_state
        if state is None:
            return
        bounds = self._connection.execute(
            """
            SELECT MIN(tail_ordinal), MAX(tail_ordinal), MIN(event_at_us),
                   MAX(event_at_us), MAX(source_order)
            FROM model_call_tail
            """
        ).fetchone()
        expected_ordinals = (None, None) if state.row_count == 0 else (1, state.row_count)
        if tuple(bounds[:2]) != expected_ordinals or tuple(bounds[2:]) != (
            state.minimum_event_at_us,
            state.maximum_event_at_us,
            state.maximum_source_order,
        ):
            raise PublicationWriteError(
                "model-call tail state does not reconcile with bounded tail rows"
            )
