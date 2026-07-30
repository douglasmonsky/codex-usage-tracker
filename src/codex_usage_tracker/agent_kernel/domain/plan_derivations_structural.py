"""Pure structural, delegation, operations, and review plan derivations."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping
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
    events = _complete_order(
        [
            fact
            for relation in ("canonical_call", "tool_invocation", "state_change", "turn")
            for fact in _rows(bundle, relation, request)
        ]
    )
    use = _uses(plan)["first_boundary_v1"]
    records = [
        {
            "kind": fact.relation,
            "tokens": fact.values.get("total_tokens", fact.values.get("output_tokens")),
        }
        for fact in events
    ]
    calls = [
        _bound_call(use, {"boundary_kind": kind, "records": records}, field)
        for kind, field in (
            ("tool_invocation", "first_action_tokens"),
            ("state_change", "first_mutation_tokens"),
            ("canonical_call", "first_success_tokens"),
        )
    ]
    return PlanMaterialization(
        plan["plan_id"],
        (
            _group(
                {},
                {"mutation_observed": any(fact.relation == "state_change" for fact in events)},
                calls,
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
            records.append(
                {"id": tool.logical_id, "stage": stage, "resource": resource_id}
            )
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
                {
                    "feature_id": json.dumps(
                        signature, separators=(",", ":"), ensure_ascii=True
                    )
                },
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
        descendant_calls = [
            call for call in calls if _value(call, "session_id") in descendants
        ]
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
    call_ids = {call.logical_id for call in calls} | {
        _value(call, "call_id") for call in calls
    }
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


def _derive_compare_sessions_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = bundle.get("canonical_call", [])
    left, right = request.parameters["left_session"], request.parameters["right_session"]
    if not isinstance(left, str) or not isinstance(right, str) or left == right:
        raise PlanOperandContractError("comparison sessions must be distinct stable IDs")
    left_calls, right_calls = (
        [call for call in calls if _value(call, "session_id") == left],
        [call for call in calls if _value(call, "session_id") == right],
    )
    total_left, total_right = _tokens(left_calls), _tokens(right_calls)
    direct = {
        "completion_state": {"left": "observed", "right": "observed"},
        "context_features": {"left_calls": len(left_calls), "right_calls": len(right_calls)},
        "resource_metrics": {"left": 0, "right": 0},
        "state_change_metrics": {"left": 0, "right": 0},
        "tool_metrics": {"left": 0, "right": 0},
        "turn_call_counts": {"left": len(left_calls), "right": len(right_calls)},
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
                        uses["exclusive_inclusive_scope_v1"],
                        {"inclusive": total_left, "descendant": 0},
                    ),
                    _call(
                        uses["side_by_side_delta_v1"],
                        {"current": total_right, "previous": total_left},
                    ),
                    _call(
                        uses["total_tokens_v1"],
                        {"records": _token_records(left_calls + right_calls)},
                    ),
                ],
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
