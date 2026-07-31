"""Independent structural-v2 to canonical-fact normalization for CK-07E.

The adapter accepts only body-free structural declarations and pure contract
inputs.  It owns its evidence and materialization values so the structural
truth lane cannot accidentally share adapter state with the database lane.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
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


class StructuralReferenceAdapterError(ValueError):
    """The structural declaration cannot satisfy the adapter contract."""


def _attach_occurrence_event_coordinates(
    facts: Sequence[CanonicalFact],
) -> list[CanonicalFact]:
    entity_coordinates = {
        fact.logical_id: fact.coordinates
        for fact in facts
        if fact.relation != "source_occurrence"
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
        coordinates = fact.coordinates
        if fact.relation == "source_occurrence" and coordinates is not None:
            semantic_logical_id = fact.values.get("semantic_logical_id")
            target = (
                entity_coordinates.get(semantic_logical_id)
                if isinstance(semantic_logical_id, str)
                else None
            )
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


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One owner-resolved selector and its typed provenance."""

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
            raise StructuralReferenceAdapterError(
                "evidence references require non-empty string identities"
            )
        if not isinstance(self.provenance, Mapping):
            raise StructuralReferenceAdapterError("evidence provenance must be a mapping")
        _assert_structural(self.provenance, path=f"evidence.{self.role}")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True, slots=True)
class AdapterMaterialization:
    """Frozen structural facts, request, and ordered evidence references."""

    request: PlanRequest
    facts: tuple[CanonicalFact, ...]
    evidence_references: tuple[EvidenceReference, ...]
    source: str
    snapshot_token: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, PlanRequest):
            raise StructuralReferenceAdapterError("materialization requires a PlanRequest")
        if not isinstance(self.facts, tuple) or not isinstance(self.evidence_references, tuple):
            raise StructuralReferenceAdapterError("materialization collections must be tuples")
        if not isinstance(self.source, str) or not self.source:
            raise StructuralReferenceAdapterError("materialization source is required")
        if not isinstance(self.snapshot_token, str) or not self.snapshot_token:
            raise StructuralReferenceAdapterError("materialization snapshot token is required")


_STRUCTURAL_SCHEMAS = frozenset(
    {
        "codex-usage-tracker.agent-kernel.structural-v2.v1",
        "codex-usage-tracker.synthetic-structural-v2.v1",
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
_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "answers",
        "comparison",
        "comparisons",
        "expected",
        "grade",
        "grades",
        "grading",
        "oracle",
        "oracle_case",
        "question_cases",
        "scenario_answer",
    }
)
_FORBIDDEN_BODY_KEYS = frozenset(
    {
        "body",
        "command",
        "content",
        "diff",
        "patch",
        "prompt",
        "reasoning",
        "response",
        "stderr",
        "stdout",
        "tool_output",
    }
)


