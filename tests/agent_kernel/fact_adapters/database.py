"""Independent database-v1 fact selection for the CK-07E test seam.

This module is deliberately self-contained.  It is a test-only read adapter:
the only non-stdlib imports are the frozen, pure agent-kernel value/domain
types.  It does not share relation selection, evidence resolution, or output
objects with the scenario adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FactCoordinates,
    PlanRequest,
)
from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    compile_current_valuation_matches,
)


class DatabaseAdapterContractError(ValueError):
    """The database snapshot or supplied seam contract is not admissible."""


def _attach_occurrence_event_coordinates(
    facts: Sequence[CanonicalFact],
) -> list[CanonicalFact]:
    """Attach occurrence time from already selected plan facts only.

    The database adapter must not scan every logical relation merely to recover
    coordinates.  A plan that admits ``source_occurrence`` can bind it only to
    another fact already selected by that same plan's relation allowlist.
    """

    entity_coordinates = {
        fact.logical_id: fact.coordinates
        for fact in facts
        if fact.relation not in {"source_occurrence", "valuation_match"}
        and fact.coordinates is not None
        and fact.coordinates.event_at_us is not None
    }
    manifestation_events: dict[str, int] = {}
    for fact in facts:
        if fact.relation != "source_occurrence":
            continue
        semantic_logical_id = fact.values.get("semantic_logical_id")
        target = (
            entity_coordinates.get(semantic_logical_id)
            if isinstance(semantic_logical_id, str)
            else None
        )
        manifestation_id = fact.values.get("source_manifestation_id")
        if (
            target is not None
            and target.event_at_us is not None
            and isinstance(manifestation_id, str)
        ):
            prior = manifestation_events.get(manifestation_id)
            manifestation_events[manifestation_id] = (
                target.event_at_us if prior is None else min(prior, target.event_at_us)
            )
    normalized: list[CanonicalFact] = []
    for fact in facts:
        fact_coordinates = fact.coordinates
        if fact.relation == "source_occurrence" and fact_coordinates is not None:
            semantic_logical_id = fact.values.get("semantic_logical_id")
            target = (
                entity_coordinates.get(semantic_logical_id)
                if isinstance(semantic_logical_id, str)
                else None
            )
            if target is None:
                continue
            fact_coordinates = FactCoordinates(
                event_at_us=target.event_at_us,
                source_rank=fact_coordinates.source_rank,
                source_order=fact_coordinates.source_order,
                event_kind_order=fact_coordinates.event_kind_order,
                transition_rank=fact_coordinates.transition_rank,
            )
        elif (
            fact.relation == "source_manifestation"
            and fact_coordinates is not None
            and fact_coordinates.event_at_us is None
        ):
            event_at_us = manifestation_events.get(fact.logical_id)
            if event_at_us is None:
                continue
            fact_coordinates = FactCoordinates(
                event_at_us=event_at_us,
                source_rank=fact_coordinates.source_rank,
                source_order=fact_coordinates.source_order,
                event_kind_order=fact_coordinates.event_kind_order,
                transition_rank=fact_coordinates.transition_rank,
            )
        normalized.append(
            CanonicalFact(
                relation=fact.relation,
                logical_id=fact.logical_id,
                values=fact.values,
                coordinates=fact_coordinates,
            )
        )
    return normalized


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_request_digest(request: PlanRequest) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise DatabaseAdapterContractError("request contains a non-finite decimal")
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): normalize(item) for key, item in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            raise DatabaseAdapterContractError("request contains a non-finite number")
        return value

    payload = json.dumps(
        normalize(
            {
                "gates": request.gates,
                "parameters": request.parameters,
                "plan_id": request.plan_id,
            }
        ),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    """The typed request and exact ordered evidence-selection mapping."""

    plan_request: PlanRequest
    required_role_kinds: tuple[tuple[str, str], ...]
    selector_ids: Mapping[str, str] = field(default_factory=dict)
    publication_id: str = ""
    request_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan_request, PlanRequest):
            raise DatabaseAdapterContractError("plan_request must be a PlanRequest")
        if not self.required_role_kinds:
            raise DatabaseAdapterContractError("required evidence roles must not be empty")
        roles: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for item in self.required_role_kinds:
            if (
                not isinstance(item, (tuple, list))
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or not isinstance(item[1], str)
                or not item[1]
            ):
                raise DatabaseAdapterContractError("evidence role/kind entries are malformed")
            if item[0] in roles:
                raise DatabaseAdapterContractError("evidence roles must be unique")
            roles.add(item[0])
            normalized.append((item[0], item[1]))
        object.__setattr__(self, "required_role_kinds", tuple(normalized))
        if not isinstance(self.selector_ids, Mapping):
            raise DatabaseAdapterContractError("selector_ids must be a mapping")
        if any(
            not isinstance(key, str) or not isinstance(value, str) or not value
            for key, value in self.selector_ids.items()
        ):
            raise DatabaseAdapterContractError("selector IDs must be nonempty strings")
        object.__setattr__(self, "selector_ids", MappingProxyType(dict(self.selector_ids)))
        digest = self.request_digest or _canonical_request_digest(self.plan_request)
        if not isinstance(digest, str) or not digest:
            raise DatabaseAdapterContractError("request digest must be a nonempty string")
        object.__setattr__(self, "request_digest", digest)


@dataclass(frozen=True, slots=True)
class EvidenceReferenceV1:
    """One owner-dispatched selector with typed provenance."""

    role: str
    selector_kind: str
    selector: str
    logical_id: str
    provenance_kind: str
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.role,
                self.selector_kind,
                self.selector,
                self.logical_id,
                self.provenance_kind,
            )
        ):
            raise DatabaseAdapterContractError("evidence reference identity is malformed")
        if not isinstance(self.provenance, Mapping):
            raise DatabaseAdapterContractError("evidence provenance must be a mapping")
        object.__setattr__(self, "provenance", _freeze(dict(self.provenance)))


@dataclass(frozen=True, slots=True)
class DatabaseV1FactMaterialization:
    """Frozen normalized facts, request, evidence, and read-snapshot token."""

    request: PlanRequest
    facts: tuple[CanonicalFact, ...]
    evidence_references: tuple[EvidenceReferenceV1, ...]
    snapshot_token: str
    source: str = "database_v1"

    def __post_init__(self) -> None:
        if not isinstance(self.request, PlanRequest):
            raise DatabaseAdapterContractError("materialization request is malformed")
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "evidence_references", tuple(self.evidence_references))
        if not self.snapshot_token:
            raise DatabaseAdapterContractError("materialization has no snapshot token")

    @property
    def evidence(self) -> tuple[EvidenceReferenceV1, ...]:
        return self.evidence_references


# Compatibility names are local aliases, not imports from another adapter.
EvidenceReference = EvidenceReferenceV1
AdapterMaterialization = DatabaseV1FactMaterialization


_RELATION_QUERIES: Mapping[str, str] = MappingProxyType(
    {
        "canonical_call": """
            SELECT mc.call_id, mc.session_id, mc.turn_id, mc.model_profile_id,
                   s.project_id, NULL AS tool_id, mc.lifecycle_state AS lifecycle,
                   mc.context_window_tokens, mc.uncached_input_tokens,
                   mc.cached_input_tokens, mc.reasoning_tokens, mc.output_tokens,
                   mc.measurement_mask,
                   mc.event_at_us, mc.source_rank, mc.source_order,
                   mc.event_kind_order, mc.transition_rank
              FROM model_calls_visible AS mc
              JOIN sessions AS s ON s.session_id = mc.session_id
             ORDER BY mc.call_id
        """,
        "project": """
            SELECT p.project_id, NULL AS parent_project_id,
                   NULL AS event_at_us, COALESCE(sm.source_rank, 0) AS source_rank,
                   COALESCE(o.record_ordinal, 0) AS source_order,
                   CASE WHEN o.occurrence_id IS NULL THEN 0 ELSE 10 END AS event_kind_order,
                   0 AS transition_rank
              FROM projects AS p
              LEFT JOIN source_occurrences AS o
                ON o.occurrence_id = (
                    SELECT so.occurrence_id
                      FROM source_occurrences AS so
                     WHERE so.semantic_logical_id = p.project_id
                     ORDER BY so.record_ordinal, so.occurrence_id
                     LIMIT 1
                )
              LEFT JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY project_id
        """,
        "session": """
            SELECT session_id, project_id, root_session_id, parent_session_id,
                   delegation_depth, lifecycle_state, start_at_us, end_at_us,
                   completion_basis, start_at_us AS event_at_us,
                   COALESCE(sm.source_rank, 0) AS source_rank,
                   COALESCE(o.record_ordinal, 0) AS source_order,
                   CASE WHEN o.occurrence_id IS NULL THEN 0 ELSE 10 END AS event_kind_order,
                   0 AS transition_rank
              FROM sessions AS s
              LEFT JOIN source_occurrences AS o
                ON o.occurrence_id = s.primary_occurrence_id
              LEFT JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY session_id
        """,
        "turn": """
            SELECT t.turn_id, t.session_id, t.ordinal,
                   t.lifecycle_state AS lifecycle, t.lifecycle_state,
                   t.start_at_us, t.end_at_us, t.completion_basis,
                   json_object(
                       'event_at_us', t.start_at_us,
                       'source_rank', sm.source_rank,
                       'source_order', o.record_ordinal
                   ) AS first_boundary_coordinates,
                   t.start_at_us AS event_at_us,
                   COALESCE(sm.source_rank, 0) AS source_rank,
                   COALESCE(o.record_ordinal, 0) AS source_order,
                   CASE WHEN o.occurrence_id IS NULL THEN 0 ELSE 10 END AS event_kind_order,
                   0 AS transition_rank
              FROM turns AS t
              LEFT JOIN source_occurrences AS o
                ON o.occurrence_id = t.primary_occurrence_id
              LEFT JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY t.turn_id
        """,
        "model_profile": """
            SELECT p.model_profile_id, p.model,
                   reasoning_effort AS effort, service_tier AS tier,
                   NULL AS event_at_us, COALESCE(sm.source_rank, 0) AS source_rank,
                   COALESCE(o.record_ordinal, 0) AS source_order,
                   CASE WHEN o.occurrence_id IS NULL THEN 0 ELSE 10 END AS event_kind_order,
                   0 AS transition_rank
              FROM model_profiles AS p
              LEFT JOIN source_occurrences AS o
                ON o.occurrence_id = (
                    SELECT so.occurrence_id
                      FROM source_occurrences AS so
                     WHERE so.semantic_logical_id = p.model_profile_id
                     ORDER BY so.record_ordinal, so.occurrence_id
                     LIMIT 1
                )
              LEFT JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY model_profile_id
        """,
        "tool_invocation": """
            SELECT t.tool_id, t.session_id, t.turn_id, t.transport_name,
                   t.semantic_operation, t.tool_family,
                   t.primary_resource_id AS resource_id,
                   (
                       SELECT json_group_array(resource_id)
                         FROM (
                             SELECT resource_id, MIN(primary_order) AS primary_order
                               FROM (
                                   SELECT t.primary_resource_id AS resource_id,
                                          0 AS primary_order
                                    WHERE t.primary_resource_id IS NOT NULL
                                   UNION ALL
                                   SELECT tr.resource_id, 1 AS primary_order
                                     FROM tool_resources AS tr
                                    WHERE tr.tool_id = t.tool_id
                               )
                              WHERE resource_id IS NOT NULL
                              GROUP BY resource_id
                              ORDER BY primary_order, resource_id
                         )
                   ) AS resource_links,
                   r.resource_kind, t.write_intent,
                   t.lifecycle_state AS lifecycle,
                   t.observed_duration_us AS duration_us, t.output_bytes,
                   t.error_category, t.start_at_us AS event_at_us,
                   t.start_source_rank AS source_rank,
                   t.start_source_order AS source_order,
                   t.start_event_kind_order AS event_kind_order,
                   t.start_transition_rank AS transition_rank,
                   t.start_at_us, t.start_source_rank,
                   t.start_source_order, t.start_event_kind_order,
                   t.start_transition_rank, t.terminal_at_us,
                   t.terminal_source_rank, t.terminal_source_order,
                   t.terminal_event_kind_order, t.terminal_transition_rank
              FROM tool_invocations AS t
              LEFT JOIN resources AS r ON r.resource_id = t.primary_resource_id
             ORDER BY t.tool_id
        """,
        "resource": """
            SELECT r.resource_id, r.resource_kind,
                   NULL AS event_at_us, COALESCE(sm.source_rank, 0) AS source_rank,
                   COALESCE(o.record_ordinal, 0) AS source_order,
                   CASE WHEN o.occurrence_id IS NULL THEN 0 ELSE 10 END AS event_kind_order,
                   0 AS transition_rank
              FROM resources AS r
              LEFT JOIN source_occurrences AS o
                ON o.occurrence_id = (
                    SELECT so.occurrence_id
                      FROM source_occurrences AS so
                     WHERE so.semantic_logical_id = r.resource_id
                     ORDER BY so.record_ordinal, so.occurrence_id
                     LIMIT 1
                )
              LEFT JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY resource_id
        """,
        "state_change": """
            SELECT change_id AS state_change_id, session_id, turn_id,
                   resource_id, change_kind AS mutation_kind,
                   event_at_us, source_rank, source_order,
                   event_kind_order, transition_rank
              FROM state_changes
             ORDER BY change_id
        """,
        "compaction_boundary": """
            SELECT compaction_id, session_id,
                   event_at_us, source_rank, source_order,
                   event_kind_order, transition_rank
              FROM compaction_boundaries
             ORDER BY compaction_id
        """,
        "context_component": """
            SELECT component_id, session_id, turn_id, call_id, category,
                   observed_utf8_bytes, observed_event_count, estimated_tokens,
                   total_context_utf8_bytes, event_at_us, source_rank,
                   source_order, event_kind_order, transition_rank
              FROM context_components
             ORDER BY component_id
        """,
        "allowance_observation": """
            SELECT o.observation_id, o.limit_id, l.provider,
                   o.plan_identity AS plan, o.window_kind, o.reset_identity,
                   o.observed_at_us, o.used_percent, o.remaining_percent,
                   'same_cycle_adjacent' AS compatibility_basis,
                   c.completion_status, o.source_rank, o.source_order,
                   o.event_kind_order, o.transition_rank
              FROM allowance_observations AS o
              JOIN allowance_limits AS l ON l.limit_id = o.limit_id
              JOIN allowance_cycles AS c ON c.cycle_id = o.cycle_id
             ORDER BY o.observation_id
        """,
        "publication": """
            SELECT p.publication_id,
                   (
                       SELECT json_group_object(
                           c.capability_id,
                           json(CASE WHEN c.observed_entity_count > 0
                                     THEN 'true' ELSE 'false' END)
                       )
                         FROM publication_capability_coverage AS c
                        WHERE c.publication_id = p.publication_id
                   ) AS capabilities,
                   (
                       SELECT json_group_object(e.entity_kind, e.entity_count)
                         FROM publication_entity_counts AS e
                        WHERE e.publication_id = p.publication_id
                   ) AS measurements,
                   p.indexed_from_us,
                   p.guaranteed_complete_from_us,
                   json_object(
                       'basis', (
                           SELECT c.grade
                             FROM publication_capability_coverage AS c
                            WHERE c.publication_id = p.publication_id
                              AND c.capability_id = 'valuation'
                       ),
                       'priced_calls', (
                           SELECT c.eligible_entity_count - c.unavailable_entity_count
                             FROM publication_capability_coverage AS c
                            WHERE c.publication_id = p.publication_id
                              AND c.capability_id = 'valuation'
                       )
                   ) AS valuation_coverage,
                   p.observed_through_us,
                   p.indexed_through_us AS _indexed_through_us,
                   p.operation_id, p.artifact_manifest_sha256,
                   p.committed_at_us, p.committed_at_us AS event_at_us,
                   0 AS source_rank, 0 AS source_order,
                   0 AS event_kind_order, 0 AS transition_rank
              FROM publication_head AS h
              JOIN publications AS p ON p.publication_id = h.publication_id
             WHERE h.singleton = 1 AND p.status = 'committed'
             ORDER BY p.committed_at_us DESC
             LIMIT 1
        """,
        "publication_delta": """
            SELECT d.inserted_count, d.removed_count, d.corrected_count,
                   d.recanonicalized_count, d.terminalized_count,
                   COALESCE(d.uncached_input_token_delta, 0)
                   + COALESCE(d.cached_input_token_delta, 0)
                   + COALESCE(d.reasoning_token_delta, 0)
                   + COALESCE(d.output_token_delta, 0) AS token_delta,
                   'publication-delta:' || substr(
                       d.publication_id, length('publication:') + 1
                   ) AS publication_id,
                   NULL AS event_at_us,
                   0 AS source_rank, 0 AS source_order,
                   0 AS event_kind_order, 0 AS transition_rank
              FROM publication_head AS h
              JOIN publication_deltas AS d ON d.publication_id = h.publication_id
             WHERE h.singleton = 1
             ORDER BY d.publication_id DESC
             LIMIT 1
        """,
        "source_manifestation": """
            SELECT manifestation_id AS source_manifestation_id,
                   state AS lifecycle_state,
                   'source_inventory' AS canonical_basis,
                   NULL AS event_at_us, source_rank AS source_rank,
                   source_rank AS source_order, 10 AS event_kind_order,
                   0 AS transition_rank
              FROM source_manifestations
             ORDER BY manifestation_id
        """,
        "source_occurrence": """
            SELECT o.occurrence_id, o.semantic_logical_id,
                   sm.manifestation_id AS source_manifestation_id,
                   o.source_revision, o.record_ordinal, o.byte_start,
                   o.byte_end, o.adapter_version,
                   NULL AS event_at_us,
                   json_object(
                       'adapter_version', o.adapter_version,
                       'byte_end', o.byte_end,
                       'byte_start', o.byte_start,
                       'record_ordinal', o.record_ordinal,
                       'source_revision', o.source_revision
                   ) AS occurrence_coordinates,
                   sm.source_rank AS source_rank, o.record_ordinal AS source_order,
                   10 AS event_kind_order, 0 AS transition_rank
              FROM source_occurrences AS o
              JOIN source_manifestations AS sm
                ON sm.manifestation_key = o.manifestation_key
             ORDER BY o.occurrence_id
        """,
    }
)

_RELATION_ID_FIELDS: Mapping[str, str] = MappingProxyType(
    {
        "canonical_call": "call_id",
        "project": "project_id",
        "session": "session_id",
        "turn": "turn_id",
        "model_profile": "model_profile_id",
        "tool_invocation": "tool_id",
        "resource": "resource_id",
        "state_change": "state_change_id",
        "compaction_boundary": "compaction_id",
        "context_component": "component_id",
        "allowance_observation": "observation_id",
        "publication": "publication_id",
        "publication_delta": "publication_id",
        "source_manifestation": "source_manifestation_id",
        "source_occurrence": "occurrence_id",
    }
)

_RELATION_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "canonical_call": frozenset(
            {
                "call_id",
                "session_id",
                "turn_id",
                "model_profile_id",
                "project_id",
                "tool_id",
                "context_window_tokens",
                "uncached_input_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "output_tokens",
                "measurement_mask",
                "lifecycle",
            }
        ),
        "project": frozenset({"project_id", "parent_project_id"}),
        "session": frozenset(
            {
                "session_id",
                "project_id",
                "root_session_id",
                "parent_session_id",
                "delegation_depth",
                "start_at_us",
                "end_at_us",
                "lifecycle_state",
                "completion_basis",
            }
        ),
        "turn": frozenset(
            {
                "turn_id",
                "session_id",
                "ordinal",
                "lifecycle",
                "lifecycle_state",
                "start_at_us",
                "end_at_us",
                "completion_basis",
                "first_boundary_coordinates",
            }
        ),
        "model_profile": frozenset({"model_profile_id", "model", "effort", "tier"}),
        "tool_invocation": frozenset(
            {
                "tool_id",
                "session_id",
                "turn_id",
                "transport_name",
                "semantic_operation",
                "tool_family",
                "resource_links",
                "resource_id",
                "resource_kind",
                "write_intent",
                "lifecycle",
                "start_at_us",
                "start_source_rank",
                "start_source_order",
                "start_event_kind_order",
                "start_transition_rank",
                "terminal_at_us",
                "terminal_source_rank",
                "terminal_source_order",
                "terminal_event_kind_order",
                "terminal_transition_rank",
                "output_bytes",
                "duration_us",
                "error_category",
            }
        ),
        "resource": frozenset({"resource_id", "resource_kind"}),
        "state_change": frozenset(
            {"state_change_id", "session_id", "turn_id", "resource_id", "mutation_kind"}
        ),
        "compaction_boundary": frozenset({"compaction_id", "session_id"}),
        "context_component": frozenset(
            {
                "component_id",
                "session_id",
                "turn_id",
                "call_id",
                "category",
                "observed_utf8_bytes",
                "observed_event_count",
                "estimated_tokens",
                "total_context_utf8_bytes",
            }
        ),
        "allowance_observation": frozenset(
            {
                "observation_id",
                "provider",
                "limit_id",
                "plan",
                "window_kind",
                "reset_identity",
                "observed_at_us",
                "allowance_percent",
                "completion_status",
                "compatibility_basis",
            }
        ),
        "publication": frozenset(
            {
                "publication_id",
                "capabilities",
                "measurements",
                "indexed_from_us",
                "guaranteed_complete_from_us",
                "valuation_coverage",
                "observed_through_us",
            }
        ),
        "publication_delta": frozenset(
            {
                "inserted_count",
                "removed_count",
                "corrected_count",
                "recanonicalized_count",
                "terminalized_count",
                "token_delta",
            }
        ),
        "source_manifestation": frozenset(
            {"source_manifestation_id", "lifecycle_state", "canonical_basis"}
        ),
        "source_occurrence": frozenset(
            {
                "occurrence_id",
                "semantic_logical_id",
                "source_manifestation_id",
                "occurrence_coordinates",
            }
        ),
        "valuation_match": frozenset(
            {
                "call_id",
                "rate_card_digest",
                "match_basis",
                "configured_cost_usd",
                "estimated_credits",
                "coverage_basis",
                "cost_grade",
                "cost_unpriced_reason",
                "unpriced_reason",
            }
        ),
    }
)

_SELECTOR_KINDS = frozenset(
    {
        "allowance_interval",
        "allowance_observation",
        "call",
        "model_profile",
        "project",
        "publication",
        "rate_card",
        "resource",
        "session",
        "source_manifestation",
        "state_change",
        "tool",
        "turn",
        "window",
    }
)

_SOURCE_OWNER_ENTITY_QUERIES: Mapping[str, str] = MappingProxyType(
    {
        "allowance_observation": "SELECT 1 FROM allowance_observations WHERE observation_id = ? LIMIT 1",
        "call": "SELECT 1 FROM model_calls_visible WHERE call_id = ? LIMIT 1",
        "model_profile": "SELECT 1 FROM model_profiles WHERE model_profile_id = ? LIMIT 1",
        "project": "SELECT 1 FROM projects WHERE project_id = ? LIMIT 1",
        "resource": "SELECT 1 FROM resources WHERE resource_id = ? LIMIT 1",
        "session": "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1",
        "state_change": "SELECT 1 FROM state_changes WHERE change_id = ? LIMIT 1",
        "tool": "SELECT 1 FROM tool_invocations WHERE tool_id = ? LIMIT 1",
        "turn": "SELECT 1 FROM turns WHERE turn_id = ? LIMIT 1",
    }
)

_SOURCE_OCCURRENCES_SQL = """
    SELECT o.occurrence_id, o.semantic_logical_id, sm.manifestation_id,
           o.source_revision, o.record_ordinal, o.byte_start, o.byte_end,
           o.adapter_version
      FROM source_occurrences AS o
     JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key
     WHERE o.semantic_logical_id = ?
     ORDER BY o.record_ordinal, o.occurrence_id
