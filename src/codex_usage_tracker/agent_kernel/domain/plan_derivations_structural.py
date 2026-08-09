"""Pure structural, delegation, operations, and review plan derivations."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FormulaInvocation,
    PlanMaterialization,
    PlanOperandContractError,
    PlanRequest,
    _call,
    _complete_order,
    _group,
    _scoped,
    _sum,
    _uses,
)


def _value(fact: CanonicalFact, name: str) -> Any:
    if name not in fact.values:
        raise PlanOperandContractError(f"{fact.relation} is missing {name}")
    return fact.values[name]


def _order_key(fact: CanonicalFact) -> tuple[Any, ...]:
    if fact.coordinates is None:
        raise PlanOperandContractError("complete event coordinates are required")
    return fact.coordinates.key(fact.logical_id)


def _rows(
    bundle: Mapping[str, list[CanonicalFact]], relation: str, request: PlanRequest
) -> list[CanonicalFact]:
    return _scoped(bundle.get(relation, []), request)


_TOKEN_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)
_CONTEXT_WINDOW_MASK = 1 << 4
_TOOL_LIFECYCLES = frozenset({"succeeded", "failed", "pending", "running", "open"})
_TERMINAL_TOOL_LIFECYCLES = frozenset({"succeeded", "failed"})


def _stable_id(fact: CanonicalFact, field: str, relation: str | None = None) -> str:
    value = _value(fact, field)
    if not isinstance(value, str) or not value:
        raise PlanOperandContractError(
            f"{fact.relation if relation is None else relation} requires stable {field}"
        )
    return value


def _validate_unique_ids(
    facts: list[CanonicalFact], field: str, relation: str | None = None
) -> dict[str, CanonicalFact]:
    result: dict[str, CanonicalFact] = {}
    for fact in facts:
        stable_id = _stable_id(fact, field, relation)
        if stable_id in result:
            raise PlanOperandContractError(
                f"duplicate {relation or fact.relation} stable ID: {stable_id}"
            )
        result[stable_id] = fact
    return result


def _exact_nonnegative(value: Any, label: str) -> int | Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise PlanOperandContractError(f"{label} must be an exact number or null")
    if isinstance(value, Decimal) and not value.is_finite():
        raise PlanOperandContractError(f"{label} must be finite")
    if value < 0:
        raise PlanOperandContractError(f"{label} must be non-negative")
    return value


def _normalized_sum(values: list[int | Decimal]) -> int | Decimal:
    total = sum(values, Decimal(0))
    if isinstance(total, Decimal) and total == total.to_integral_value():
        return int(total)
    return total


def _token_sum(
    facts: list[CanonicalFact], fields: tuple[str, ...] = _TOKEN_FIELDS
) -> dict[str, int | Decimal | None]:
    totals: dict[str, int | Decimal | None] = {}
    for field in fields:
        values: list[int | Decimal] = []
        missing = False
        for fact in facts:
            if field not in fact.values:
                missing = True
                continue
            value = _exact_nonnegative(fact.values[field], field)
            if value is None:
                missing = True
            else:
                values.append(value)
        totals[field] = None if missing else _normalized_sum(values)
    return totals


def _token_total(
    facts: list[CanonicalFact], fields: tuple[str, ...] = _TOKEN_FIELDS
) -> int | Decimal | None:
    totals = _token_sum(facts, fields)
    exact_values: list[int | Decimal] = []
    for field in fields:
        value = totals[field]
        if value is None:
            return None
        exact_values.append(value)
    return _normalized_sum(exact_values)


def _coordinate_key(
    event_at_us: Any,
    source_rank: Any,
    source_order: Any,
    event_kind_order: Any,
    logical_id: str,
    transition_rank: Any,
    label: str,
) -> tuple[Any, ...]:
    if event_at_us is not None and (
        isinstance(event_at_us, bool) or not isinstance(event_at_us, int)
    ):
        raise PlanOperandContractError(f"{label} event_at_us must be an integer or null")
    ranks = (source_rank, source_order, event_kind_order, transition_rank)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in ranks):
        raise PlanOperandContractError(f"{label} coordinate order is malformed")
    if not isinstance(logical_id, str) or not logical_id:
        raise PlanOperandContractError(f"{label} logical_id is malformed")
    return (
        event_at_us is None,
        event_at_us if event_at_us is not None else 0,
        source_rank,
        source_order,
        event_kind_order,
        logical_id,
        transition_rank,
    )


def _fact_coordinate(fact: CanonicalFact, stable_id_field: str, label: str) -> tuple[Any, ...]:
    coordinate = fact.coordinates
    if coordinate is None:
        raise PlanOperandContractError(f"{label} coordinate is incomplete")
    stable_id = _stable_id(fact, stable_id_field)
    return _coordinate_key(
        coordinate.event_at_us,
        coordinate.source_rank,
        coordinate.source_order,
        coordinate.event_kind_order,
        stable_id,
        coordinate.transition_rank,
        label,
    )


def _tool_coordinate(fact: CanonicalFact, prefix: str, *, required: bool) -> tuple[Any, ...] | None:
    stable_id = _stable_id(fact, "tool_id")
    fields = (
        f"{prefix}_at_us",
        f"{prefix}_source_rank",
        f"{prefix}_source_order",
        f"{prefix}_event_kind_order",
        f"{prefix}_transition_rank",
    )
    present = [field in fact.values for field in fields]
    if not any(present):
        if required:
            raise PlanOperandContractError(f"incomplete {prefix} coordinate")
        return None
    if not all(present):
        raise PlanOperandContractError(f"incomplete {prefix} coordinate")
    if fact.values[fields[0]] is None:
        raise PlanOperandContractError(f"tool {prefix} event_at_us must not be null")
    return _coordinate_key(
        fact.values[fields[0]],
        fact.values[fields[1]],
        fact.values[fields[2]],
        fact.values[fields[3]],
        stable_id,
        fact.values[fields[4]],
        f"tool {prefix}",
    )


def _window_contains(request: PlanRequest, coordinate: tuple[Any, ...]) -> bool:
    window = request.parameters.get("window")
    if not isinstance(window, Mapping):
        raise PlanOperandContractError("window must be an object")
    start, end = window.get("start_us"), window.get("end_us")
    event_at_us = coordinate[1] if not coordinate[0] else None
    return event_at_us is not None and start <= event_at_us < end


def _side_facts(
    facts: list[CanonicalFact], session_id: str, session_field: str = "session_id"
) -> list[CanonicalFact]:
    return [fact for fact in facts if _value(fact, session_field) == session_id]


def _tokens(facts: list[CanonicalFact]) -> Any:
    values = (
        _sum(facts, "uncached_input_tokens"),
        _sum(facts, "cached_input_tokens"),
        _sum(facts, "output_tokens"),
    )
    if any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), 0)


def _token_records(facts: list[CanonicalFact]) -> list[dict[str, Any]]:
    return [
        {
            name: _value(fact, name)
            for name in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
        }
        for fact in facts
    ]


def _bound_call(
    use: Mapping[str, Any], operands: Mapping[str, Any], field: str
) -> FormulaInvocation:
    call = _call(use, operands)
    return FormulaInvocation(
        call.use_id,
        call.formula_id,
        call.operands,
        MappingProxyType({field: "$"}),
        call.internal_only,
        call.consume_as,
    )


def _derive_turn_completion_efficiency_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls, turns = _rows(bundle, "canonical_call", request), _rows(bundle, "turn", request)
    by_session: dict[str, list[CanonicalFact]] = defaultdict(list)
    for call in calls:
        by_session[_value(call, "session_id")].append(call)
    use = _uses(plan)
    groups = []
    for session_id, session_calls in by_session.items():
        session_turns = [turn for turn in turns if _value(turn, "session_id") == session_id]
        completed = [turn for turn in session_turns if _value(turn, "lifecycle") == "completed"]
        total = _tokens(session_calls)
        groups.append(
            _group(
                {"session_id": session_id},
                {
                    "calls": len(session_calls),
                    "turns": len(session_turns),
                    "completion_state": "completed"
                    if session_turns and len(completed) == len(session_turns)
                    else "incomplete",
                },
                [
                    _call(
                        use["completion_cohort_ratio_v1"],
                        {"numerator": total, "denominator": len(completed)},
                    ),
                    _call(use["total_tokens_v1"], {"records": _token_records(session_calls)}),
                ],
                (-len(session_calls), session_id),
            )
        )
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _derive_first_action_mutation_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    session_selector = request.parameters.get("session_selector")

    def selected(relation: str) -> list[CanonicalFact]:
        # Tool membership is governed by its explicit start coordinate.  The
        # generic fact coordinate may represent a terminal/occurrence anchor,
        # so applying _scoped before reading start_at_us can drop a valid
        # action or admit an out-of-window one.
        facts = (
            list(bundle.get(relation, []))
            if relation == "tool_invocation"
            else _rows(bundle, relation, request)
        )
        selected_facts = []
        for fact in facts:
            fact_session_id = _stable_id(fact, "session_id")
            if session_selector is None or fact_session_id == session_selector:
                selected_facts.append(fact)
        return selected_facts

    calls = selected("canonical_call")
    tools = selected("tool_invocation")
    changes = selected("state_change")
    call_ids = _validate_unique_ids(calls, "call_id")
    for fact in calls:
        _stable_id(fact, "session_id")
        _stable_id(fact, "turn_id")
        _fact_coordinate(fact, "call_id", "canonical call")

    _validate_unique_ids(tools, "tool_id")
    tool_boundaries: list[tuple[tuple[Any, ...], str, str]] = []
    for fact in tools:
        _stable_id(fact, "session_id")
        start = _tool_coordinate(fact, "start", required=True)
        assert start is not None
        lifecycle = _value(fact, "lifecycle")
        if lifecycle not in _TOOL_LIFECYCLES:
            raise PlanOperandContractError("malformed tool lifecycle")
        tool_id = _stable_id(fact, "tool_id")
        if _window_contains(request, start):
            tool_boundaries.append((start, "tool_start", tool_id))
        terminal = _tool_coordinate(
            fact, "terminal", required=lifecycle in _TERMINAL_TOOL_LIFECYCLES
        )
        if terminal is not None:
            if start is None:
                raise PlanOperandContractError("terminal without start")
            if terminal < start:
                raise PlanOperandContractError("terminal coordinate precedes start")
            if lifecycle not in _TERMINAL_TOOL_LIFECYCLES:
                raise PlanOperandContractError("malformed terminal lifecycle")
            if lifecycle == "succeeded" and _window_contains(request, terminal):
                tool_boundaries.append(
                    (terminal, "tool_terminal_succeeded", tool_id)
                )

    _validate_unique_ids(changes, "state_change_id")
    change_boundaries: list[tuple[tuple[Any, ...], str, str]] = []
    for fact in changes:
        _stable_id(fact, "session_id")
        mutation_kind = _value(fact, "mutation_kind")
        if not isinstance(mutation_kind, str) or not mutation_kind:
            raise PlanOperandContractError("malformed state-change mutation kind")
        coordinate = _fact_coordinate(fact, "state_change_id", "state change")
        change_boundaries.append((coordinate, "state_change", _stable_id(fact, "state_change_id")))

    call_coordinates = [
        (_fact_coordinate(fact, "call_id", "canonical call"), fact) for fact in call_ids.values()
    ]

    def boundary_records(
        candidates: list[tuple[tuple[Any, ...], str, str]], kind: str
    ) -> list[dict[str, Any]]:
        records = []
        for coordinate, candidate_kind, logical_id in sorted(candidates):
            if candidate_kind != kind:
                continue
            prior = [
                fact for call_coordinate, fact in call_coordinates if call_coordinate < coordinate
            ]
            records.append(
                {
                    "kind": kind,
                    "logical_id": logical_id,
                    "tokens": _token_total(prior),
                }
            )
        return records

    use = _uses(plan)["first_boundary_v1"]
    formula_calls = [
        _bound_call(
            use, {"boundary_kind": kind, "records": boundary_records(candidates, kind)}, field
        )
        for candidates, kind, field in (
            (tool_boundaries, "tool_start", "first_action_tokens"),
            (change_boundaries, "state_change", "first_mutation_tokens"),
            (tool_boundaries, "tool_terminal_succeeded", "first_success_tokens"),
        )
    ]
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                {"mutation_observed": bool(change_boundaries)},
                formula_calls,
                (),
            ),
        ),
    )


def _stage(fact: CanonicalFact) -> str:
    if fact.relation != "tool_invocation":
        return "other"
    operation, lifecycle = _value(fact, "semantic_operation"), _value(fact, "lifecycle")
    if lifecycle == "failed":
        return "failure"
    if operation in {"read", "search", "inspect"}:
        return "inspect"
    if operation in {"write", "edit", "execute", "test"}:
        return "attempt"
    return "other"


def _derive_retry_cycles_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    tools = _complete_order(_rows(bundle, "tool_invocation", request))
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for tool in tools:
        grouped[_value(tool, "resource_id")].append(tool)
    groups = []
    for resource_id, resource_tools in grouped.items():
        prior = None
        records = []
        for tool in resource_tools:
            stage = _stage(tool)
            if prior == "failure" and stage == "inspect":
                stage = "reinspect"
            elif prior == "reinspect" and stage == "attempt":
                stage = "retry"
            records.append({"id": tool.logical_id, "stage": stage, "resource": resource_id})
            prior = stage
        groups.append(
            _group(
                {"resource_id": resource_id},
                {"terminal_status": records[-1]["stage"]},
                [
                    _call(
                        _uses(plan)["retry_sequence_matcher_v1"],
                        {"records": records},
                    )
                ],
                _order_key(resource_tools[0]),
            )
        )
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _derive_model_effort_transitions_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = _complete_order(_rows(bundle, "canonical_call", request))
    use = _uses(plan)["consecutive_profile_transition_v1"]
    by_session: dict[str, list[CanonicalFact]] = defaultdict(list)
    for call in calls:
        by_session[_value(call, "session_id")].append(call)
    groups = []
    for rows in by_session.values():
        for previous, current in zip(rows, rows[1:], strict=False):
            previous_profile = _value(previous, "model_profile_id")
            current_profile = _value(current, "model_profile_id")
            if previous_profile == current_profile:
                continue
            records = [
                {"profile": previous_profile, "total_tokens": _tokens([previous])},
                {"profile": current_profile, "total_tokens": _tokens([current])},
            ]
            groups.append(
                _group(
                    {"transition_id": _value(current, "call_id")},
                    {
                        "previous_profile": previous_profile,
                        "current_profile": current_profile,
                    },
                    [_call(use, {"records": records})],
                    _order_key(current),
                )
            )
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _resource_signature(tool: CanonicalFact) -> tuple[Any, Any, Any]:
    return (
        _value(tool, "semantic_operation"),
        _value(tool, "resource_kind"),
        _value(tool, "write_intent"),
    )


def _derive_automation_candidates_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    tools, changes = (
        _rows(bundle, "tool_invocation", request),
        _rows(bundle, "state_change", request),
    )
    use = _uses(plan)["structural_workflow_features_v1"]
    grouped: dict[tuple[Any, Any, Any], list[CanonicalFact]] = defaultdict(list)
    for tool in tools:
        grouped[_resource_signature(tool)].append(tool)
    groups = []
    for signature, rows in grouped.items():
        resource_ids = {_value(row, "resource_id") for row in rows}
        mutations = sum(_value(change, "resource_id") in resource_ids for change in changes)
        sequences = [[row.logical_id for row in rows]]
        operands = {
            "frequency": len(rows),
            "failure_count": sum(_value(row, "lifecycle") == "failed" for row in rows),
            "mutation_count": mutations,
            "observed_sequences": len(sequences),
            "structural_features": {
                "operation": signature[0],
                "resource_kind": signature[1],
                "write_intent": signature[2],
                "sequence_count": len(sequences),
            },
        }
        groups.append(
            _group(
                {"feature_id": json.dumps(signature, separators=(",", ":"), ensure_ascii=True)},
                {"frequency": len(rows)},
                [_call(use, operands)],
                (-len(rows), *map(str, signature)),
            )
        )
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _derive_parent_subagent_usage_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls, sessions = _rows(bundle, "canonical_call", request), bundle.get("session", [])
    mode = request.parameters["family_mode"]
    if mode not in {"root", "direct_parent"}:
        raise PlanOperandContractError("family_mode must be root or direct_parent")
    children: dict[str, list[str]] = defaultdict(list)
    for session in sessions:
        parent = _value(session, "parent_session_id")
        if parent is not None:
            children[parent].append(_value(session, "session_id"))
    groups = []
    parent_ids = set(children)
    if mode == "root":
        parent_ids -= {child for child_ids in children.values() for child in child_ids}
    for parent in sorted(parent_ids):
        child_ids = children[parent]
        descendants = set(child_ids)
        if mode == "root":
            pending = list(child_ids)
            while pending:
                child = pending.pop()
                for descendant in children.get(child, []):
                    if descendant not in descendants:
                        descendants.add(descendant)
                        pending.append(descendant)
        family = set(child_ids) | {parent}
        if mode == "root":
            family |= descendants
        family_calls = [call for call in calls if _value(call, "session_id") in family]
        descendant_calls = [call for call in calls if _value(call, "session_id") in descendants]
        groups.append(
            _group(
                {"session_id": parent},
                {
                    "child_count": len(child_ids),
                    "descendant_exclusive_tokens": _tokens(descendant_calls),
                },
                [
                    _call(
                        _uses(plan)["exclusive_inclusive_scope_v1"],
                        {
                            "inclusive": _tokens(family_calls),
                            "descendant": _tokens(descendant_calls),
                        },
                    )
                ],
                (parent,),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(groups))


def _derive_delegation_cohorts_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    cohort = request.parameters["cohort"]
    if not isinstance(cohort, Mapping) or set(cohort) != {"left", "right"}:
        raise PlanOperandContractError("cohort must contain exactly left and right")
    calls, tools, changes = (
        _rows(bundle, "canonical_call", request),
        _rows(bundle, "tool_invocation", request),
        _rows(bundle, "state_change", request),
    )
    direct: dict[str, Any] = {
        "cohort_size": {},
        "model_mix": {},
        "mutation_features": {},
        "usage_features": {},
    }
    sides = {}
    for side in ("left", "right"):
        members = cohort[side]
        if not isinstance(members, (list, tuple)) or not all(
            isinstance(member, str) and member for member in members
        ):
            raise PlanOperandContractError("cohort members must be stable IDs")
        chosen_calls = [call for call in calls if _value(call, "session_id") in members]
        sides[side] = _tokens(chosen_calls)
        direct["cohort_size"][side] = len(members)
        direct["model_mix"][side] = {_value(call, "model_profile_id"): 1 for call in chosen_calls}
        direct["usage_features"][side] = {"tokens": sides[side], "calls": len(chosen_calls)}
        direct["mutation_features"][side] = {
            "state_changes": sum(_value(change, "session_id") in members for change in changes),
            "tools": sum(_value(tool, "session_id") in members for tool in tools),
        }
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {}, direct, [_call(_uses(plan)["observational_cohort_comparison_v1"], sides)], ()
            ),
        ),
    )


def _derive_data_health_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    publications = bundle.get("publication", [])
    if len(publications) != 1:
        raise PlanOperandContractError("data health requires exactly one publication head")
    publication = publications[0]
    direct = {
        name: _value(publication, name)
        for name in (
            "capabilities",
            "guaranteed_complete_from_us",
            "indexed_from_us",
            "measurements",
            "valuation_coverage",
        )
    }
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                direct,
                [
                    _call(
                        _uses(plan)["freshness_age_v1"],
                        {
                            "current": request.parameters["as_of_us"],
                            "previous": _value(publication, "observed_through_us"),
                        },
                    )
                ],
                (),
            ),
        ),
    )


def _derive_dedup_source_audit_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls, manifestations, occurrences = (
        _rows(bundle, "canonical_call", request),
        _rows(bundle, "source_manifestation", request),
        _rows(bundle, "source_occurrence", request),
    )
    call_ids = {call.logical_id for call in calls} | {_value(call, "call_id") for call in calls}
    groups = []
    for manifestation in manifestations:
        manifestation_id = _value(manifestation, "source_manifestation_id")
        manifestation_occurrences = [
            occurrence
            for occurrence in occurrences
            if _value(occurrence, "source_manifestation_id") == manifestation_id
        ]
        semantic_ids = {
            _value(occurrence, "semantic_logical_id")
            for occurrence in manifestation_occurrences
            if _value(occurrence, "semantic_logical_id") in call_ids
        }
        groups.append(
            _group(
                {"source_manifestation_id": manifestation_id},
                {
                    "canonical_basis": _value(manifestation, "canonical_basis"),
                    "manifestation_count": 1,
                },
                [
                    _call(
                        _uses(plan)["semantic_occurrence_reconciliation_v1"],
                        {
                            "manifestation_count": len(manifestation_occurrences),
                            "semantic_entity_count": len(semantic_ids),
                        },
                    )
                ],
                (-len(manifestation_occurrences), manifestation_id),
            )
        )
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _window_rows(facts: list[CanonicalFact], window: Mapping[str, Any]) -> list[CanonicalFact]:
    start, end = window.get("start_us"), window.get("end_us")
    if not isinstance(start, int) or not isinstance(end, int) or start >= end:
        raise PlanOperandContractError("review windows must be non-empty intervals")
    return [
        fact
        for fact in facts
        if fact.coordinates is not None
        and fact.coordinates.event_at_us is not None
        and start <= fact.coordinates.event_at_us < end
    ]


def _derive_weekly_review_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = bundle.get("canonical_call", [])
    current, previous = (
        _window_rows(calls, request.parameters["current_window"]),
        _window_rows(calls, request.parameters["previous_window"]),
    )
    session_totals: dict[str, Any] = defaultdict(int)
    for call in current:
        session_totals[_value(call, "session_id")] += _tokens([call])
    direct = {
        "allowance_facts": {"observations": len(bundle.get("allowance_observation", []))},
        "context_facts": {"calls": len(current)},
        "model_mix": {"profiles": sorted({_value(call, "model_profile_id") for call in current})},
        "tool_mix": {
            "tools": len(
                _window_rows(
                    bundle.get("tool_invocation", []), request.parameters["current_window"]
                )
            )
        },
    }
    uses = _uses(plan)
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                direct,
                [
                    _call(
                        uses["signed_driver_contribution_v1"],
                        {"current": _tokens(current), "previous": _tokens(previous)},
                    ),
                    _call(uses["top_share_v1"], {"values": list(session_totals.values()), "n": 1}),
                    _call(uses["total_tokens_v1"], {"records": _token_records(current)}),
                ],
                (),
            ),
        ),
    )


def _derive_investigation_candidates_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls, tools, changes = (
        _rows(bundle, "canonical_call", request),
        _rows(bundle, "tool_invocation", request),
        _rows(bundle, "state_change", request),
    )
    features = {"calls": len(calls), "tools": len(tools), "state_changes": len(changes)}
    direct = {
        "baseline": {"call_count": len(calls)},
        "coverage": {"tool_count": len(tools), "state_change_count": len(changes)},
        "representative_selectors": {
            "session_ids": sorted({_value(call, "session_id") for call in calls})
        },
    }
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                direct,
                [
                    _call(
                        _uses(plan)["investigation_feature_vector_v1"],
                        {"candidate_features": features},
                    )
                ],
                (),
            ),
        ),
    )


def _compare_window_rows(
    bundle: Mapping[str, list[CanonicalFact]], relation: str, request: PlanRequest
) -> list[CanonicalFact]:
    return (
        _rows(bundle, relation, request)
        if request.parameters.get("window") is not None
        else list(bundle.get(relation, []))
    )


def _require_text(fact: CanonicalFact, field: str) -> str:
    value = _value(fact, field)
    if not isinstance(value, str) or not value:
        raise PlanOperandContractError(f"{fact.relation} {field} is malformed")
    return value


def _validate_session_hierarchy(
    sessions: list[CanonicalFact],
) -> tuple[dict[str, CanonicalFact], dict[str, tuple[str, ...] | None]]:
    by_id = _validate_unique_ids(sessions, "session_id", "session")
    parent_by_id, parent_field_present, hierarchy_complete = _session_hierarchy_maps(by_id)
    _validate_parent_edges(by_id, parent_by_id, parent_field_present)
    descendants: dict[str, tuple[str, ...] | None] = {}
    for session_id in by_id:
        if (
            _validated_hierarchy_chain(
                session_id,
                by_id,
                parent_by_id,
                parent_field_present,
                hierarchy_complete,
            )
            is None
        ):
            descendants[session_id] = None
            continue
        relationships = [
            _is_descendant_session(
                candidate,
                session_id,
                by_id,
                parent_by_id,
                parent_field_present,
                hierarchy_complete,
            )
            for candidate in by_id
        ]
        descendants[session_id] = (
            None
            if any(value is None for value in relationships)
            else tuple(
                candidate for candidate, value in zip(by_id, relationships, strict=True) if value
            )
        )
    return by_id, descendants


def _session_hierarchy_maps(
    by_id: Mapping[str, CanonicalFact],
) -> tuple[dict[str, str | None], dict[str, bool], dict[str, bool]]:
    parent_by_id: dict[str, str | None] = {}
    parent_field_present: dict[str, bool] = {}
    hierarchy_complete: dict[str, bool] = {}
    for session_id, fact in by_id.items():
        root_present = "root_session_id" in fact.values
        parent_present = "parent_session_id" in fact.values
        depth_present = "delegation_depth" in fact.values
        root = fact.values.get("root_session_id")
        parent = fact.values.get("parent_session_id")
        depth = fact.values.get("delegation_depth")
        if root_present and (not isinstance(root, str) or not root):
            raise PlanOperandContractError("session hierarchy root is malformed")
        if parent_present and parent is not None and (not isinstance(parent, str) or not parent):
            raise PlanOperandContractError("session hierarchy parent is malformed")
        if depth_present and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 0):
            raise PlanOperandContractError("session hierarchy depth is malformed")
        parent_by_id[session_id] = parent
        parent_field_present[session_id] = parent_present
        hierarchy_complete[session_id] = root_present and parent_present and depth_present
    return parent_by_id, parent_field_present, hierarchy_complete


def _validate_parent_edges(
    by_id: Mapping[str, CanonicalFact],
    parent_by_id: Mapping[str, str | None],
    parent_field_present: Mapping[str, bool],
) -> None:
    for session_id in by_id:
        seen = {session_id}
        current = session_id
        while parent_field_present[current] and parent_by_id[current] is not None:
            parent = parent_by_id[current]
            assert parent is not None
            if parent not in by_id or parent in seen:
                raise PlanOperandContractError("malformed or cyclic session hierarchy")
            seen.add(parent)
            current = parent


def _known_hierarchy_root(
    session_id: str,
    by_id: Mapping[str, CanonicalFact],
    parent_by_id: Mapping[str, str | None],
    parent_field_present: Mapping[str, bool],
) -> bool:
    fact = by_id[session_id]
    return (
        "root_session_id" in fact.values
        and "delegation_depth" in fact.values
        and fact.values["root_session_id"] == session_id
        and fact.values["delegation_depth"] == 0
        and (not parent_field_present[session_id] or parent_by_id[session_id] is None)
    )


def _validated_hierarchy_chain(
    session_id: str,
    by_id: Mapping[str, CanonicalFact],
    parent_by_id: Mapping[str, str | None],
    parent_field_present: Mapping[str, bool],
    hierarchy_complete: Mapping[str, bool],
) -> tuple[str, int] | None:
    if not hierarchy_complete[session_id]:
        return None
    current = session_id
    chain_depth = 0
    while parent_field_present[current]:
        parent = parent_by_id[current]
        if parent is None:
            break
        current = parent
        chain_depth += 1
        if not parent_field_present[current] and not _known_hierarchy_root(
            current, by_id, parent_by_id, parent_field_present
        ):
            return None
    fact = by_id[session_id]
    if (
        _value(fact, "root_session_id") != current
        or _value(fact, "delegation_depth") != chain_depth
    ):
        raise PlanOperandContractError("session hierarchy depth/root mismatch")
    return current, chain_depth


def _is_descendant_session(
    candidate: str,
    ancestor: str,
    by_id: Mapping[str, CanonicalFact],
    parent_by_id: Mapping[str, str | None],
    parent_field_present: Mapping[str, bool],
    hierarchy_complete: Mapping[str, bool],
) -> bool | None:
    if candidate == ancestor:
        return False
    if not hierarchy_complete[candidate]:
        return (
            False
            if _known_hierarchy_root(candidate, by_id, parent_by_id, parent_field_present)
            else None
        )
    current = candidate
    while parent_field_present[current]:
        parent = parent_by_id[current]
        if parent is None:
            break
        current = parent
        if current == ancestor:
            return True
        if not parent_field_present[current]:
            return (
                False
                if _known_hierarchy_root(current, by_id, parent_by_id, parent_field_present)
                else None
            )
    return False


def _context_capability(
    publications: list[CanonicalFact],
) -> bool:
    if len(publications) != 1:
        raise PlanOperandContractError("publication capability is missing or ambiguous")
    capabilities = _value(publications[0], "capabilities")
    if not isinstance(capabilities, Mapping):
        raise PlanOperandContractError("publication capabilities are malformed")
    values = []
    for capability_id in ("structural_context", "context_components"):
        if capability_id not in capabilities:
            continue
        capability = capabilities[capability_id]
        if not isinstance(capability, bool):
            raise PlanOperandContractError("publication capability is malformed")
        values.append(capability)
    if not values or any(value != values[0] for value in values):
        raise PlanOperandContractError("publication structural-context capability is missing")
    return values[0]


def _context_features(
    calls: list[CanonicalFact], capability_available: bool
) -> dict[str, Any] | None:
    observed: list[int] = []
    availability: list[bool] = []
    for call in calls:
        if "context_window_tokens" not in call.values or "measurement_mask" not in call.values:
            raise PlanOperandContractError("context measurement authority is missing")
        mask = call.values["measurement_mask"]
        if isinstance(mask, bool) or not isinstance(mask, int) or mask < 0:
            raise PlanOperandContractError("context measurement mask is malformed")
        value = _exact_nonnegative(call.values["context_window_tokens"], "context_window_tokens")
        available = bool(mask & _CONTEXT_WINDOW_MASK)
        availability.append(available)
        if available != (value is not None):
            raise PlanOperandContractError("context-window measurement availability disagrees")
        if not available:
            continue
        if not isinstance(value, int):
            raise PlanOperandContractError("context_window_tokens must be an integer")
        observed.append(value)
    if not capability_available:
        return None
    if not calls:
        return {"observed_call_count": 0, "distinct_context_window_tokens": []}
    if not any(availability):
        return None
    if not all(availability):
        raise PlanOperandContractError("mixed context-window measurement is unavailable")
    return {
        "observed_call_count": len(calls),
        "distinct_context_window_tokens": sorted(set(observed)),
    }


def _count_by_kind(
    facts: list[CanonicalFact], id_field: str, kind_field: str, output_kind: str
) -> dict[str, Any]:
    _validate_unique_ids(facts, id_field)
    counts: dict[str, int] = {}
    for fact in facts:
        kind = _require_text(fact, kind_field)
        counts[kind] = counts.get(kind, 0) + 1
    return {"count": len(facts), output_kind: dict(sorted(counts.items()))}


def _tool_metrics(tools: list[CanonicalFact]) -> dict[str, int]:
    _validate_unique_ids(tools, "tool_id", "tool_invocation")
    counts = {
        "invocation_count": len(tools),
        "succeeded_count": 0,
        "failed_count": 0,
        "open_count": 0,
    }
    for tool in tools:
        lifecycle = _require_text(tool, "lifecycle")
        if lifecycle not in _TOOL_LIFECYCLES:
            raise PlanOperandContractError("unknown tool lifecycle")
        if lifecycle == "succeeded":
            counts["succeeded_count"] += 1
        elif lifecycle == "failed":
            counts["failed_count"] += 1
        else:
            counts["open_count"] += 1
    return counts


def _resource_metrics(
    tools: list[CanonicalFact], changes: list[CanonicalFact], resources: list[CanonicalFact]
) -> dict[str, Any]:
    kinds = _resource_kinds(resources)
    linked = _linked_resource_ids(tools, changes)
    if linked - set(kinds):
        raise PlanOperandContractError("dangling resource join")
    by_kind: dict[str, int] = {}
    for resource_id in sorted(linked):
        kind = kinds[resource_id]
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {"count": len(linked), "by_kind": dict(sorted(by_kind.items()))}


def _resource_kinds(resources: list[CanonicalFact]) -> dict[str, str]:
    resource_by_id = _validate_unique_ids(resources, "resource_id", "resource")
    kinds: dict[str, str] = {}
    for resource_id, resource in resource_by_id.items():
        kind = _require_text(resource, "resource_kind")
        if resource_id in kinds and kinds[resource_id] != kind:
            raise PlanOperandContractError("conflicting resource join")
        kinds[resource_id] = kind
    return kinds


def _linked_resource_ids(tools: list[CanonicalFact], changes: list[CanonicalFact]) -> set[str]:
    linked: set[str] = set()
    for tool in tools:
        if "resource_links" not in tool.values or "resource_id" not in tool.values:
            raise PlanOperandContractError("tool resource join is missing")
        links = tool.values["resource_links"]
        if not isinstance(links, (list, tuple)):
            raise PlanOperandContractError("tool resource_links are malformed")
        for resource_id in links:
            if not isinstance(resource_id, str) or not resource_id:
                raise PlanOperandContractError("tool resource link is malformed")
            linked.add(resource_id)
        primary = tool.values["resource_id"]
        if primary is not None:
            if not isinstance(primary, str) or not primary:
                raise PlanOperandContractError("tool resource_id is malformed")
            linked.add(primary)
    for change in changes:
        if "resource_id" not in change.values:
            raise PlanOperandContractError("state-change resource join is missing")
        resource_id = change.values["resource_id"]
        if resource_id is not None:
            if not isinstance(resource_id, str) or not resource_id:
                raise PlanOperandContractError("state-change resource_id is malformed")
            linked.add(resource_id)
    return linked


def _token_deltas(
    left_calls: list[CanonicalFact], right_calls: list[CanonicalFact]
) -> dict[str, Any]:
    left = _token_sum(left_calls)
    right = _token_sum(right_calls)
    deltas: dict[str, Any] = {}
    for field in _TOKEN_FIELDS:
        left_value, right_value = left[field], right[field]
        deltas[field] = (
            None if left_value is None or right_value is None else right_value - left_value
        )
    deltas["total_tokens"] = (
        None
        if any(deltas[field] is None for field in _TOKEN_FIELDS)
        else _normalized_sum(
            [deltas[field] for field in _TOKEN_FIELDS if deltas[field] is not None]
        )
    )
    return deltas


def _validate_compare_relations(
    request: PlanRequest,
    calls: list[CanonicalFact],
    tools: list[CanonicalFact],
    changes: list[CanonicalFact],
    turns: list[CanonicalFact],
) -> None:
    windowed = request.parameters.get("window") is not None
    for fact in calls:
        _stable_id(fact, "session_id")
        _stable_id(fact, "turn_id")
        if windowed:
            _fact_coordinate(fact, "call_id", "canonical call")
        _token_sum([fact])
    for fact in tools:
        _stable_id(fact, "session_id")
        if windowed:
            _fact_coordinate(fact, "tool_id", "tool invocation")
        if _require_text(fact, "lifecycle") not in _TOOL_LIFECYCLES:
            raise PlanOperandContractError("unknown tool lifecycle")
        if "resource_links" not in fact.values or "resource_id" not in fact.values:
            raise PlanOperandContractError("tool resource join is missing")
    for fact in changes:
        _stable_id(fact, "session_id")
        if windowed:
            _fact_coordinate(fact, "state_change_id", "state change")
        _require_text(fact, "mutation_kind")
    for fact in turns:
        _stable_id(fact, "session_id")
        if windowed:
            _fact_coordinate(fact, "turn_id", "turn")


def _compare_side_values(
    session_id: str,
    session_by_id: Mapping[str, CanonicalFact],
    descendants: Mapping[str, tuple[str, ...] | None],
    call_by_id: Mapping[str, CanonicalFact],
    tool_by_id: Mapping[str, CanonicalFact],
    change_by_id: Mapping[str, CanonicalFact],
    turn_by_id: Mapping[str, CanonicalFact],
    resources: list[CanonicalFact],
    capability_available: bool,
) -> tuple[dict[str, Any], list[CanonicalFact]]:
    side_calls = _side_facts(list(call_by_id.values()), session_id)
    side_tools = _side_facts(list(tool_by_id.values()), session_id)
    side_changes = _side_facts(list(change_by_id.values()), session_id)
    side_turns = _side_facts(list(turn_by_id.values()), session_id)
    descendant_ids = descendants[session_id]
    descendant_calls = (
        [
            fact
            for descendant in descendant_ids
            for fact in _side_facts(list(call_by_id.values()), descendant)
        ]
        if descendant_ids is not None
        else []
    )
    exclusive = _token_total(side_calls)
    descendant_total = _token_total(descendant_calls) if descendant_ids is not None else None
    inclusive = (
        None
        if exclusive is None or descendant_total is None
        else _normalized_sum([exclusive, descendant_total])
    )
    session = session_by_id[session_id]
    completion_basis = _value(session, "completion_basis")
    if completion_basis is not None and (
        not isinstance(completion_basis, str) or not completion_basis
    ):
        raise PlanOperandContractError("session completion_basis is malformed")
    values = {
        "completion_state": {
            "lifecycle_state": _require_text(session, "lifecycle_state"),
            "completion_basis": completion_basis,
        },
        "context_features": _context_features(side_calls, capability_available),
        "delegation_metrics": {
            "exclusive_tokens": exclusive,
            "descendant_tokens": descendant_total,
            "inclusive_tokens": inclusive,
        },
        "resource_metrics": _resource_metrics(side_tools, side_changes, resources),
        "state_change_metrics": _count_by_kind(
            side_changes, "state_change_id", "mutation_kind", "by_mutation_kind"
        ),
        "tool_metrics": _tool_metrics(side_tools),
        "turn_call_counts": {
            "turn_count": len(side_turns),
            "call_count": len(side_calls),
        },
    }
    return values, side_calls


def _compare_direct_values(
    left_values: Mapping[str, Any],
    right_values: Mapping[str, Any],
    left_calls: list[CanonicalFact],
    right_calls: list[CanonicalFact],
) -> dict[str, Any]:
    paired_fields = (
        "completion_state",
        "context_features",
        "delegation_metrics",
        "resource_metrics",
        "state_change_metrics",
        "tool_metrics",
        "turn_call_counts",
    )
    direct = {
        field: {"left": left_values[field], "right": right_values[field]} for field in paired_fields
    }
    direct["token_deltas"] = _token_deltas(left_calls, right_calls)
    return direct


def _compare_formula_calls(
    uses: Mapping[str, Any],
    left_values: Mapping[str, Any],
    left_calls: list[CanonicalFact],
    right_calls: list[CanonicalFact],
) -> list[FormulaInvocation]:
    delegation = left_values["delegation_metrics"]
    return [
        _call(
            uses["exclusive_inclusive_scope_v1"],
            {
                "inclusive": delegation["inclusive_tokens"]
                if delegation["inclusive_tokens"] is not None
                else 0,
                "descendant": delegation["descendant_tokens"]
                if delegation["descendant_tokens"] is not None
                else 0,
            },
        ),
        _call(
            uses["side_by_side_delta_v1"],
            {"current": _token_total(right_calls), "previous": _token_total(left_calls)},
        ),
        _call(
            uses["total_tokens_v1"],
            {
                "records": [
                    {
                        name: fact.values.get(name)
                        for name in (
                            "uncached_input_tokens",
                            "cached_input_tokens",
                            "output_tokens",
                        )
                    }
                    for fact in left_calls + right_calls
                ]
            },
        ),
    ]


def _derive_compare_sessions_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = _compare_window_rows(bundle, "canonical_call", request)
    tools = _compare_window_rows(bundle, "tool_invocation", request)
    changes = _compare_window_rows(bundle, "state_change", request)
    turns = _compare_window_rows(bundle, "turn", request)
    resources = list(bundle.get("resource", []))
    left, right = request.parameters["left_session"], request.parameters["right_session"]
    if not isinstance(left, str) or not isinstance(right, str) or left == right:
        raise PlanOperandContractError("comparison sessions must be distinct stable IDs")
    session_by_id, descendants = _validate_session_hierarchy(list(bundle.get("session", [])))
    if left not in session_by_id or right not in session_by_id:
        raise PlanOperandContractError("requested comparison session is unavailable")
    call_by_id = _validate_unique_ids(calls, "call_id", "canonical_call")
    tool_by_id = _validate_unique_ids(tools, "tool_id", "tool_invocation")
    change_by_id = _validate_unique_ids(changes, "state_change_id", "state_change")
    turn_by_id = _validate_unique_ids(turns, "turn_id", "turn")
    _validate_compare_relations(request, calls, tools, changes, turns)
    side_args = (
        session_by_id,
        descendants,
        call_by_id,
        tool_by_id,
        change_by_id,
        turn_by_id,
        resources,
        _context_capability(list(bundle.get("publication", []))),
    )
    left_values, left_calls = _compare_side_values(left, *side_args)
    right_values, right_calls = _compare_side_values(right, *side_args)
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                _compare_direct_values(left_values, right_values, left_calls, right_calls),
                _compare_formula_calls(_uses(plan), left_values, left_calls, right_calls),
                (),
            ),
        ),
    )


DERIVATIONS: Mapping[
    str,
    Callable[
        [Mapping[str, Any], PlanRequest, Mapping[str, list[CanonicalFact]]], PlanMaterialization
    ],
] = {
    "derive_turn_completion_efficiency_v1": _derive_turn_completion_efficiency_v1,
    "derive_first_action_mutation_v1": _derive_first_action_mutation_v1,
    "derive_retry_cycles_v1": _derive_retry_cycles_v1,
    "derive_model_effort_transitions_v1": _derive_model_effort_transitions_v1,
    "derive_automation_candidates_v1": _derive_automation_candidates_v1,
    "derive_parent_subagent_usage_v1": _derive_parent_subagent_usage_v1,
    "derive_delegation_cohorts_v1": _derive_delegation_cohorts_v1,
    "derive_data_health_v1": _derive_data_health_v1,
    "derive_dedup_source_audit_v1": _derive_dedup_source_audit_v1,
    "derive_weekly_review_v1": _derive_weekly_review_v1,
    "derive_investigation_candidates_v1": _derive_investigation_candidates_v1,
    "derive_compare_sessions_v1": _derive_compare_sessions_v1,
}