def _assert_structural(value: Any, *, path: str = "record") -> None:
    """Reject answer caches, bodies, and binary floats recursively."""

    if isinstance(value, float):
        raise StructuralReferenceAdapterError(f"{path} contains a binary float")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StructuralReferenceAdapterError(f"{path} contains a non-string key")
            lowered = key.lower()
            if lowered in _FORBIDDEN_KEYS or lowered.startswith(
                ("answer_", "oracle_", "grading_", "comparison_")
            ):
                raise StructuralReferenceAdapterError(
                    f"{path} contains forbidden answer field: {key}"
                )
            if (
                lowered in _FORBIDDEN_BODY_KEYS
                or lowered.endswith("_body")
                or lowered.startswith("raw_")
            ):
                raise StructuralReferenceAdapterError(
                    f"{path} contains forbidden body field: {key}"
                )
            _assert_structural(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            _assert_structural(item, path=f"{path}[{index}]")
    elif isinstance(value, Decimal) and not value.is_finite():
        raise StructuralReferenceAdapterError(f"{path} contains a non-finite decimal")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StructuralReferenceAdapterError(f"{label} must be a string-keyed mapping")
    return value


def _integer(value: Any, label: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise StructuralReferenceAdapterError(f"{label} must be an integer")
    return value


def _required_integer(value: Any, label: str) -> int:
    parsed = _integer(value, label)
    if parsed is None:
        raise StructuralReferenceAdapterError(f"{label} must be an integer")
    return parsed


def _coordinates(raw: Mapping[str, Any], label: str) -> FactCoordinates:
    source = raw.get("coordinates", raw)
    if source is None:
        source = {}
    source = _mapping(source, f"{label}.coordinates")
    return FactCoordinates(
        event_at_us=_integer(source.get("event_at_us"), f"{label}.event_at_us", nullable=True),
        source_rank=_required_integer(source.get("source_rank", 0), f"{label}.source_rank"),
        source_order=_required_integer(source.get("source_order", 0), f"{label}.source_order"),
        event_kind_order=_required_integer(
            source.get("event_kind_order", 0), f"{label}.event_kind_order"
        ),
        transition_rank=_required_integer(
            source.get("transition_rank", 0), f"{label}.transition_rank"
        ),
    )


def _ordered_occurrences(
    values: Sequence[Mapping[str, Any]],
    label: str,
) -> list[Mapping[str, Any]]:
    def key(value: Mapping[str, Any]) -> tuple[int, str]:
        ordinal = value.get("record_ordinal")
        occurrence_id = value.get("occurrence_id")
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or not isinstance(occurrence_id, str)
            or not occurrence_id
        ):
            raise StructuralReferenceAdapterError(f"{label} has malformed occurrence ordering")
        return ordinal, occurrence_id

    return sorted(values, key=key)


def _selected_fact_values(
    relation: str,
    values: Mapping[str, Any],
    fields: frozenset[str],
) -> dict[str, Any]:
    selected = {key: value for key, value in values.items() if key in fields}
    if relation == "allowance_observation":
        for field in ("allowance_percent", "used_percent", "remaining_percent"):
            value = selected.get(field)
            if isinstance(value, str):
                selected[field] = Decimal(value)
    if relation != "tool_invocation":
        return selected
    links = selected.get("resource_links")
    primary = selected.get("resource_id")
    if (
        not isinstance(links, Sequence)
        or isinstance(links, (str, bytes))
        or any(not isinstance(item, str) or not item for item in links)
    ):
        raise StructuralReferenceAdapterError("tool_invocation resource_links must be resource IDs")
    unique = set(links)
    if isinstance(primary, str) and primary:
        unique.add(primary)
        selected["resource_links"] = [
            primary,
            *sorted(item for item in unique if item != primary),
        ]
    else:
        selected["resource_links"] = sorted(unique)
    return selected


def _request_digest(request: PlanRequest) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: normalize(item) for key, item in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, Decimal):
            return str(value)
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


def _selector_prefix(kind: str) -> str:
    return kind.replace("_", "-")


def _selector_parts(selector: str) -> tuple[str, str]:
    if not isinstance(selector, str):
        raise StructuralReferenceAdapterError("selector must be a string")
    prefix, separator, logical_id = selector.partition(":")
    if not separator or not prefix or not logical_id:
        raise StructuralReferenceAdapterError(f"invalid selector: {selector!r}")
    return prefix, logical_id


def _required_entries(required: Any) -> tuple[Mapping[str, Any], ...]:
    """Normalize ordered selection mappings without losing their order."""

    if isinstance(required, Mapping):
        for key in ("selections", "required", "evidence"):
            if key in required:
                return _required_entries(required[key])
        if "required_role_kinds" in required:
            role_kinds = required["required_role_kinds"]
            selector_ids = required.get("selector_ids", {})
            if not isinstance(role_kinds, Sequence) or not isinstance(selector_ids, Mapping):
                raise StructuralReferenceAdapterError("required evidence mapping is malformed")
            entries = []
            for pair in role_kinds:
                if (
                    not isinstance(pair, Sequence)
                    or len(pair) != 2
                    or not all(isinstance(item, str) for item in pair)
                ):
                    raise StructuralReferenceAdapterError("required role/kind entry is malformed")
                role, kind = pair
                if kind == "window":
                    entry = {"role": role, "selector_kind": kind}
                    selector = selector_ids.get(role, selector_ids.get(kind))
                    if selector is not None:
                        if not isinstance(selector, str):
                            raise StructuralReferenceAdapterError(
                                f"{role} has an invalid exact selector mapping"
                            )
                        entry["selector"] = selector
                    entries.append(entry)
                else:
                    selector = selector_ids.get(role, selector_ids.get(kind))
                    if not isinstance(selector, str):
                        raise StructuralReferenceAdapterError(
                            f"{role} has no exact selector mapping"
                        )
                    entries.append({"role": role, "selector_kind": kind, "selector": selector})
            return tuple(entries)
        entries = []
        for role, value in required.items():
            if not isinstance(role, str):
                raise StructuralReferenceAdapterError("evidence roles must be strings")
            if isinstance(value, Mapping):
                item = dict(value)
                item.setdefault("role", role)
                entries.append(item)
            elif isinstance(value, str):
                entries.append({"role": role, "selector": value})
            else:
                raise StructuralReferenceAdapterError("evidence selection must be a mapping")
        return tuple(entries)
    if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
        if not all(isinstance(item, Mapping) for item in required):
            raise StructuralReferenceAdapterError("evidence selections must be mappings")
        return tuple(required)
    raise StructuralReferenceAdapterError("required evidence selections are malformed")


