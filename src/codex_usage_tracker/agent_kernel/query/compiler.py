"""Query-only database-v1 fact selection for named plan operands.

The compiler is deliberately narrower than a query service.  It turns one
injected plan contract and one typed request into canonical facts from a
caller-owned SQLite read transaction.  Plan derivation, answer assembly, and
cursor encoding remain separate pure or transport boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    compile_current_valuation_matches,
    validate_rate_card_frontier,
)
from codex_usage_tracker.agent_kernel.storage.rate_cards import (
    RateCardFrontierError,
    load_publication_rate_card_frontier,
)


class FactCompilerError(ValueError):
    """The supplied request or database snapshot cannot be compiled safely."""


DatabaseV1CompilerError = FactCompilerError
QueryCompilerError = FactCompilerError


@dataclass(frozen=True, slots=True)
class ExplainDetail:
    """One SQLite ``EXPLAIN QUERY PLAN`` row."""

    select_id: int
    order: int
    from_id: int
    detail: str

    @property
    def from_table(self) -> int:
        """Compatibility spelling for consumers that call this a table ID."""

        return self.from_id


@dataclass(frozen=True, slots=True)
class SqlSource:
    """The exact closed statement and its planner evidence."""

    statement_id: str
    sql: str
    parameters: tuple[Any, ...]
    explain: tuple[ExplainDetail, ...]

    @property
    def source_id(self) -> str:
        return self.statement_id

    @property
    def statement(self) -> str:
        return self.sql

    @property
    def explain_details(self) -> tuple[ExplainDetail, ...]:
        return self.explain


@dataclass(frozen=True, slots=True)
class FactCompilation:
    """Facts and read-snapshot diagnostics emitted by the production compiler."""

    request: PlanRequest
    facts: tuple[CanonicalFact, ...]
    publication_id: str
    request_digest: str
    sql_sources: tuple[SqlSource, ...]
    snapshot_token: str
    evidence_references: tuple[Any, ...] = ()

    @property
    def evidence(self) -> tuple[Any, ...]:
        return self.evidence_references

    @property
    def sql_evidence(self) -> tuple[SqlSource, ...]:
        return self.sql_sources

    @property
    def explain(self) -> tuple[ExplainDetail, ...]:
        return tuple(detail for source in self.sql_sources for detail in source.explain)


DatabaseV1FactMaterialization = FactCompilation
FactMaterialization = FactCompilation


def _text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        suffix = " or null" if nullable else ""
        raise FactCompilerError(f"{label} must be non-empty text{suffix}")
    return value


def _integer(value: Any, label: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FactCompilerError(f"{label} must be an integer{ ' or null' if nullable else ''}")
    return value


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise FactCompilerError("decimal is not finite")
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _decimal(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        parsed = value
        rendered = _canonical_decimal(parsed)
    elif isinstance(value, str):
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as error:
            raise FactCompilerError(f"database field {field} is not a decimal") from error
        rendered = _canonical_decimal(parsed)
        if value != rendered:
            raise FactCompilerError(f"database field {field} is not a canonical decimal string")
    else:
        raise FactCompilerError(f"database field {field} must be a decimal string or null")
    if not parsed.is_finite():
        raise FactCompilerError(f"database field {field} is not finite")
    return parsed


def _json(value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise FactCompilerError(f"database field {field} must be JSON text")

    def reject_constant(constant: str) -> Any:
        raise ValueError(f"non-finite JSON constant: {constant}")

    try:
        return json.loads(value, parse_constant=reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise FactCompilerError(f"malformed JSON in database field {field}") from error


def _typed_value(field: str, value: Any) -> Any:
    if field == "write_intent" and value is not None:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise FactCompilerError(f"database field {field} must be a SQLite boolean")
    if field in {
        "capabilities",
        "measurements",
        "valuation_coverage",
        "occurrence_coordinates",
        "first_boundary_coordinates",
        "resource_links",
    } and isinstance(value, str):
        return _json(value, field)
    if field in {"allowance_percent", "used_percent", "remaining_percent"}:
        return _decimal(value, field)
    return value


def _row_dict(row: Any, description: Sequence[Any] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}  # noqa: SIM118
    if isinstance(row, Mapping):
        return dict(row)
    if description is None:
        raise FactCompilerError("database row has no column description")
    return {column[0]: value for column, value in zip(description, row, strict=True)}


def _allowance_percent(values: Mapping[str, Any]) -> Decimal | None:
    used = _decimal(values.get("used_percent"), "used_percent")
    remaining = _decimal(values.get("remaining_percent"), "remaining_percent")
    for field, value in (("used_percent", used), ("remaining_percent", remaining)):
        if value is not None and (value < Decimal("0") or value > Decimal("100")):
            raise FactCompilerError(f"{field} is outside the canonical percentage range")
    if used is None and remaining is None:
        return None
    if used is not None and remaining is not None and used + remaining != Decimal("100"):
        raise FactCompilerError("allowance used_percent and remaining_percent disagree")
    return remaining if remaining is not None else Decimal("100") - used  # type: ignore[operator]


def _coordinates(values: Mapping[str, Any]) -> FactCoordinates:
    event_at_us = values.get("event_at_us", values.get("observed_at_us"))
    source_rank = _integer(values.get("source_rank", 0), "source_rank")
    source_order = _integer(values.get("source_order", 0), "source_order")
    event_kind_order = _integer(values.get("event_kind_order", 0), "event_kind_order")
    transition_rank = _integer(values.get("transition_rank", 0), "transition_rank")
    if any(
        value is None or value < 0
        for value in (source_rank, source_order, event_kind_order, transition_rank)
    ):
        raise FactCompilerError("fact coordinates require nonnegative source components")
    assert source_rank is not None
    assert source_order is not None
    assert event_kind_order is not None
    assert transition_rank is not None
    return FactCoordinates(
        event_at_us=_integer(event_at_us, "event_at_us", nullable=True),
        source_rank=source_rank,
        source_order=source_order,
        event_kind_order=event_kind_order,
        transition_rank=transition_rank,
    )


def _freeze_request_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise FactCompilerError("request mappings require string keys")
        return {key: _freeze_request_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_freeze_request_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise FactCompilerError("request contains a non-finite number")
    if isinstance(value, (str, int, bool)) or value is None or isinstance(value, float):
        return value
    raise FactCompilerError(f"request contains unsupported value: {type(value).__name__}")


def request_digest(request: PlanRequest) -> str:
    """Return the canonical request identity used by request-derived selectors."""

    if not isinstance(request, PlanRequest):
        raise FactCompilerError("request must be a PlanRequest")
    payload = json.dumps(
        _freeze_request_value(
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


def _attach_occurrence_event_coordinates(
    facts: Sequence[CanonicalFact],
) -> list[CanonicalFact]:
    """Bind occurrence/manifestation coordinates only to selected facts."""

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
        target_id = fact.values.get("semantic_logical_id")
        target = entity_coordinates.get(target_id) if isinstance(target_id, str) else None
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
        coordinates = fact.coordinates
        if fact.relation == "source_occurrence" and coordinates is not None:
            target_id = fact.values.get("semantic_logical_id")
            target = entity_coordinates.get(target_id) if isinstance(target_id, str) else None
            if target is None:
                continue
            coordinates = FactCoordinates(
                event_at_us=target.event_at_us,
                source_rank=coordinates.source_rank,
                source_order=coordinates.source_order,
                event_kind_order=coordinates.event_kind_order,
                transition_rank=coordinates.transition_rank,
            )
        elif (
            fact.relation == "source_manifestation"
            and coordinates is not None
            and coordinates.event_at_us is None
        ):
            event_at_us = manifestation_events.get(fact.logical_id)
            if event_at_us is None:
                continue
            coordinates = FactCoordinates(
                event_at_us=event_at_us,
                source_rank=coordinates.source_rank,
                source_order=coordinates.source_order,
                event_kind_order=coordinates.event_kind_order,
                transition_rank=coordinates.transition_rank,
            )
        normalized.append(
            CanonicalFact(
                relation=fact.relation,
                logical_id=fact.logical_id,
                values=fact.values,
                coordinates=coordinates,
            )
        )
    return normalized


# Every entry is a complete statement.  Callers can choose a statement ID,
# but cannot supply SQL, a table name, a predicate, or an order clause.
_STATEMENTS: Mapping[str, str] = MappingProxyType(
    {
        "canonical_call": """
            SELECT mc.call_id, mc.session_id, mc.turn_id, mc.model_profile_id,
                   s.project_id, NULL AS tool_id, mc.lifecycle_state AS lifecycle,
                   mc.context_window_tokens, mc.uncached_input_tokens,
                   mc.cached_input_tokens, mc.reasoning_tokens, mc.output_tokens,
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
                   p.reasoning_effort AS effort, p.service_tier AS tier,
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
                   t.start_transition_rank AS transition_rank
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
                   p.observed_through_us, p.indexed_through_us,
                   p.operation_id, p.artifact_manifest_sha256,
                   p.committed_at_us, p.status,
                   p.committed_at_us AS event_at_us,
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
        "snapshot_publication": """
            SELECT p.publication_id, p.rate_card_digest, p.status,
                   p.committed_at_us, p.observed_through_us
              FROM publication_head AS h
              JOIN publications AS p ON p.publication_id = h.publication_id
             WHERE h.singleton = 1
        """,
        "active_rate_card": """
            SELECT a.publication_id, a.rate_card_id, r.digest,
                   r.validation_status
              FROM active_rate_card AS a
              JOIN rate_card_revisions AS r ON r.rate_card_id = a.rate_card_id
             WHERE a.singleton = 1
        """,
        "rate_card_publication": """
            SELECT rate_card_digest
              FROM publications
             WHERE publication_id = ?
        """,
        "rate_card_revisions": """
            SELECT rate_card_id, digest, predecessor_rate_card_id,
                   effective_at_us, validation_status
              FROM rate_card_revisions
             ORDER BY digest
        """,
        "publication_source_coverage": """
            SELECT source_id,
                   selected_manifestation_count, selected_manifestation_bytes,
                   deferred_manifestation_count, deferred_manifestation_bytes,
                   malformed_manifestation_count, malformed_manifestation_bytes,
                   missing_manifestation_count, missing_manifestation_bytes,
                   uncertain_manifestation_count, uncertain_manifestation_bytes,
                   malformed_range_count, malformed_range_bytes,
                   selected_complete_record_count, tail_pending,
                   indexed_from_us, indexed_through_us,
                   guaranteed_complete_from_us, guaranteed_complete_through_us,
                   clock_quality, clock_uncertainty_us,
                   inventory_started_at_us, inventory_completed_at_us
              FROM publication_source_coverage
             WHERE publication_id = ?
             ORDER BY source_id
        """,
        "publication_inventory_sources": """
            SELECT DISTINCT source_id
              FROM source_manifestations
             ORDER BY source_id
        """,
        "publication_capability_coverage": """
            SELECT capability_id, eligible_entity_count, observed_entity_count,
                   unavailable_entity_count, measurement_mask, grade, basis
              FROM publication_capability_coverage
             WHERE publication_id = ?
             ORDER BY capability_id
        """,
        "publication_entity_counts": """
            SELECT entity_kind, entity_count
              FROM publication_entity_counts
             WHERE publication_id = ?
             ORDER BY entity_kind
        """,
        "valuation_calls": """
            SELECT call_id, model_profile_id, uncached_input_tokens,
                   cached_input_tokens, reasoning_tokens, output_tokens,
                   event_at_us, source_rank, source_order,
                   event_kind_order, transition_rank
              FROM model_calls_visible
             ORDER BY call_id
        """,
        "valuation_profiles": """
            SELECT model_profile_id, model, reasoning_effort, service_tier
              FROM model_profiles
             ORDER BY model_profile_id
        """,
    }
)