"""


def _row_dict(row: Any, description: Sequence[Any] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}  # noqa: SIM118
    if isinstance(row, Mapping):
        return dict(row)
    if description is None:
        raise DatabaseAdapterContractError("database row has no column description")
    return {column[0]: value for column, value in zip(description, row, strict=True)}


def _typed_value(field: str, value: Any) -> Any:
    boolean_fields = {"write_intent"}
    json_fields = {
        "capabilities",
        "measurements",
        "valuation_coverage",
        "occurrence_coordinates",
        "first_boundary_coordinates",
        "resource_links",
    }
    decimal_fields = {"allowance_percent", "used_percent", "remaining_percent"}
    if field in boolean_fields and value is not None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise DatabaseAdapterContractError(f"database field {field} must be a SQLite boolean")
    if field in json_fields and isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError) as error:
            raise DatabaseAdapterContractError(
                f"malformed JSON in database field {field}"
            ) from error
    if field in decimal_fields and value is not None:
        if field == "allowance_percent" and isinstance(value, Decimal):
            if not value.is_finite():
                raise DatabaseAdapterContractError("database field allowance_percent is not finite")
            return value
        if not isinstance(value, str):
            raise DatabaseAdapterContractError(
                f"database field {field} must be a canonical decimal string"
            )
        try:
            decimal = Decimal(value)
        except (InvalidOperation, ValueError) as error:
            raise DatabaseAdapterContractError(
                f"malformed decimal in database field {field}"
            ) from error
        if not decimal.is_finite():
            raise DatabaseAdapterContractError(f"non-finite decimal in database field {field}")
        canonical = "0" if decimal == 0 else format(decimal.normalize(), "f")
        if "." in canonical:
            canonical = canonical.rstrip("0").rstrip(".")
        if value != canonical:
            raise DatabaseAdapterContractError(
                f"database field {field} is not a canonical decimal string"
            )
        return decimal
    return value


def _allowance_remaining_percent(values: Mapping[str, Any]) -> Decimal | None:
    used = _typed_value("used_percent", values.get("used_percent"))
    remaining = _typed_value("remaining_percent", values.get("remaining_percent"))
    lower = Decimal("0")
    upper = Decimal("100")
    for name, value in (("used_percent", used), ("remaining_percent", remaining)):
        if value is not None and (value < lower or value > upper):
            raise DatabaseAdapterContractError(f"{name} is outside the canonical percentage range")
    if used is None and remaining is None:
        return None
    if used is not None and remaining is not None and used + remaining != upper:
        raise DatabaseAdapterContractError("allowance used_percent and remaining_percent disagree")
    if remaining is not None:
        return remaining
    assert used is not None
    return upper - used


def _coordinates(values: Mapping[str, Any]) -> FactCoordinates:
    event_at = values.get("event_at_us")
    if event_at is None:
        event_at = values.get("observed_at_us")
    return FactCoordinates(
        event_at_us=event_at,
        source_rank=int(values.get("source_rank", 0) or 0),
        source_order=int(values.get("source_order", 0) or 0),
        event_kind_order=int(values.get("event_kind_order", 0) or 0),
        transition_rank=int(values.get("transition_rank", 0) or 0),
    )


def _selector_prefix(kind: str) -> str:
    return kind.replace("_", "-")


class DatabaseV1FactAdapter:
    """Select only permitted logical facts from one query-only snapshot."""

    source_name = "database_v1"

    def __init__(
        self,
        contract: Mapping[str, Any] | None = None,
        selector_contract: Mapping[str, Any] | None = None,
        evidence_selection: Any = None,
    ) -> None:
        self._contract = contract
        self._selector_contract = selector_contract
        self._evidence_selection = evidence_selection

    def materialize(
        self,
        connection: sqlite3.Connection,
        request: PlanRequest | AdapterRequest | Any,
        required_role_kinds: Any = None,
        selector_ids: Mapping[str, str] | None = None,
    ) -> DatabaseV1FactMaterialization:
        self._assert_query_only(connection)
        plan_request, required, selected_ids, request_digest, publication_id = self._request_parts(
            request, required_role_kinds, selector_ids
        )
        plan = self._plan(plan_request.plan_id)
        permitted = self._permitted_sources(plan)
        owner_rules = self._owner_rules()

        connection.execute("BEGIN")
        try:
            facts: list[CanonicalFact] = []
            for relation in permitted:
                if relation == "valuation_match":
                    facts.extend(self._valuation_facts(connection, permitted[relation]))
                    continue
                cursor = connection.execute(_RELATION_QUERIES[relation])
                description = cursor.description
                for row in cursor:
                    raw = _row_dict(row, description)
                    if relation == "allowance_observation":
                        raw["allowance_percent"] = _allowance_remaining_percent(raw)
                    elif relation == "publication":
                        self._validate_publication_authority(connection, raw)
                    logical_id_field = _RELATION_ID_FIELDS[relation]
                    logical_id = raw.get(logical_id_field)
                    if not isinstance(logical_id, str) or not logical_id:
                        raise DatabaseAdapterContractError(
                            f"{relation} row has no logical identity"
                        )
                    values = {
                        key: _typed_value(key, value)
                        for key, value in raw.items()
                        if key in permitted[relation]
                    }
                    facts.append(
                        CanonicalFact(
                            relation,
                            logical_id,
                            values,
                            _coordinates(raw),
                        )
                    )
            if not facts:
                raise DatabaseAdapterContractError(
                    f"database snapshot produced no facts for {plan_request.plan_id}"
                )
            facts = _attach_occurrence_event_coordinates(facts)
            evidence = self._evidence(
                connection,
                plan_request,
                required,
                selected_ids,
                request_digest,
                owner_rules,
            )
            self._validate_evidence(required, evidence, owner_rules)
            snapshot_token = self._snapshot_token(connection, publication_id)
        except DatabaseAdapterContractError:
            raise
        except (sqlite3.DatabaseError, TypeError, ValueError) as error:
            raise DatabaseAdapterContractError("database snapshot is malformed") from error
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")

        ordered = sorted(
            facts,
            key=lambda fact: (
                fact.coordinates.key(fact.logical_id)  # type: ignore[union-attr]
                if fact.coordinates is not None
                else (True, 0, 0, 0, 0, fact.logical_id, 0)
            ),
        )
        keys = [fact.coordinates.key(fact.logical_id) for fact in ordered if fact.coordinates]
        if len(keys) != len(set(keys)):
            raise DatabaseAdapterContractError("fact coordinates do not form a total order")
        return DatabaseV1FactMaterialization(
            request=plan_request,
            facts=tuple(ordered),
            evidence_references=tuple(evidence),
            snapshot_token=snapshot_token,
        )

    @staticmethod
    def _assert_query_only(connection: sqlite3.Connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise DatabaseAdapterContractError("connection must be sqlite3.Connection")
        try:
            query_only = connection.execute("PRAGMA query_only").fetchone()[0]
        except sqlite3.DatabaseError as error:
            raise DatabaseAdapterContractError(
                "connection is not a SQLite query surface"
            ) from error
        if int(query_only) != 1:
            raise DatabaseAdapterContractError("database-v1 adapter requires PRAGMA query_only=1")
        if connection.in_transaction:
            raise DatabaseAdapterContractError("adapter owns the read transaction")

    def _request_parts(
        self,
        request: PlanRequest | AdapterRequest | Any,
        required_role_kinds: Any,
        selector_ids: Mapping[str, str] | None,
    ) -> tuple[PlanRequest, tuple[Mapping[str, Any], ...], Mapping[str, str], str, str]:
        wrapper = request if isinstance(request, AdapterRequest) else None
        plan_request = wrapper.plan_request if wrapper is not None else request
        if not isinstance(plan_request, PlanRequest):
            raise DatabaseAdapterContractError("request must contain a PlanRequest")
        supplied_required = (
            required_role_kinds
            if required_role_kinds is not None
            else getattr(wrapper, "required_role_kinds", None)
        )
        if supplied_required is None:
            supplied_required = self._evidence_selection
        required = self._normalize_required(supplied_required)
        selected = (
            selector_ids if selector_ids is not None else getattr(wrapper, "selector_ids", {})
        )
        if not isinstance(selected, Mapping):
            raise DatabaseAdapterContractError("selector IDs must be a mapping")
        selected_values: dict[str, str] = dict(selected)
        for entry in required:
            role = entry["role"]
            kind = entry["selector_kind"]
            explicit_selector = entry.get("selector")
            explicit_logical_id = entry.get("logical_id")
            if kind == "window":
                if isinstance(explicit_logical_id, str) and explicit_logical_id:
                    selected_values.setdefault(role, explicit_logical_id)
                elif isinstance(explicit_selector, str):
                    _prefix, suffix = self._selector_parts(explicit_selector, kind)
                    selected_values.setdefault(role, suffix)
                continue
            if isinstance(explicit_logical_id, str) and explicit_logical_id:
                selected_values.setdefault(role, explicit_logical_id)
            elif isinstance(explicit_selector, str):
                _prefix, suffix = self._selector_parts(explicit_selector, kind)
                selected_values.setdefault(role, suffix)
            elif role not in selected_values and kind in selected_values:
                selected_values[role] = selected_values[kind]
        digest = _canonical_request_digest(plan_request)
        supplied_digest = getattr(wrapper, "request_digest", None)
        if supplied_digest is not None and supplied_digest != digest:
            raise DatabaseAdapterContractError("request digest does not match the typed request")
        publication_id = getattr(wrapper, "publication_id", "") or ""
        return plan_request, required, MappingProxyType(selected_values), digest, publication_id

    @staticmethod
    def _normalize_required(value: Any) -> tuple[Mapping[str, Any], ...]:
        if isinstance(value, Mapping):
            for key in ("selections", "required", "evidence"):
                if key in value:
                    return DatabaseV1FactAdapter._normalize_required(value[key])
            if "required_role_kinds" in value:
                role_kinds = value["required_role_kinds"]
                selector_values = value.get("selector_ids", {})
                if not isinstance(selector_values, Mapping):
                    raise DatabaseAdapterContractError("selector_ids are malformed")
                entries = []
                for pair in role_kinds:
                    if (
                        not isinstance(pair, Sequence)
                        or isinstance(pair, (str, bytes))
                        or len(pair) != 2
                    ):
                        raise DatabaseAdapterContractError("required role/kind entry is malformed")
                    role, kind = pair
                    entry: dict[str, Any] = {"role": role, "selector_kind": kind}
                    if kind != "window":
                        selected = selector_values.get(role, selector_values.get(kind))
                        if not isinstance(selected, str):
                            raise DatabaseAdapterContractError(
                                f"{role} has no exact selector mapping"
                            )
                        entry["selector"] = selected
                    elif role in selector_values:
                        selected = selector_values[role]
                        if not isinstance(selected, str) or not selected:
                            raise DatabaseAdapterContractError(
                                f"{role} has a malformed exact window identity"
                            )
                        entry["logical_id"] = selected
                    entries.append(entry)
                value = entries
            else:
                entries = []
                for role, selected in value.items():
                    if isinstance(selected, Mapping):
                        entry = dict(selected)
                        entry.setdefault("role", role)
                    elif isinstance(selected, str):
                        entry = {"role": role, "selector": selected}
                    else:
                        raise DatabaseAdapterContractError("evidence selection is malformed")
                    entries.append(entry)
                value = entries
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise DatabaseAdapterContractError("exact required evidence mapping is missing")
        if value and all(
            isinstance(item, Sequence)
            and not isinstance(item, (str, bytes))
            and len(item) == 2
            and all(isinstance(part, str) and part for part in item)
            for item in value
        ):
            value = tuple(
                {"role": item[0], "selector_kind": item[1]}  # type: ignore[index]
                for item in value
            )
        result: list[Mapping[str, Any]] = []
        roles: set[str] = set()
        for item in value:
            if isinstance(item, Mapping):
                entry = dict(item)
                role, kind = entry.get("role"), entry.get("selector_kind", entry.get("kind"))
            else:
                raise DatabaseAdapterContractError("required evidence mapping is malformed")
            if (
                not isinstance(role, str)
                or not role
                or role in roles
                or not isinstance(kind, str)
                or not kind
            ):
                raise DatabaseAdapterContractError("required evidence mapping has empty identity")
            entry["role"] = role
            entry["selector_kind"] = kind
            selector = entry.get("selector")
            if selector is not None and (not isinstance(selector, str) or not selector):
                raise DatabaseAdapterContractError("evidence selector is malformed")
            result.append(entry)
            roles.add(role)
        if not result:
            raise DatabaseAdapterContractError("required evidence mapping must not be empty")
        return tuple(result)

    @staticmethod
    def _selector_parts(selector: str, kind: str) -> tuple[str, str]:
        prefix, separator, suffix = selector.partition(":")
        if not separator or prefix != _selector_prefix(kind) or not suffix:
            raise DatabaseAdapterContractError(
                f"selector prefix does not match {kind}: {selector!r}"
            )
        return prefix, suffix

    def _plan(self, plan_id: str) -> Mapping[str, Any]:
        if not isinstance(self._contract, Mapping):
            raise DatabaseAdapterContractError("plan-operand contract data is missing")
        matches = [
            item for item in self._contract.get("plans", ()) if item.get("plan_id") == plan_id
        ]
        if len(matches) != 1:
            raise DatabaseAdapterContractError(f"plan must resolve exactly once: {plan_id}")
        return matches[0]

    @staticmethod
    def _permitted_sources(plan: Mapping[str, Any]) -> dict[str, frozenset[str]]:
        sources = plan.get("permitted_sources")
        if isinstance(sources, (str, bytes)) or not isinstance(sources, Sequence):
            raise DatabaseAdapterContractError("plan permitted_sources is malformed")
        permitted: dict[str, frozenset[str]] = {}
        for source in sources:
            if not isinstance(source, Mapping):
                raise DatabaseAdapterContractError("plan source declaration is malformed")
            relation = source.get("relation")
            fields = source.get("fields")
            if (
                relation in permitted
                or not isinstance(relation, str)
                or relation not in _RELATION_QUERIES
                and relation != "valuation_match"
            ):
                raise DatabaseAdapterContractError(
                    f"relation is not in the database-v1 allowlist: {relation!r}"
                )
            if isinstance(fields, (str, bytes)) or not isinstance(fields, Sequence):
                raise DatabaseAdapterContractError(f"fields are malformed for {relation}")
            selected = frozenset(fields)
            if not selected or not all(isinstance(field, str) for field in selected):
                raise DatabaseAdapterContractError(f"fields are malformed for {relation}")
            allowed = _RELATION_FIELDS.get(relation, frozenset())
            if not selected.issubset(allowed):
                raise DatabaseAdapterContractError(f"fields are not allowed for {relation}")
            permitted[relation] = selected
        if not permitted:
            raise DatabaseAdapterContractError("plan has no permitted sources")
        return permitted

    @staticmethod
    def _validate_publication_authority(
        connection: sqlite3.Connection,
        publication: Mapping[str, Any],
    ) -> None:
        """Validate the committed publication's independent coverage rows."""

        publication_id = publication.get("publication_id")
        if not isinstance(publication_id, str) or not publication_id:
            raise DatabaseAdapterContractError("publication authority has no logical identity")

        def integer(value: Any, label: str, *, nullable: bool = False) -> int | None:
            if value is None and nullable:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                raise DatabaseAdapterContractError(f"{label} is not an integer")
            return value

        def nonnegative(value: Any, label: str) -> int:
            typed = integer(value, label)
            assert typed is not None
            if typed < 0:
                raise DatabaseAdapterContractError(f"{label} is negative")
            return typed

        for bound_field in (
            "indexed_from_us",
            "guaranteed_complete_from_us",
            "observed_through_us",
            "_indexed_through_us",
        ):
            integer(
                publication.get(bound_field),
                f"publication.{bound_field}",
                nullable=True,
            )

        source_cursor = connection.execute(
            """
                SELECT source_id,
                       selected_manifestation_count, selected_manifestation_bytes,
                       deferred_manifestation_count, deferred_manifestation_bytes,
                       malformed_manifestation_count, malformed_manifestation_bytes,
                       missing_manifestation_count, missing_manifestation_bytes,
                       uncertain_manifestation_count, uncertain_manifestation_bytes,
                       malformed_range_count, malformed_range_bytes,
                       selected_complete_record_count,
                       tail_pending,
                       indexed_from_us, indexed_through_us,
                       guaranteed_complete_from_us, guaranteed_complete_through_us,
                       clock_quality, clock_uncertainty_us,
                       inventory_started_at_us, inventory_completed_at_us
                  FROM publication_source_coverage
                 WHERE publication_id = ?
                 ORDER BY source_id
            """,
            (publication_id,),
        )
        source_rows = [_row_dict(row, source_cursor.description) for row in source_cursor]
        if not source_rows:
            raise DatabaseAdapterContractError(
                "publication source coverage is missing for the current publication"
            )
        source_ids: set[str] = set()
        source_count_fields = (
            "selected_manifestation_count",
            "selected_manifestation_bytes",
            "deferred_manifestation_count",
            "deferred_manifestation_bytes",
            "malformed_manifestation_count",
            "malformed_manifestation_bytes",
            "missing_manifestation_count",
            "missing_manifestation_bytes",
            "uncertain_manifestation_count",
            "uncertain_manifestation_bytes",
            "malformed_range_count",
            "malformed_range_bytes",
            "selected_complete_record_count",
        )
        for row in source_rows:
            source_id = row.get("source_id")
            if not isinstance(source_id, str) or not source_id or source_id in source_ids:
                raise DatabaseAdapterContractError("publication source coverage is malformed")
            source_ids.add(source_id)
            for count_field in source_count_fields:
                nonnegative(row.get(count_field), f"source coverage {count_field}")
            tail_pending = integer(row.get("tail_pending"), "source coverage tail pending")
            if tail_pending not in {0, 1}:
                raise DatabaseAdapterContractError("source coverage tail pending is malformed")
            for bound_field in (
                "indexed_from_us",
                "indexed_through_us",
                "guaranteed_complete_from_us",
                "guaranteed_complete_through_us",
            ):
                integer(
                    row.get(bound_field),
                    f"source coverage {bound_field}",
                    nullable=True,
                )
            indexed_from = row.get("indexed_from_us")
            indexed_through = row.get("indexed_through_us")
            guaranteed_from = row.get("guaranteed_complete_from_us")
            guaranteed_through = row.get("guaranteed_complete_through_us")
            if (indexed_from is None) != (indexed_through is None):
                raise DatabaseAdapterContractError("source coverage indexed bounds are malformed")
            if indexed_from is not None and indexed_from > indexed_through:
                raise DatabaseAdapterContractError("source coverage indexed bounds are reversed")
            if (guaranteed_from is None) != (guaranteed_through is None):
                raise DatabaseAdapterContractError(
                    "source coverage completeness bounds are malformed"
                )
            if guaranteed_from is not None and guaranteed_from > guaranteed_through:
                raise DatabaseAdapterContractError(
                    "source coverage completeness bounds are reversed"
                )
            if (
                indexed_from != publication.get("indexed_from_us")
                or indexed_through != publication.get("_indexed_through_us")
                or guaranteed_from != publication.get("guaranteed_complete_from_us")
                or guaranteed_through
                != (
                    publication.get("_indexed_through_us")
                    if publication.get("guaranteed_complete_from_us") is not None
                    else None
                )
            ):
                raise DatabaseAdapterContractError(
                    "publication source coverage bounds do not match the committed publication"
                )
            clock_quality = row.get("clock_quality")
            if clock_quality not in {"unknown", "unsynchronized", "bounded"}:
                raise DatabaseAdapterContractError("source coverage clock quality is malformed")
            uncertainty = integer(
                row.get("clock_uncertainty_us"),
                "source coverage clock uncertainty",
                nullable=True,
            )
            if clock_quality == "bounded" and uncertainty is None:
                raise DatabaseAdapterContractError(
                    "bounded source coverage has no clock uncertainty"
                )
            if uncertainty is not None and uncertainty < 0:
                raise DatabaseAdapterContractError("source coverage clock uncertainty is negative")
            if clock_quality != "bounded" and uncertainty is not None:
                raise DatabaseAdapterContractError(
                    "non-bounded source coverage has clock uncertainty"
                )
            started = integer(row.get("inventory_started_at_us"), "source inventory start")
            completed = integer(row.get("inventory_completed_at_us"), "source inventory end")
            assert started is not None and completed is not None
            if started > completed:
                raise DatabaseAdapterContractError("source inventory bounds are reversed")

        inventory_cursor = connection.execute(
            """
                SELECT DISTINCT source_id
                  FROM source_manifestations
                 ORDER BY source_id
            """
        )
        inventory_ids = {row[0] for row in inventory_cursor}
        if inventory_ids and inventory_ids != source_ids:
            raise DatabaseAdapterContractError(
                "publication source coverage does not match the source inventory"
            )

        capability_cursor = connection.execute(
            """
                SELECT capability_id, eligible_entity_count, observed_entity_count,
                       unavailable_entity_count, measurement_mask, grade, basis
                  FROM publication_capability_coverage
                 WHERE publication_id = ?
                 ORDER BY capability_id
            """,
            (publication_id,),
        )
        capability_rows = [
            _row_dict(row, capability_cursor.description) for row in capability_cursor
        ]
        if not capability_rows:
            raise DatabaseAdapterContractError(
                "publication capability coverage is missing for the current publication"
            )
        capabilities: dict[str, bool] = {}
        valuation_rows: list[Mapping[str, Any]] = []
        for row in capability_rows:
            capability_id = row.get("capability_id")
            if (
                not isinstance(capability_id, str)
                or not capability_id
                or capability_id in capabilities
            ):
                raise DatabaseAdapterContractError("publication capability coverage is malformed")
            eligible = nonnegative(row.get("eligible_entity_count"), "capability eligible count")
            observed = nonnegative(row.get("observed_entity_count"), "capability observed count")
            unavailable = nonnegative(
                row.get("unavailable_entity_count"), "capability unavailable count"
            )
            nonnegative(row.get("measurement_mask"), "capability measurement mask")
            if observed > eligible or unavailable > eligible or observed + unavailable > eligible:
                raise DatabaseAdapterContractError("publication capability counts are inconsistent")
            grade = row.get("grade")
            basis = row.get("basis")
            if grade not in {"exact", "deterministic", "configured_estimate"}:
                raise DatabaseAdapterContractError("publication capability grade is malformed")
            if not isinstance(basis, str) or not basis:
                raise DatabaseAdapterContractError("publication capability basis is malformed")
            capabilities[capability_id] = observed > 0
            if capability_id == "valuation":
                valuation_rows.append(row)

        if len(valuation_rows) != 1:
            raise DatabaseAdapterContractError(
                "publication valuation coverage is missing or ambiguous"
            )
        valuation = valuation_rows[0]
        if valuation.get("grade") != "configured_estimate":
            raise DatabaseAdapterContractError(
                "publication valuation coverage is not a configured estimate"
            )
        priced_calls = int(valuation["eligible_entity_count"]) - int(
            valuation["unavailable_entity_count"]
        )
        expected_valuation = {
            "basis": "configured_estimate",
            "priced_calls": priced_calls,
        }

        entity_cursor = connection.execute(
            """
                SELECT entity_kind, entity_count
                  FROM publication_entity_counts
                 WHERE publication_id = ?
                 ORDER BY entity_kind
            """,
            (publication_id,),
        )
        entity_rows = [_row_dict(row, entity_cursor.description) for row in entity_cursor]
        if not entity_rows:
            raise DatabaseAdapterContractError(
                "publication entity counts are missing for the current publication"
            )
        measurements: dict[str, int] = {}
        for row in entity_rows:
            entity_kind = row.get("entity_kind")
            if not isinstance(entity_kind, str) or not entity_kind or entity_kind in measurements:
                raise DatabaseAdapterContractError("publication entity counts are malformed")
            measurements[entity_kind] = nonnegative(
                row.get("entity_count"), "publication entity count"
            )

        capabilities_value = _typed_value("capabilities", publication.get("capabilities"))
        measurements_value = _typed_value("measurements", publication.get("measurements"))
        valuation_value = _typed_value("valuation_coverage", publication.get("valuation_coverage"))
        if capabilities_value != capabilities:
            raise DatabaseAdapterContractError(
                "publication capabilities do not match authoritative coverage"
            )
        if measurements_value != measurements:
            raise DatabaseAdapterContractError(
                "publication measurements do not match authoritative entity counts"
            )
        if valuation_value != expected_valuation:
            raise DatabaseAdapterContractError(
                "publication valuation coverage does not match authoritative coverage"
            )

    def _owner_rules(self) -> Mapping[str, Mapping[str, Any]]:
        if not isinstance(self._selector_contract, Mapping):
            raise DatabaseAdapterContractError("selector-provenance contract data is missing")
        ownership = self._selector_contract.get("ownership")
        if isinstance(ownership, (str, bytes)) or not isinstance(ownership, Sequence):
            raise DatabaseAdapterContractError("selector ownership contract is malformed")
        rules: dict[str, Mapping[str, Any]] = {}
        for item in ownership:
            if not isinstance(item, Mapping):
                continue
            kind = item.get("kind")
            if isinstance(kind, str):
                rules[kind] = item
        if set(rules) != _SELECTOR_KINDS:
            raise DatabaseAdapterContractError(
                "selector ownership contract does not cover all 14 kinds"
            )
        return rules

    def _valuation_facts(
        self,
        connection: sqlite3.Connection,
        permitted_fields: frozenset[str],
    ) -> list[CanonicalFact]:
        calls_cursor = connection.execute(
            """
                SELECT call_id, model_profile_id, uncached_input_tokens,
                       cached_input_tokens, reasoning_tokens, output_tokens,
                       event_at_us, source_rank, source_order,
                       event_kind_order, transition_rank
                  FROM model_calls_visible
                 ORDER BY call_id
            """
        )
        calls = [_row_dict(row, calls_cursor.description) for row in calls_cursor]
        profiles_cursor = connection.execute(
            """
                SELECT model_profile_id, model, reasoning_effort, service_tier
                  FROM model_profiles
                 ORDER BY model_profile_id
            """
        )
        profiles = [_row_dict(row, profiles_cursor.description) for row in profiles_cursor]
        frontier, publication_digest = self._frontier(connection)
        matches = compile_current_valuation_matches(
            calls,
            profiles,
            frontier,
            publication_rate_card_digest=publication_digest,
        )
        coordinates = {row["call_id"]: _coordinates(row) for row in calls}
        facts: list[CanonicalFact] = []
        for match in matches:
            cost_reason = getattr(match.cost_unpriced_reason, "value", match.cost_unpriced_reason)
            credit_reason = getattr(
                match.credit_unpriced_reason, "value", match.credit_unpriced_reason
            )
            values = {
                "call_id": match.call_id,
                "configured_cost_usd": (
                    Decimal(match.configured_cost_usd)
                    if match.configured_cost_usd is not None
                    else None
                ),
                "coverage_basis": {
                    "cost": match.cost_coverage,
                    "credit": match.credit_coverage,
                    "rate_card_digest": match.rate_card_digest,
                },
                "estimated_credits": (
                    Decimal(match.estimated_credits)
                    if match.estimated_credits is not None
                    else None
                ),
                "match_basis": match.match_basis,
                "rate_card_digest": match.rate_card_digest,
                "cost_grade": match.cost_grade,
                "cost_unpriced_reason": cost_reason,
                "unpriced_reason": cost_reason or credit_reason,
            }
            values = {key: value for key, value in values.items() if key in permitted_fields}
            logical_id = match.valuation_id or semantic_id(
                "valuation", [match.call_id, match.rate_card_digest]
            )
            facts.append(
                CanonicalFact(
                    "valuation_match",
                    logical_id,
                    values,
                    coordinates.get(match.call_id),
                )
            )
        return facts

    @staticmethod
    def _frontier(
        connection: sqlite3.Connection,
    ) -> tuple[RateCardFrontier | None, str | None]:
        head = connection.execute(
            """
                SELECT p.publication_id, p.rate_card_digest, a.rate_card_id,
                       a.publication_id AS active_publication_id
                  FROM publication_head AS h
                  JOIN publications AS p ON p.publication_id = h.publication_id
                  LEFT JOIN active_rate_card AS a ON a.singleton = 1
                 WHERE h.singleton = 1 AND p.status = 'committed'
            """
        ).fetchone()
        if head is None:
            return None, None
        publication_digest = head[1]
        if head[3] != head[0]:
            return RateCardFrontier(str(publication_digest or ""), ()), publication_digest
        rows_cursor = connection.execute(
            """
                SELECT rate_card_id, digest, predecessor_rate_card_id,
                       source_name, source_url, effective_at_us, fetched_at_us,
                       currency, model_match_rules_json, four_class_rates_json,
                       credit_rates_json, reasoning_in_output, confidence,
                       validation_status
                  FROM rate_card_revisions
                 ORDER BY digest
            """
        )
        rows = [_row_dict(row, rows_cursor.description) for row in rows_cursor]
        by_id = {row.get("rate_card_id"): row for row in rows}
        head_id = head[2]
        if not isinstance(head_id, str) or head_id not in by_id:
            return RateCardFrontier(str(publication_digest or ""), ()), publication_digest
        chain: list[RateCardRevision] = []
        current_id: str | None = head_id
        seen: set[str] = set()
        while current_id is not None and current_id not in seen:
            seen.add(current_id)
            row = by_id[current_id]
            rules = _json_or_invalid(row.get("model_match_rules_json"), [])
            rates = _json_or_invalid(row.get("four_class_rates_json"), None)
            credits = _json_or_invalid(row.get("credit_rates_json"), None)
            predecessor_id = row.get("predecessor_rate_card_id")
            predecessor_digest = (
                by_id[predecessor_id].get("digest")
                if predecessor_id in by_id
                else ("0" * 64 if predecessor_id else None)
            )
            chain.append(
                RateCardRevision(
                    rate_card_id=str(row.get("rate_card_id") or ""),
                    digest=str(row.get("digest") or ""),
                    predecessor_digest=predecessor_digest,
                    effective_at_us=row.get("effective_at_us"),
                    fetched_at_us=row.get("fetched_at_us"),
                    source_name=str(row.get("source_name") or ""),
                    source_url=row.get("source_url"),
                    currency=str(row.get("currency") or ""),
                    model_match_rules=tuple(rules)
                    if isinstance(rules, Sequence) and not isinstance(rules, (str, bytes))
                    else rules,
                    four_class_rates=rates,
                    credit_rates=credits,
                    reasoning_in_output=bool(row.get("reasoning_in_output")),
                    confidence=str(row.get("confidence") or ""),
                    validation_status=str(row.get("validation_status") or ""),
                )
            )
            current_id = predecessor_id
        if current_id in seen:
            # The already-built predecessor links retain the cycle for the
            # pure compiler's typed fail-closed result.
            pass
        return RateCardFrontier(str(publication_digest or ""), tuple(chain)), publication_digest

    @staticmethod
    def _snapshot_token(connection: sqlite3.Connection, fallback: str) -> str:
        row = connection.execute(
            """
                SELECT p.publication_id
                  FROM publication_head AS h
                  JOIN publications AS p ON p.publication_id = h.publication_id
                 WHERE h.singleton = 1 AND p.status = 'committed'
            """
        ).fetchone()
        if row is None or not row[0]:
            if fallback:
                return fallback
            raise DatabaseAdapterContractError("read snapshot has no committed publication head")
        return str(row[0])

    def _evidence(
        self,
        connection: sqlite3.Connection,
        plan_request: PlanRequest,
        required: tuple[Mapping[str, Any], ...],
        selected_ids: Mapping[str, str],
        request_digest: str,
        owner_rules: Mapping[str, Mapping[str, Any]],
    ) -> tuple[EvidenceReferenceV1, ...]:
        references: list[EvidenceReferenceV1] = []
        for entry in required:
            role = entry["role"]
            kind = entry["selector_kind"]
            if kind not in _SELECTOR_KINDS:
                raise DatabaseAdapterContractError(f"unsupported selector kind: {kind}")
            rule = owner_rules.get(kind)
            if rule is None:
                raise DatabaseAdapterContractError(f"selector owner is missing for {kind}")
            if kind == "window":
                window = self._window_value(plan_request.parameters, role)
                if not isinstance(window, Mapping):
                    raise DatabaseAdapterContractError(f"{role} has no typed window")
                start, end, timezone = (
                    window.get("start_us"),
                    window.get("end_us"),
                    window.get("timezone", "UTC"),
                )
                if (
                    isinstance(start, bool)
                    or not isinstance(start, int)
                    or isinstance(end, bool)
                    or not isinstance(end, int)
                    or start > end
                    or not isinstance(timezone, str)
                    or not timezone
                ):
                    raise DatabaseAdapterContractError(f"{role} has malformed window bounds")
                logical_id = semantic_id("window", [request_digest, role, start, end, timezone])
                selector = entry.get("selector")
                if selector is None:
                    selector = f"window:{logical_id}"
                _prefix, suffix = self._selector_parts(selector, kind)
                if suffix != logical_id:
                    raise DatabaseAdapterContractError(
                        f"{role} window selector does not match its request parameter"
                    )
                supplied_logical_ids: list[Any] = []
                if role in selected_ids:
                    supplied_logical_ids.append(selected_ids[role])
                if "logical_id" in entry:
                    supplied_logical_ids.append(entry["logical_id"])
                if any(
                    not isinstance(value, str) or not value or value != logical_id
                    for value in supplied_logical_ids
                ):
                    raise DatabaseAdapterContractError(
                        f"{role} window logical ID does not match its request parameter"
                    )
                selected_logical_id = logical_id
                provenance: Mapping[str, Any] = {
                    "end_us": end,
                    "parameter_role": role,
                    "request_digest": request_digest,
                    "start_us": start,
                    "timezone": timezone,
                }
                references.append(
                    EvidenceReferenceV1(
                        role, kind, selector, selected_logical_id, "request_derivation", provenance
                    )
                )
                continue
            requested_logical_id = selected_ids.get(role)
            entry_logical_id = entry.get("logical_id")
            if entry_logical_id is not None and (
                not isinstance(entry_logical_id, str) or not entry_logical_id
            ):
                raise DatabaseAdapterContractError(f"{role} has no logical selector")
            if (
                requested_logical_id is not None
                and entry_logical_id is not None
                and requested_logical_id != entry_logical_id
            ):
                raise DatabaseAdapterContractError(f"{role} has conflicting selected logical IDs")
            entity_logical_id = (
                entry_logical_id if isinstance(entry_logical_id, str) else requested_logical_id
            )
            if not isinstance(entity_logical_id, str) or not entity_logical_id:
                raise DatabaseAdapterContractError(f"{role} has no selected selector")
            selector = entry.get("selector")
            if selector is None:
                selector = f"{_selector_prefix(kind)}:{entity_logical_id}"
            _prefix, suffix = self._selector_parts(selector, kind)
            provenance_kind = rule.get("provenance_kind")
            if not isinstance(provenance_kind, str):
                raise DatabaseAdapterContractError(f"{kind} owner provenance is malformed")
            provenance = self._owner_provenance(
                connection, kind, entity_logical_id, provenance_kind
            )
            if kind == "rate_card":
                resolved_digest = provenance.get("digest")
                if not isinstance(resolved_digest, str) or not resolved_digest:
                    raise DatabaseAdapterContractError("rate-card provenance has no digest")
                if suffix != resolved_digest or any(
                    value is not None and value != resolved_digest
                    for value in (requested_logical_id, entry_logical_id)
                ):
                    raise DatabaseAdapterContractError(
                        f"{role} rate-card selector does not identify its revision digest"
                    )
                entity_logical_id = resolved_digest
            elif entity_logical_id != suffix:
                raise DatabaseAdapterContractError(
                    f"{role} selector does not identify its selected entity"
                )
            references.append(
                EvidenceReferenceV1(
                    role,
                    kind,
                    selector,
                    entity_logical_id,
                    provenance_kind,
                    provenance,
                )
            )
        return tuple(references)

    @staticmethod
    def _window_value(parameters: Mapping[str, Any], role: str) -> Any:
        return parameters.get(role)

    def _owner_provenance(
        self,
        connection: sqlite3.Connection,
        kind: str,
        logical_id: str,
        provenance_kind: str,
    ) -> Mapping[str, Any]:
        if provenance_kind == "source_occurrence":
            query = _SOURCE_OWNER_ENTITY_QUERIES.get(kind)
            if query is None:
                raise DatabaseAdapterContractError(f"{kind} has no source owner")
            if connection.execute(query, (logical_id,)).fetchone() is None:
                raise DatabaseAdapterContractError(f"{kind} selector does not resolve")
            if kind == "model_profile":
                profile = connection.execute(
                    "SELECT model, reasoning_effort, service_tier FROM model_profiles WHERE model_profile_id = ?",
                    (logical_id,),
                ).fetchone()
                call_cursor = connection.execute(
                    "SELECT call_id FROM model_calls_visible WHERE model_profile_id = ? ORDER BY call_id",
                    (logical_id,),
                )
                call_ids = [row[0] for row in call_cursor]
                call_occurrences: list[Mapping[str, Any]] = []
                for call_id in call_ids:
                    occurrences = self._occurrence_mappings(connection, call_id)
                    if not occurrences:
                        raise DatabaseAdapterContractError(
                            f"{kind} representative call has no source occurrence"
                        )
                    call_occurrences.extend(occurrences)
                if profile is None or any(value in (None, "") for value in profile) or not call_ids:
                    raise DatabaseAdapterContractError(
                        f"{kind} selector has no representative call"
                    )
                call_occurrences.sort(
                    key=lambda item: (
                        item["record_ordinal"],
                        item["occurrence_id"],
                    )
                )
                return {
                    "profile_tuple": {
                        "model": profile[0],
                        "reasoning_effort": profile[1],
                        "service_tier": profile[2],
                    },
                    "representative_call_occurrences": call_occurrences,
                    "representative_call_selectors": [f"call:{call_id}" for call_id in call_ids],
                }
            occurrences = self._occurrence_mappings(connection, logical_id)
            if not occurrences:
                raise DatabaseAdapterContractError(f"{kind} selector has no source occurrence")
            return {"occurrences": occurrences}
        if provenance_kind == "configured_artifact":
            row = connection.execute(
                """
                    SELECT r.digest, r.source_name, r.fetched_at_us, r.validation_status
                      FROM rate_card_revisions AS r
                      JOIN publication_head AS h ON h.singleton = 1
                      JOIN publications AS p ON p.publication_id = h.publication_id
                     WHERE (r.rate_card_id = ? OR r.digest = ?)
                       AND p.rate_card_digest IS NOT NULL
                """,
                (logical_id, logical_id),
            ).fetchone()
            if row is None:
                raise DatabaseAdapterContractError("rate-card selector does not resolve")
            frontier, _digest = self._frontier(connection)
            if frontier is None or not any(
                isinstance(revision, RateCardRevision)
                and (revision.rate_card_id == logical_id or revision.digest == logical_id)
                for revision in frontier.revisions
            ):
                raise DatabaseAdapterContractError(
                    "rate-card selector is outside the captured frontier"
                )
            return {
                "digest": row[0],
                "source_name": row[1],
                "fetched_at_us": row[2],
                "validation_status": row[3],
            }
        if provenance_kind == "publication_commit":
            row = connection.execute(
                """
                    SELECT p.operation_id, p.artifact_manifest_sha256, p.committed_at_us
                      FROM publication_head AS h
                      JOIN publications AS p ON p.publication_id = h.publication_id
                     WHERE h.singleton = 1 AND p.publication_id = ? AND p.status = 'committed'
                """,
                (logical_id,),
            ).fetchone()
            if row is None:
                raise DatabaseAdapterContractError(
                    "publication selector does not resolve to the committed head"
                )
            return {
                "operation_id": row[0],
                "artifact_manifest_sha256": row[1],
                "committed_at_us": row[2],
            }
        if provenance_kind == "source_inventory":
            row = connection.execute(
                """
                    SELECT sm.source_id, sm.content_revision, sm.state,
                           h.publication_id AS selected_publication_id
                      FROM source_manifestations AS sm
                      JOIN publication_head AS h ON h.singleton = 1
                     WHERE sm.manifestation_id = ?
                """,
                (logical_id,),
            ).fetchone()
            if row is None:
                raise DatabaseAdapterContractError("source manifestation selector does not resolve")
            return {
                "source_id": row[0],
                "content_revision": row[1],
                "state": row[2],
                "selected_publication_id": row[3],
            }
        if provenance_kind == "derived_boundary_pair":
            row = connection.execute(
                """
                    SELECT start_observation_id, end_observation_id,
                           compatibility_basis
                      FROM allowance_intervals
                     WHERE interval_id = ?
                """,
                (logical_id,),
            ).fetchone()
            if row is None:
                raise DatabaseAdapterContractError("allowance interval selector does not resolve")
            start_id, end_id, compatibility = row
            start_occurrences = self._occurrence_mappings(connection, start_id)
            end_occurrences = self._occurrence_mappings(connection, end_id)
            if not compatibility or not start_occurrences or not end_occurrences:
                raise DatabaseAdapterContractError(
                    "allowance interval boundary provenance is incomplete"
                )
            return {
                "compatibility_version": "allowance-compatibility-v1",
                "end_observation_selector": f"allowance-observation:{end_id}",
                "end_occurrences": end_occurrences,
                "start_observation_selector": f"allowance-observation:{start_id}",
                "start_occurrences": start_occurrences,
            }
        raise DatabaseAdapterContractError(f"unsupported owner provenance: {provenance_kind}")

    @staticmethod
    def _occurrence_mappings(
        connection: sqlite3.Connection, logical_id: str
    ) -> list[Mapping[str, Any]]:
        cursor = connection.execute(_SOURCE_OCCURRENCES_SQL, (logical_id,))
        result: list[Mapping[str, Any]] = []
        for row in cursor:
            values = _row_dict(row, cursor.description)
            result.append(
                {
                    "adapter_version": values["adapter_version"],
                    "byte_end": values["byte_end"],
                    "byte_start": values["byte_start"],
                    "occurrence_id": values["occurrence_id"],
                    "record_ordinal": values["record_ordinal"],
                    "semantic_logical_id": values["semantic_logical_id"],
                    "source_manifestation_id": values["manifestation_id"],
                    "source_revision": values["source_revision"],
                }
            )
        return result

    @staticmethod
    def _validate_evidence(
        required: tuple[Mapping[str, Any], ...],
        materialized: Sequence[EvidenceReferenceV1],
        owner_rules: Mapping[str, Mapping[str, Any]],
    ) -> None:
        expected = [
            (entry.get("role"), entry.get("selector_kind"), entry.get("selector"))
            for entry in required
        ]
        actual = [(item.role, item.selector_kind, item.selector) for item in materialized]
        expected = [
            (role, kind, selector if selector is not None else next_item.selector)
            for (role, kind, selector), next_item in zip(expected, materialized, strict=True)
        ]
        if expected != actual:
            raise DatabaseAdapterContractError(
                "required and materialized evidence sequences differ"
            )
        for item in materialized:
            rule = owner_rules.get(item.selector_kind)
            if rule is None or item.provenance_kind != rule.get("provenance_kind"):
                raise DatabaseAdapterContractError(f"{item.role} uses unsupported provenance")
            fields = rule.get("required_provenance_fields")
            if isinstance(fields, (str, bytes)) or not isinstance(fields, Sequence):
                raise DatabaseAdapterContractError(f"{item.role} owner rule is malformed")
            missing = [
                field for field in fields if item.provenance.get(field) in (None, "", [], {})
            ]
            if missing:
                raise DatabaseAdapterContractError(
                    f"{item.role} provenance is incomplete: {missing}"
                )


def _json_or_invalid(value: Any, fallback: Any) -> Any:
    if not isinstance(value, str):
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


__all__ = [
    "AdapterMaterialization",
    "AdapterRequest",
    "DatabaseAdapterContractError",
    "DatabaseV1FactAdapter",
    "DatabaseV1FactMaterialization",
    "EvidenceReference",
    "EvidenceReferenceV1",
]