class StructuralReferenceFactAdapter:
    """Build permitted canonical facts and evidence from structural mappings."""

    source_name = "structural_reference"

    def __init__(
        self,
        plan_contract: Mapping[str, Any],
        selector_contract: Mapping[str, Any],
    ) -> None:
        self._plan_contract = _mapping(plan_contract, "plan contract")
        selector_contract = _mapping(selector_contract, "selector contract")
        ownership = selector_contract.get("ownership", ())
        if not isinstance(ownership, Sequence):
            raise StructuralReferenceAdapterError("selector ownership is malformed")
        self._owner_rules = {
            item["kind"]: item
            for item in ownership
            if isinstance(item, Mapping) and isinstance(item.get("kind"), str)
        }

    def materialize(
        self,
        declarations: Mapping[str, Any],
        request: PlanRequest,
        required_evidence: Any,
    ) -> AdapterMaterialization:
        declarations = self._validate_declarations(declarations)
        if not isinstance(request, PlanRequest):
            raise StructuralReferenceAdapterError("request must be a PlanRequest")
        _assert_structural(request.parameters, path="request.parameters")
        _assert_structural(required_evidence, path="required_evidence")
        plan = self._plan(request.plan_id)
        permitted = self._permitted_sources(plan)
        raw_facts = self._facts(declarations["facts"])
        facts = [
            CanonicalFact(
                relation,
                logical_id,
                _selected_fact_values(relation, values, permitted[relation]),
                coordinates,
            )
            for relation, logical_id, values, coordinates in raw_facts
            if relation in permitted
        ]
        if "valuation_match" in permitted:
            facts = [fact for fact in facts if fact.relation != "valuation_match"]
            facts.extend(
                self._valuation_facts(declarations, raw_facts, permitted["valuation_match"])
            )
        if not facts:
            raise StructuralReferenceAdapterError(
                f"scenario has no permitted facts for {request.plan_id}"
            )
        facts = _attach_occurrence_event_coordinates(facts)
        references = self._evidence(declarations, request, required_evidence, raw_facts)

        def fact_key(fact: CanonicalFact) -> tuple[int, int, int, int, int, str]:
            if fact.coordinates is None:
                raise StructuralReferenceAdapterError(
                    f"{fact.relation} fact has no total-order coordinates"
                )
            return fact.coordinates.key(fact.logical_id)

        ordered = tuple(sorted(facts, key=fact_key))
        return AdapterMaterialization(
            request=request,
            facts=ordered,
            evidence_references=references,
            source=self.source_name,
            snapshot_token=declarations["scenario_id"],
        )

    def _validate_declarations(self, declarations: Mapping[str, Any]) -> Mapping[str, Any]:
        _assert_structural(declarations)
        declarations = _mapping(declarations, "structural declarations")
        if declarations.get("schema") not in _STRUCTURAL_SCHEMAS:
            raise StructuralReferenceAdapterError("unsupported structural-v2 schema")
        scenario_id = declarations.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise StructuralReferenceAdapterError("scenario_id must be non-empty")
        for key in (
            "facts",
            "occurrences",
            "selector_entities",
            "source_manifestations",
        ):
            if key not in declarations or not isinstance(declarations[key], (Mapping, Sequence)):
                raise StructuralReferenceAdapterError(f"{key} is missing or malformed")
        return declarations

    def _plan(self, plan_id: str) -> Mapping[str, Any]:
        if self._plan_contract.get("schema") != "codex-usage-tracker.plan-operand-contract.v1":
            raise StructuralReferenceAdapterError("unsupported plan operand contract")
        plans = self._plan_contract.get("plans")
        if not isinstance(plans, Sequence):
            raise StructuralReferenceAdapterError("plan contract plans are malformed")
        matches = [
            item for item in plans if isinstance(item, Mapping) and item.get("plan_id") == plan_id
        ]
        if len(matches) != 1:
            raise StructuralReferenceAdapterError(f"plan must resolve exactly once: {plan_id}")
        return matches[0]

    @staticmethod
    def _permitted_sources(plan: Mapping[str, Any]) -> dict[str, frozenset[str]]:
        sources = plan.get("permitted_sources")
        if not isinstance(sources, Sequence):
            raise StructuralReferenceAdapterError("permitted_sources are malformed")
        permitted: dict[str, frozenset[str]] = {}
        for source in sources:
            if not isinstance(source, Mapping):
                raise StructuralReferenceAdapterError("permitted source is malformed")
            relation, fields = source.get("relation"), source.get("fields")
            if not isinstance(relation, str) or not isinstance(fields, Sequence):
                raise StructuralReferenceAdapterError("permitted source identity is malformed")
            if any(not isinstance(field, str) for field in fields):
                raise StructuralReferenceAdapterError("permitted source fields must be strings")
            permitted[relation] = frozenset(fields)
        return permitted

    @staticmethod
    def _facts(raw: Any) -> tuple[tuple[str, str, Mapping[str, Any], FactCoordinates], ...]:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise StructuralReferenceAdapterError("facts must be an ordered sequence")
        result = []
        for index, item in enumerate(raw):
            item = _mapping(item, f"facts[{index}]")
            relation = item.get("relation")
            logical_id = item.get("logical_id")
            values = item.get("values", {})
            if not isinstance(relation, str) or not relation:
                raise StructuralReferenceAdapterError(f"facts[{index}] has no relation")
            if not isinstance(logical_id, str) or not logical_id:
                raise StructuralReferenceAdapterError(f"facts[{index}] has no logical_id")
            values = _mapping(values, f"facts[{index}].values")
            result.append((relation, logical_id, values, _coordinates(item, f"facts[{index}]")))
        return tuple(result)

    @staticmethod
    def _frontier(raw: Any) -> RateCardFrontier | None:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise StructuralReferenceAdapterError("rate_card_frontier must be a mapping or null")
        revisions = raw.get("revisions")
        if not isinstance(revisions, Sequence):
            raise StructuralReferenceAdapterError("rate_card_frontier revisions are malformed")
        typed: list[RateCardRevision] = []
        required = (
            "rate_card_id",
            "digest",
            "source_name",
            "currency",
            "model_match_rules",
            "four_class_rates",
            "credit_rates",
            "reasoning_in_output",
            "confidence",
            "validation_status",
        )
        for index, value in enumerate(revisions):
            value = _mapping(value, f"rate_card_frontier.revisions[{index}]")
            missing = [field for field in required if field not in value]
            if missing:
                raise StructuralReferenceAdapterError(
                    f"rate-card revision is missing fields: {missing}"
                )
            typed.append(
                RateCardRevision(
                    rate_card_id=value["rate_card_id"],
                    digest=value["digest"],
                    predecessor_digest=value.get("predecessor_digest"),
                    effective_at_us=value.get("effective_at_us"),
                    fetched_at_us=value.get("fetched_at_us"),
                    source_name=value["source_name"],
                    source_url=value.get("source_url"),
                    currency=value["currency"],
                    model_match_rules=tuple(value["model_match_rules"]),
                    four_class_rates=value["four_class_rates"],
                    credit_rates=value["credit_rates"],
                    reasoning_in_output=value["reasoning_in_output"],
                    confidence=value["confidence"],
                    validation_status=value["validation_status"],
                )
            )
        head_digest = raw.get("head_digest")
        if not isinstance(head_digest, str) or not head_digest:
            raise StructuralReferenceAdapterError(
                "rate-card frontier head_digest must be a non-empty string"
            )
        return RateCardFrontier(head_digest=head_digest, revisions=tuple(typed))

    def _valuation_facts(
        self,
        declarations: Mapping[str, Any],
        raw_facts: Sequence[tuple[str, str, Mapping[str, Any], FactCoordinates]],
        permitted_fields: frozenset[str],
    ) -> tuple[CanonicalFact, ...]:
        calls = []
        profiles = []
        coordinates: dict[str, FactCoordinates] = {}
        for relation, logical_id, values, fact_coordinates in raw_facts:
            if relation == "canonical_call":
                call_id = values.get("call_id", logical_id)
                coordinates[logical_id] = fact_coordinates
                if isinstance(call_id, str):
                    coordinates[call_id] = fact_coordinates
                calls.append(
                    {
                        "call_id": call_id,
                        "model_profile_id": values.get("model_profile_id"),
                        "uncached_input_tokens": values.get("uncached_input_tokens"),
                        "cached_input_tokens": values.get("cached_input_tokens"),
                        "reasoning_tokens": values.get("reasoning_tokens"),
                        "output_tokens": values.get("output_tokens"),
                        "event_at_us": fact_coordinates.event_at_us,
                    }
                )
            elif relation == "model_profile":
                profiles.append(
                    {
                        "model_profile_id": values.get("model_profile_id", logical_id),
                        "model": values.get("model"),
                        "reasoning_effort": values.get("effort", values.get("reasoning_effort")),
                        "service_tier": values.get("tier", values.get("service_tier")),
                    }
                )
        publication_digest = declarations.get("publication_rate_card_digest")
        if publication_digest is not None and not isinstance(publication_digest, str):
            raise StructuralReferenceAdapterError(
                "publication_rate_card_digest must be a string or null"
            )
        try:
            matches = compile_current_valuation_matches(
                calls,
                profiles,
                self._frontier(declarations.get("rate_card_frontier")),
                publication_rate_card_digest=publication_digest,
            )
        except (TypeError, ValueError) as error:
            raise StructuralReferenceAdapterError(
                f"valuation declarations are invalid: {error}"
            ) from error
        result = []
        for match in matches:
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
                "unpriced_reason": match.cost_unpriced_reason or match.credit_unpriced_reason,
                "cost_unpriced_reason": match.cost_unpriced_reason,
            }
            logical_id = match.valuation_id or semantic_id(
                "valuation", [match.call_id, match.rate_card_digest or publication_digest]
            )
            result.append(
                CanonicalFact(
                    "valuation_match",
                    logical_id,
                    {key: value for key, value in values.items() if key in permitted_fields},
                    coordinates.get(match.call_id),
                )
            )
        return tuple(result)

    def _evidence(
        self,
        declarations: Mapping[str, Any],
        request: PlanRequest,
        required: Any,
        raw_facts: Sequence[tuple[str, str, Mapping[str, Any], FactCoordinates]],
    ) -> tuple[EvidenceReference, ...]:
        entries = _required_entries(required)
        references: list[EvidenceReference] = []
        for index, entry in enumerate(entries):
            entry = _mapping(entry, f"required_evidence[{index}]")
            role = entry.get("role")
            kind = entry.get("selector_kind", entry.get("kind"))
            selector = entry.get("selector")
            if (
                not isinstance(role, str)
                or not role
                or not isinstance(kind, str)
                or kind not in _SELECTOR_KINDS
            ):
                raise StructuralReferenceAdapterError("evidence role or selector kind is invalid")
            if kind == "window":
                window = self._window(request, role)
                request_digest = _request_digest(request)
                derived_logical_id = semantic_id(
                    "window",
                    [
                        request_digest,
                        role,
                        window["start_us"],
                        window["end_us"],
                        window["timezone"],
                    ],
                )
                expected_selector = f"{_selector_prefix(kind)}:{derived_logical_id}"
                if selector is not None and selector != expected_selector:
                    raise StructuralReferenceAdapterError(
                        f"{role} window selector does not match its request identity"
                    )
                supplied_logical_id = entry.get("logical_id")
                if supplied_logical_id is not None and supplied_logical_id != derived_logical_id:
                    raise StructuralReferenceAdapterError(
                        f"{role} window logical ID does not match its request identity"
                    )
                selector = expected_selector
                logical_id = derived_logical_id
                provenance: Mapping[str, Any] = {
                    "end_us": window["end_us"],
                    "parameter_role": role,
                    "request_digest": request_digest,
                    "start_us": window["start_us"],
                    "timezone": window["timezone"],
                }
            else:
                if not isinstance(selector, str):
                    raise StructuralReferenceAdapterError(f"{role} has no exact selector")
                prefix, selector_logical_id = _selector_parts(selector)
                selected_logical_id = entry.get("logical_id", selector_logical_id)
                if not isinstance(selected_logical_id, str) or not selected_logical_id:
                    raise StructuralReferenceAdapterError(f"{role} has no logical selector")
                if prefix != _selector_prefix(kind):
                    raise StructuralReferenceAdapterError(
                        f"{role} selector prefix does not match {kind}"
                    )
                if kind == "rate_card":
                    selected_digest = self._selected_frontier_digest(declarations)
                    if (
                        selector_logical_id != selected_digest
                        or selected_logical_id != selected_digest
                    ):
                        raise StructuralReferenceAdapterError(
                            f"{role} rate-card selector and logical ID must equal "
                            "the selected publication frontier digest"
                        )
                    logical_id = selected_digest
                else:
                    logical_id = selected_logical_id
                if kind != "rate_card" and logical_id != selector_logical_id:
                    raise StructuralReferenceAdapterError(
                        f"{role} selector does not identify its selected entity"
                    )
                provenance_kind, provenance = self._provenance(
                    declarations, kind, logical_id, raw_facts
                )
                if kind == "rate_card" and _selector_parts(selector)[1] != provenance.get("digest"):
                    raise StructuralReferenceAdapterError(
                        f"{role} rate-card selector does not identify its revision"
                    )
                references.append(
                    EvidenceReference(role, kind, selector, logical_id, provenance_kind, provenance)
                )
                continue
            references.append(
                EvidenceReference(
                    role, kind, selector, logical_id, "request_derivation", provenance
                )
            )
        self._validate_evidence(entries, references, declarations)
        return tuple(references)

    @staticmethod
    def _window(request: PlanRequest, role: str) -> Mapping[str, Any]:
        if role not in request.parameters:
            raise StructuralReferenceAdapterError(f"{role} has no typed request window")
        value = request.parameters[role]
        if not isinstance(value, Mapping):
            raise StructuralReferenceAdapterError(f"{role} has no typed request window")
        start = _required_integer(value.get("start_us"), f"{role}.start_us")
        end = _required_integer(value.get("end_us"), f"{role}.end_us")
        timezone = value.get("timezone", "UTC")
        if not isinstance(timezone, str) or not timezone or end < start:
            raise StructuralReferenceAdapterError(f"{role} has an invalid request window")
        return {"start_us": start, "end_us": end, "timezone": timezone}

    def _provenance(
        self,
        declarations: Mapping[str, Any],
        kind: str,
        logical_id: str,
        raw_facts: Sequence[tuple[str, str, Mapping[str, Any], FactCoordinates]],
    ) -> tuple[str, Mapping[str, Any]]:
        self._require_owner(kind)
        entities = declarations["selector_entities"]
        if not isinstance(entities, Mapping) or logical_id not in entities.get(kind, ()):
            raise StructuralReferenceAdapterError(
                f"selector has no scenario-owned entity: {logical_id}"
            )
        rule = self._owner_rules[kind]
        provenance_kind = rule.get("provenance_kind")
        if not isinstance(provenance_kind, str):
            raise StructuralReferenceAdapterError(f"owner rule is malformed for {kind}")
        if provenance_kind == "source_occurrence":
            provenance = self._source_occurrence_provenance(
                declarations, kind, logical_id, raw_facts
            )
        elif provenance_kind == "configured_artifact":
            provenance = self._rate_card_provenance(declarations, logical_id)
        elif provenance_kind == "publication_commit":
            provenance = self._publication_provenance(raw_facts, logical_id)
        elif provenance_kind == "derived_boundary_pair":
            provenance = self._boundary_provenance(declarations, logical_id)
        elif provenance_kind == "source_inventory":
            manifestations = _mapping(
                declarations["source_manifestations"], "source_manifestations"
            )
            provenance = _mapping(
                manifestations.get(logical_id), f"source_manifestations.{logical_id}"
            )
        else:
            raise StructuralReferenceAdapterError(
                f"unsupported owner provenance: {provenance_kind}"
            )
        required = rule.get("required_provenance_fields", ())
        if not isinstance(required, Sequence) or any(
            field not in provenance or provenance[field] in (None, "", [], {}) for field in required
        ):
            raise StructuralReferenceAdapterError(f"{kind} provenance is incomplete")
        return provenance_kind, provenance

    def _require_owner(self, kind: str) -> None:
        if kind not in self._owner_rules:
            raise StructuralReferenceAdapterError(f"selector owner is missing for {kind}")

    @staticmethod
    def _source_occurrence_provenance(
        declarations: Mapping[str, Any],
        kind: str,
        logical_id: str,
        raw_facts: Sequence[tuple[str, str, Mapping[str, Any], FactCoordinates]],
    ) -> Mapping[str, Any]:
        if kind == "model_profile":
            calls = [
                call_id
                for relation, call_id, values, _coordinates_value in raw_facts
                if relation == "canonical_call" and values.get("model_profile_id") == logical_id
            ]
            occurrences_by_id = _mapping(declarations["occurrences"], "occurrences")
            representative: list[Mapping[str, Any]] = []
            for call_id in sorted(calls):
                call_occurrences = occurrences_by_id.get(call_id)
                if (
                    not isinstance(call_occurrences, Sequence)
                    or isinstance(call_occurrences, (str, bytes))
                    or not call_occurrences
                    or any(not isinstance(item, Mapping) or not item for item in call_occurrences)
                ):
                    raise StructuralReferenceAdapterError(
                        f"{logical_id} has no representative call occurrence"
                    )
                representative.extend(
                    _ordered_occurrences(
                        call_occurrences,
                        f"{logical_id} representative call",
                    )
                )
            profile = next(
                (
                    values
                    for relation, fact_id, values, _coordinates_value in raw_facts
                    if relation == "model_profile" and fact_id == logical_id
                ),
                None,
            )
            if not representative:
                raise StructuralReferenceAdapterError(
                    f"{logical_id} has no representative call occurrence"
                )
            profile_tuple = {
                "model": profile.get("model") if profile else None,
                "reasoning_effort": profile.get("effort", profile.get("reasoning_effort"))
                if profile
                else None,
                "service_tier": profile.get("tier", profile.get("service_tier"))
                if profile
                else None,
            }
            if any(value in (None, "") for value in profile_tuple.values()):
                raise StructuralReferenceAdapterError(
                    f"{logical_id} has incomplete profile provenance"
                )
            return {
                "profile_tuple": profile_tuple,
                "representative_call_selectors": [f"call:{call_id}" for call_id in sorted(calls)],
                "representative_call_occurrences": _ordered_occurrences(
                    representative,
                    f"{logical_id} representative calls",
                ),
            }
        occurrences = _mapping(declarations["occurrences"], "occurrences").get(logical_id)
        if (
            not isinstance(occurrences, Sequence)
            or isinstance(occurrences, (str, bytes))
            or not occurrences
        ):
            raise StructuralReferenceAdapterError(f"{logical_id} has no source occurrence")
        if any(not isinstance(item, Mapping) or not item for item in occurrences):
            raise StructuralReferenceAdapterError(
                f"{logical_id} has invalid source occurrence provenance"
            )
        return {
            "occurrences": _ordered_occurrences(
                occurrences,
                logical_id,
            )
        }

    @staticmethod
    def _selected_frontier_digest(declarations: Mapping[str, Any]) -> str:
        digest = declarations.get("publication_rate_card_digest")
        frontier = declarations.get("rate_card_frontier")
        if not isinstance(frontier, Mapping):
            raise StructuralReferenceAdapterError("rate card evidence has no frontier")
        if not isinstance(digest, str) or not digest:
            raise StructuralReferenceAdapterError(
                "rate card evidence has no selected publication digest"
            )
        if frontier.get("head_digest") != digest:
            raise StructuralReferenceAdapterError(
                "rate card evidence does not match the selected publication frontier"
            )
        return digest

    @classmethod
    def _rate_card_provenance(
        cls, declarations: Mapping[str, Any], logical_id: str
    ) -> Mapping[str, Any]:
        selected_digest = cls._selected_frontier_digest(declarations)
        if logical_id != selected_digest:
            raise StructuralReferenceAdapterError(
                "rate card logical ID must equal the selected publication frontier digest"
            )
        frontier = _mapping(declarations["rate_card_frontier"], "rate_card_frontier")
        revisions = frontier.get("revisions")
        if not isinstance(revisions, Sequence) or isinstance(revisions, (str, bytes)):
            raise StructuralReferenceAdapterError("rate card frontier revisions are malformed")
        matches = [
            revision
            for revision in revisions
            if isinstance(revision, Mapping) and revision.get("digest") == selected_digest
        ]
        if len(matches) != 1:
            raise StructuralReferenceAdapterError(
                "selected publication rate-card digest is not uniquely captured in the frontier"
            )
        revision = matches[0]
        return {
            "digest": revision.get("digest"),
            "fetched_at_us": revision.get("fetched_at_us"),
            "source_name": revision.get("source_name"),
            "validation_status": revision.get("validation_status"),
        }

    @staticmethod
    def _publication_provenance(
        raw_facts: Sequence[tuple[str, str, Mapping[str, Any], FactCoordinates]], logical_id: str
    ) -> Mapping[str, Any]:
        for relation, fact_id, values, _coordinates_value in raw_facts:
            if relation == "publication" and fact_id == logical_id:
                return {
                    "artifact_manifest_sha256": values.get("artifact_manifest_sha256"),
                    "committed_at_us": values.get("committed_at_us"),
                    "operation_id": values.get("operation_id"),
                }
        raise StructuralReferenceAdapterError(
            f"publication is not a scenario-owned fact: {logical_id}"
        )

    @staticmethod
    def _boundary_provenance(declarations: Mapping[str, Any], logical_id: str) -> Mapping[str, Any]:
        entities = _mapping(declarations["selector_entities"], "selector_entities")
        observations = entities.get("allowance_observation")
        if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
            raise StructuralReferenceAdapterError("allowance observation entities are malformed")
        intervals = declarations.get("allowance_intervals")
        if not isinstance(intervals, Mapping):
            raise StructuralReferenceAdapterError("allowance interval boundary mapping is missing")
        interval = intervals.get(logical_id)
        if not isinstance(interval, Mapping):
            raise StructuralReferenceAdapterError(
                f"allowance interval has no boundary mapping: {logical_id}"
            )
        start = interval.get("start_observation_id")
        end = interval.get("end_observation_id")
        if (
            not isinstance(start, str)
            or not start
            or not isinstance(end, str)
            or not end
            or start == end
            or start not in observations
            or end not in observations
        ):
            raise StructuralReferenceAdapterError(
                f"allowance interval has malformed or nonexistent boundaries: {logical_id}"
            )
        occurrences = _mapping(declarations["occurrences"], "occurrences")

        def boundary_occurrences(observation_id: str) -> list[Mapping[str, Any]]:
            values = occurrences.get(observation_id)
            if (
                not isinstance(values, Sequence)
                or isinstance(values, (str, bytes))
                or not values
                or any(not isinstance(item, Mapping) or not item for item in values)
            ):
                raise StructuralReferenceAdapterError(
                    f"allowance interval boundary has no real occurrences: {observation_id}"
                )
            return _ordered_occurrences(values, observation_id)

        start_occurrences = boundary_occurrences(start)
        end_occurrences = boundary_occurrences(end)
        return {
            "compatibility_version": "allowance-compatibility-v1",
            "end_observation_selector": f"allowance-observation:{end}",
            "end_occurrences": end_occurrences,
            "start_observation_selector": f"allowance-observation:{start}",
            "start_occurrences": start_occurrences,
        }

    def _validate_evidence(
        self,
        entries: Sequence[Mapping[str, Any]],
        references: Sequence[EvidenceReference],
        declarations: Mapping[str, Any],
    ) -> None:
        expected: list[tuple[str, str, str]] = []
        for entry in entries:
            role = entry.get("role")
            kind = entry.get("selector_kind", entry.get("kind"))
            selector = entry.get("selector")
            if kind == "window" and selector is None:
                selector = next(item.selector for item in references if item.role == role)
            if (
                not isinstance(role, str)
                or not isinstance(kind, str)
                or not isinstance(selector, str)
            ):
                raise StructuralReferenceAdapterError("required evidence triple is malformed")
            expected.append((role, kind, selector))
        actual = [(item.role, item.selector_kind, item.selector) for item in references]
        if expected != actual:
            raise StructuralReferenceAdapterError(
                "required and materialized evidence selections differ"
            )
        for reference in references:
            if reference.selector_kind != "window":
                entities = _mapping(declarations["selector_entities"], "selector_entities")
                if reference.logical_id not in entities.get(reference.selector_kind, ()):
                    raise StructuralReferenceAdapterError(
                        f"{reference.role} references no scenario-owned entity"
                    )


__all__ = [
    "AdapterMaterialization",
    "EvidenceReference",
    "StructuralReferenceAdapterError",
    "StructuralReferenceFactAdapter",
]