STATEMENT_IDS = tuple(_STATEMENTS)
SQL_STATEMENTS = _STATEMENTS

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


class _StatementRecorder:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.sources: list[SqlSource] = []

    def execute(self, statement_id: str, parameters: Sequence[Any] = ()) -> Any:
        sql = _STATEMENTS.get(statement_id)
        if sql is None:
            raise FactCompilerError(f"unknown closed SQL statement ID: {statement_id}")
        bound = tuple(parameters)
        explain_cursor = self.connection.execute("EXPLAIN QUERY PLAN " + sql, bound)
        explain = tuple(
            ExplainDetail(
                select_id=_integer(row[0], "EXPLAIN select ID") or 0,
                order=_integer(row[1], "EXPLAIN order") or 0,
                from_id=_integer(row[2], "EXPLAIN from ID") or 0,
                detail=_text(row[3], "EXPLAIN detail") or "",
            )
            for row in explain_cursor
        )
        cursor = self.connection.execute(sql, bound)
        self.sources.append(SqlSource(statement_id, sql, bound, explain))
        return cursor


def _require_query_snapshot(connection: sqlite3.Connection) -> None:
    if not isinstance(connection, sqlite3.Connection):
        raise FactCompilerError("connection must be a sqlite3.Connection")
    try:
        query_only = connection.execute("PRAGMA query_only").fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise FactCompilerError("connection is not a SQLite query surface") from error
    if int(query_only) != 1:
        raise FactCompilerError("database-v1 compiler requires PRAGMA query_only=1")
    if not connection.in_transaction:
        raise FactCompilerError(
            "database-v1 compiler requires one caller-owned active deferred read transaction"
        )


def _plan(contract: Mapping[str, Any], plan_id: str) -> Mapping[str, Any]:
    if not isinstance(contract, Mapping):
        raise FactCompilerError("plan-operand contract mapping is missing")
    plans = contract.get("plans")
    if isinstance(plans, (str, bytes)) or not isinstance(plans, Sequence):
        raise FactCompilerError("plan-operand contract plans are malformed")
    matches = [item for item in plans if isinstance(item, Mapping) and item.get("plan_id") == plan_id]
    if len(matches) != 1:
        raise FactCompilerError(f"plan must resolve exactly once: {plan_id}")
    selected = matches[0]
    if selected.get("status") != "resolved":
        raise FactCompilerError(
            f"plan derivation is blocked: {selected.get('blocked_reason') or selected.get('status')}"
        )
    return selected


def _validate_request(plan: Mapping[str, Any], request: PlanRequest) -> None:
    schema = plan.get("request_schema")
    if not isinstance(schema, Mapping):
        raise FactCompilerError("plan request schema is missing")
    required = schema.get("required")
    optional = schema.get("optional")
    if not isinstance(required, Mapping) or not isinstance(optional, Mapping):
        raise FactCompilerError("plan request parameter schema is malformed")
    supplied = set(request.parameters)
    missing = set(required) - supplied
    unknown = supplied - set(required) - set(optional)
    if missing or unknown:
        raise FactCompilerError(
            f"request parameter mismatch; missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )
    if schema.get("additional_parameters") is not False:
        raise FactCompilerError("plan must reject additional request parameters")


def _permitted_sources(plan: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    sources = plan.get("permitted_sources")
    if isinstance(sources, (str, bytes)) or not isinstance(sources, Sequence):
        raise FactCompilerError("plan permitted_sources are malformed")
    permitted: dict[str, frozenset[str]] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise FactCompilerError("plan source declaration is malformed")
        relation = source.get("relation")
        fields = source.get("fields")
        if not isinstance(relation, str) or relation in permitted or relation not in _RELATION_FIELDS:
            raise FactCompilerError(f"relation is not in the database-v1 allowlist: {relation!r}")
        if isinstance(fields, (str, bytes)) or not isinstance(fields, Sequence):
            raise FactCompilerError(f"fields are malformed for {relation}")
        if any(not isinstance(field, str) for field in fields):
            raise FactCompilerError(f"fields are malformed for {relation}")
        if len(fields) != len(set(fields)):
            raise FactCompilerError(f"fields are malformed for {relation}")
        selected = frozenset(fields)
        if not selected or not selected.issubset(_RELATION_FIELDS[relation]):
            raise FactCompilerError(f"fields are not allowed for {relation}")
        permitted[relation] = selected
    if not permitted:
        raise FactCompilerError("plan has no permitted sources")
    return permitted


def _source_key(fact: CanonicalFact) -> tuple[Any, ...]:
    if fact.coordinates is None:
        raise FactCompilerError(f"fact has no total-order coordinates: {fact.logical_id}")
    return fact.coordinates.key(fact.logical_id)


class DatabaseV1FactCompiler:
    """Compile one named request into facts from one active read snapshot."""

    source_name = "database_v1"

    def __init__(
        self,
        plan_operands: Mapping[str, Any],
        selector_provenance: Mapping[str, Any] | None = None,
        required_evidence: Any = None,
    ) -> None:
        self._plan_operands = plan_operands
        self._selector_provenance = selector_provenance
        self._required_evidence = required_evidence

    def compile(
        self,
        connection: sqlite3.Connection,
        request: PlanRequest,
        *,
        required_evidence: Any = None,
        selector_ids: Mapping[str, str] | None = None,
    ) -> FactCompilation:
        _require_query_snapshot(connection)
        if not isinstance(request, PlanRequest):
            raise FactCompilerError("request must be a PlanRequest")
        selected_plan = _plan(self._plan_operands, request.plan_id)
        _validate_request(selected_plan, request)
        permitted = _permitted_sources(selected_plan)
        digest = request_digest(request)
        recorder = _StatementRecorder(connection)

        try:
            publication_id, publication_digest = self._current_publication(recorder)
            self._validate_active_rate_card(recorder, publication_id, publication_digest)
            facts: list[CanonicalFact] = []
            for relation, fields in permitted.items():
                if relation == "valuation_match":
                    facts.extend(self._valuation_facts(recorder, fields, publication_id, publication_digest))
                    continue
                cursor = recorder.execute(relation)
                description = cursor.description
                for row in cursor:
                    raw = _row_dict(row, description)
                    if relation == "allowance_observation":
                        raw["allowance_percent"] = _allowance_percent(raw)
                    if relation == "publication":
                        self._validate_publication_authority(recorder, raw)
                    logical_id_field = _RELATION_ID_FIELDS[relation]
                    logical_id = _text(raw.get(logical_id_field), f"{relation}.{logical_id_field}")
                    assert logical_id is not None
                    values: dict[str, Any] = {}
                    for field in fields:
                        if field not in raw:
                            raise FactCompilerError(
                                f"closed statement {relation} did not produce permitted field {field}"
                            )
                        values[field] = _typed_value(field, raw[field])
                    facts.append(
                        CanonicalFact(
                            relation=relation,
                            logical_id=logical_id,
                            values=values,
                            coordinates=_coordinates(raw),
                        )
                    )
            if not facts:
                raise FactCompilerError(f"database snapshot produced no facts for {request.plan_id}")
            facts = _attach_occurrence_event_coordinates(facts)
            ordered = tuple(sorted(facts, key=_source_key))
            keys = [_source_key(fact) for fact in ordered]
            if len(keys) != len(set(keys)):
                raise FactCompilerError("fact coordinates do not form a total order")

            evidence: tuple[Any, ...] = ()
            requested_evidence = required_evidence if required_evidence is not None else self._required_evidence
            if requested_evidence is not None:
                if self._selector_provenance is None:
                    raise FactCompilerError("selector-provenance contract mapping is missing")
                from codex_usage_tracker.agent_kernel.evidence.selectors import (
                    resolve_evidence_references,
                )

                evidence = resolve_evidence_references(
                    connection,
                    request,
                    self._selector_provenance,
                    requested_evidence,
                    selector_ids=selector_ids,
                    publication_id=publication_id,
                )
            return FactCompilation(
                request=request,
                facts=ordered,
                publication_id=publication_id,
                request_digest=digest,
                sql_sources=tuple(recorder.sources),
                snapshot_token=publication_id,
                evidence_references=evidence,
            )
        except FactCompilerError:
            raise
        except (sqlite3.DatabaseError, RateCardFrontierError, TypeError, ValueError) as error:
            raise FactCompilerError("database-v1 snapshot cannot be compiled") from error

    materialize = compile

    def _current_publication(
        self, recorder: _StatementRecorder
    ) -> tuple[str, str | None]:
        cursor = recorder.execute("snapshot_publication")
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise FactCompilerError("database snapshot has no unique committed publication head")
        row = _row_dict(rows[0], cursor.description)
        publication_id = _text(row.get("publication_id"), "publication_id")
        if row.get("status") != "committed":
            raise FactCompilerError("publication head is not committed")
        assert publication_id is not None
        digest = row.get("rate_card_digest")
        if digest is not None and (not isinstance(digest, str) or not digest):
            raise FactCompilerError("publication rate-card digest is malformed")
        return publication_id, digest

    def _validate_active_rate_card(
        self,
        recorder: _StatementRecorder,
        publication_id: str,
        publication_digest: str | None,
    ) -> None:
        cursor = recorder.execute("active_rate_card")
        rows = [_row_dict(row, cursor.description) for row in cursor]
        if publication_digest is None:
            if rows:
                raise FactCompilerError("active rate-card authority exists without publication capture")
            return
        if len(rows) != 1:
            raise FactCompilerError("active rate-card authority is missing or ambiguous")
        row = rows[0]
        if (
            row.get("publication_id") != publication_id
            or row.get("digest") != publication_digest
            or row.get("validation_status") != "valid"
        ):
            raise FactCompilerError("active rate-card authority does not match publication head")

        digest_cursor = recorder.execute("rate_card_publication", (publication_id,))
        digest_rows = digest_cursor.fetchall()
        if len(digest_rows) != 1 or digest_rows[0][0] != publication_digest:
            raise FactCompilerError("publication rate-card authority is inconsistent")

    def _valuation_facts(
        self,
        recorder: _StatementRecorder,
        permitted_fields: frozenset[str],
        publication_id: str,
        publication_digest: str | None,
    ) -> list[CanonicalFact]:
        calls_cursor = recorder.execute("valuation_calls")
        calls = [_row_dict(row, calls_cursor.description) for row in calls_cursor]
        profiles_cursor = recorder.execute("valuation_profiles")
        profiles = [_row_dict(row, profiles_cursor.description) for row in profiles_cursor]
        # The production loader is the authority for the immutable captured
        # frontier.  The fixed metadata statement above is only the compiler's
        # source/explain ledger; it does not replace the production loader.
        frontier = load_publication_rate_card_frontier(recorder.connection, publication_id)
        reason = validate_rate_card_frontier(frontier, publication_digest)
        if frontier is not None:
            recorder.execute("rate_card_revisions")
        if reason is not None and frontier is not None:
            raise FactCompilerError(f"invalid publication rate-card frontier: {reason.value}")
        try:
            matches = compile_current_valuation_matches(
                calls,
                profiles,
                frontier,
                publication_rate_card_digest=publication_digest,
            )
        except (TypeError, ValueError) as error:
            raise FactCompilerError("publication valuation cannot be compiled") from error

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
                "cost_grade": match.cost_grade,
                "estimated_credits": (
                    Decimal(match.estimated_credits)
                    if match.estimated_credits is not None
                    else None
                ),
                "match_basis": match.match_basis,
                "rate_card_digest": match.rate_card_digest,
                "cost_unpriced_reason": cost_reason,
                "unpriced_reason": cost_reason or credit_reason,
            }
            selected = {key: value for key, value in values.items() if key in permitted_fields}
            logical_id = match.valuation_id or semantic_id(
                "valuation", [match.call_id, match.rate_card_digest or publication_digest]
            )
            facts.append(
                CanonicalFact(
                    relation="valuation_match",
                    logical_id=logical_id,
                    values=selected,
                    coordinates=coordinates.get(match.call_id),
                )
            )
        return facts

    def _validate_publication_authority(
        self,
        recorder: _StatementRecorder,
        publication: Mapping[str, Any],
    ) -> None:
        publication_id = _text(publication.get("publication_id"), "publication.publication_id")
        assert publication_id is not None
        _integer(publication.get("indexed_from_us"), "publication.indexed_from_us", nullable=True)
        _integer(
            publication.get("guaranteed_complete_from_us"),
            "publication.guaranteed_complete_from_us",
            nullable=True,
        )
        _integer(
            publication.get("observed_through_us"),
            "publication.observed_through_us",
            nullable=True,
        )
        _integer(
            publication.get("indexed_through_us"),
            "publication.indexed_through_us",
            nullable=True,
        )
        source_cursor = recorder.execute("publication_source_coverage", (publication_id,))
        source_rows = [_row_dict(row, source_cursor.description) for row in source_cursor]
        if not source_rows:
            raise FactCompilerError("publication source coverage is missing")
        source_ids: set[str] = set()
        count_fields = (
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
            source_id = _text(row.get("source_id"), "source coverage source_id")
            assert source_id is not None
            if source_id in source_ids:
                raise FactCompilerError("publication source coverage is duplicated")
            source_ids.add(source_id)
            for field in count_fields:
                value = _integer(row.get(field), f"source coverage {field}")
                if value is None or value < 0:
                    raise FactCompilerError(f"source coverage {field} is negative")
            tail_pending = _integer(row.get("tail_pending"), "source coverage tail_pending")
            if tail_pending not in (0, 1):
                raise FactCompilerError("source coverage tail_pending is malformed")
            for field in (
                "indexed_from_us",
                "indexed_through_us",
                "guaranteed_complete_from_us",
                "guaranteed_complete_through_us",
            ):
                _integer(row.get(field), f"source coverage {field}", nullable=True)
            indexed_from, indexed_through = row.get("indexed_from_us"), row.get("indexed_through_us")
            complete_from, complete_through = (
                row.get("guaranteed_complete_from_us"),
                row.get("guaranteed_complete_through_us"),
            )
            if (indexed_from is None) != (indexed_through is None) or (
                indexed_from is not None and indexed_from > indexed_through
            ):
                raise FactCompilerError("publication source indexed bounds are malformed")
            if (complete_from is None) != (complete_through is None) or (
                complete_from is not None and complete_from > complete_through
            ):
                raise FactCompilerError("publication source completeness bounds are malformed")
            clock_quality = row.get("clock_quality")
            if clock_quality not in {"unknown", "unsynchronized", "bounded"}:
                raise FactCompilerError("publication source clock quality is malformed")
            uncertainty = _integer(
                row.get("clock_uncertainty_us"),
                "source coverage clock uncertainty",
                nullable=True,
            )
            if clock_quality == "bounded" and uncertainty is None:
                raise FactCompilerError("bounded publication source has no clock uncertainty")
            if clock_quality != "bounded" and uncertainty is not None:
                raise FactCompilerError("non-bounded publication source has clock uncertainty")
            started = _integer(row.get("inventory_started_at_us"), "source inventory start")
            completed = _integer(row.get("inventory_completed_at_us"), "source inventory end")
            if started is None or completed is None or started > completed:
                raise FactCompilerError("source inventory bounds are malformed")
            if (
                indexed_from != publication.get("indexed_from_us")
                or indexed_through != publication.get("indexed_through_us")
                or complete_from != publication.get("guaranteed_complete_from_us")
                or complete_through
                != (
                    publication.get("indexed_through_us")
                    if publication.get("guaranteed_complete_from_us") is not None
                    else None
                )
            ):
                raise FactCompilerError("publication and source coverage bounds disagree")

        inventory_cursor = recorder.execute("publication_inventory_sources")
        inventory_ids = {row[0] for row in inventory_cursor}
        if inventory_ids != source_ids:
            raise FactCompilerError("publication source coverage does not match source inventory")

        capability_cursor = recorder.execute("publication_capability_coverage", (publication_id,))
        capability_rows = [_row_dict(row, capability_cursor.description) for row in capability_cursor]
        if not capability_rows:
            raise FactCompilerError("publication capability coverage is missing")
        capabilities: dict[str, bool] = {}
        valuation_rows: list[Mapping[str, Any]] = []
        for row in capability_rows:
            capability_id = _text(row.get("capability_id"), "capability_id")
            assert capability_id is not None
            if capability_id in capabilities:
                raise FactCompilerError("publication capability coverage is duplicated")
            eligible = _integer(row.get("eligible_entity_count"), "capability eligible count")
            observed = _integer(row.get("observed_entity_count"), "capability observed count")
            unavailable = _integer(row.get("unavailable_entity_count"), "capability unavailable count")
            mask = _integer(row.get("measurement_mask"), "capability measurement mask")
            if (
                eligible is None
                or observed is None
                or unavailable is None
                or mask is None
                or min(eligible, observed, unavailable, mask) < 0
                or observed > eligible
                or unavailable > eligible
                or observed + unavailable > eligible
            ):
                raise FactCompilerError("publication capability counts are inconsistent")
            if row.get("grade") not in {"exact", "deterministic", "configured_estimate"}:
                raise FactCompilerError("publication capability grade is malformed")
            if not isinstance(row.get("basis"), str) or not row.get("basis"):
                raise FactCompilerError("publication capability basis is malformed")
            capabilities[capability_id] = observed > 0
            if capability_id == "valuation":
                valuation_rows.append(row)
        if len(valuation_rows) != 1:
            raise FactCompilerError("publication valuation coverage is missing or ambiguous")
        valuation = valuation_rows[0]
        if valuation.get("grade") != "configured_estimate":
            raise FactCompilerError("publication valuation coverage is not a configured estimate")
        eligible = int(valuation["eligible_entity_count"])
        unavailable = int(valuation["unavailable_entity_count"])
        expected_valuation = {
            "basis": "configured_estimate",
            "priced_calls": eligible - unavailable,
        }

        entity_cursor = recorder.execute("publication_entity_counts", (publication_id,))
        entity_rows = [_row_dict(row, entity_cursor.description) for row in entity_cursor]
        if not entity_rows:
            raise FactCompilerError("publication entity counts are missing")
        measurements: dict[str, int] = {}
        for row in entity_rows:
            kind = _text(row.get("entity_kind"), "publication entity kind")
            assert kind is not None
            count = _integer(row.get("entity_count"), "publication entity count")
            if kind in measurements or count is None or count < 0:
                raise FactCompilerError("publication entity counts are malformed")
            measurements[kind] = count
        if _typed_value("capabilities", publication.get("capabilities")) != capabilities:
            raise FactCompilerError("publication capabilities do not match authoritative coverage")
        if _typed_value("measurements", publication.get("measurements")) != measurements:
            raise FactCompilerError("publication measurements do not match authoritative counts")
        if _typed_value("valuation_coverage", publication.get("valuation_coverage")) != expected_valuation:
            raise FactCompilerError("publication valuation coverage does not match authoritative coverage")


def compile_database_facts(
    connection: sqlite3.Connection,
    plan_operands: Mapping[str, Any],
    request: PlanRequest,
    *,
    selector_provenance: Mapping[str, Any] | None = None,
    required_evidence: Any = None,
    selector_ids: Mapping[str, str] | None = None,
) -> FactCompilation:
    """Functional entry point for the production fact compiler."""

    return DatabaseV1FactCompiler(
        plan_operands,
        selector_provenance,
        required_evidence,
    ).compile(
        connection,
        request,
        selector_ids=selector_ids,
    )


compile_facts = compile_database_facts


__all__ = [
    "DatabaseV1CompilerError",
    "DatabaseV1FactCompiler",
    "DatabaseV1FactMaterialization",
    "ExplainDetail",
    "FactCompilation",
    "FactCompilerError",
    "FactMaterialization",
    "QueryCompilerError",
    "SQL_STATEMENTS",
    "STATEMENT_IDS",
    "SqlSource",
    "compile_database_facts",
    "compile_facts",
    "request_digest",
]
