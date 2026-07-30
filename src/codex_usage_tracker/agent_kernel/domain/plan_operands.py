"""Pure, named-plan compilation from canonical facts to formula operands."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from codex_usage_tracker.agent_kernel.domain.formulas import (
    FormulaOperandError,
    evaluate_formula,
)


class PlanOperandContractError(ValueError):
    """A plan cannot be compiled without inventing semantics."""


def _assert_finite(value: Any, label: str) -> None:
    """Reject non-finite numbers recursively at every executable boundary."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise PlanOperandContractError(f"{label} must contain only finite numbers")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PlanOperandContractError(f"{label} must contain only finite numbers")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_finite(key, label)
            _assert_finite(item, label)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            _assert_finite(item, label)


@dataclass(frozen=True, slots=True)
class FactCoordinates:
    event_at_us: int | None
    source_rank: int
    source_order: int
    event_kind_order: int
    transition_rank: int = 0

    def __post_init__(self) -> None:
        _assert_finite(
            (
                self.event_at_us,
                self.source_rank,
                self.source_order,
                self.event_kind_order,
                self.transition_rank,
            ),
            "fact coordinates",
        )

    def key(self, logical_id: str) -> tuple[Any, ...]:
        return (
            self.event_at_us is None,
            self.event_at_us or 0,
            self.source_rank,
            self.source_order,
            self.event_kind_order,
            logical_id,
            self.transition_rank,
        )


def _mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise PlanOperandContractError(f"{name} must be a string-keyed mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class PlanRequest:
    plan_id: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    gates: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id:
            raise PlanOperandContractError("plan_id must be a non-empty string")
        object.__setattr__(self, "parameters", _mapping(self.parameters, "parameters"))
        object.__setattr__(self, "gates", _mapping(self.gates, "gates"))
        _assert_finite(self.parameters, "parameters")


@dataclass(frozen=True, slots=True)
class CanonicalFact:
    relation: str
    logical_id: str
    values: Mapping[str, Any]
    coordinates: FactCoordinates | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.relation, str) or not self.relation:
            raise PlanOperandContractError("relation must be a non-empty string")
        if not isinstance(self.logical_id, str) or not self.logical_id:
            raise PlanOperandContractError("logical_id must be a non-empty string")
        object.__setattr__(self, "values", _mapping(self.values, "fact values"))
        _assert_finite(self.values, "fact values")
        forbidden = {
            "answer",
            "comparison",
            "expected",
            "grade",
            "grading",
            "oracle",
            "scenario",
            "sql",
        }.intersection(self.values)
        if forbidden:
            raise PlanOperandContractError(
                f"forbidden fact values: {', '.join(sorted(forbidden))}"
            )


@dataclass(frozen=True, slots=True)
class FormulaInvocation:
    use_id: str
    formula_id: str
    operands: Mapping[str, Any]
    output_bindings: Mapping[str, str]
    internal_only: bool
    consume_as: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operands", _mapping(self.operands, "formula operands"))
        object.__setattr__(
            self,
            "output_bindings",
            _mapping(self.output_bindings, "formula output bindings"),
        )
        _assert_finite(self.operands, "formula operands")


@dataclass(frozen=True, slots=True)
class PlanGroup:
    key: tuple[tuple[str, Any], ...]
    direct_slots: Mapping[str, Any]
    formula_calls: tuple[FormulaInvocation, ...]
    order_key: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class PlanMaterialization:
    plan_id: str
    groups: tuple[PlanGroup, ...]


@dataclass(frozen=True, slots=True)
class PlanEvaluation:
    plan_id: str
    rows: tuple[Mapping[str, Any], ...]
    internal_results: tuple[Mapping[str, Any], ...] = ()

    def to_json(self) -> str:
        def normalize(value: Any) -> Any:
            _assert_finite(value, "plan evaluation")
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, Mapping):
                return {key: normalize(item) for key, item in sorted(value.items())}
            if isinstance(value, (tuple, list)):
                return [normalize(item) for item in value]
            return value

        return json.dumps(
            normalize(
                {
                    "internal_results": self.internal_results,
                    "plan_id": self.plan_id,
                    "rows": self.rows,
                }
            ),
            separators=(",", ":"),
            sort_keys=True,
        )


def _plan(contract: Mapping[str, Any], plan_id: str) -> Mapping[str, Any]:
    if contract.get("schema") != "codex-usage-tracker.plan-operand-contract.v1":
        raise PlanOperandContractError("unsupported plan operand contract")
    matches = [item for item in contract.get("plans", []) if item.get("plan_id") == plan_id]
    if len(matches) != 1:
        raise PlanOperandContractError(f"plan_id must resolve exactly once: {plan_id}")
    return matches[0]


def _validate_request(plan: Mapping[str, Any], request: PlanRequest) -> None:
    schema = plan.get("request_schema")
    if not isinstance(schema, Mapping):
        raise PlanOperandContractError("request_schema is malformed")
    required = schema.get("required", {})
    optional = schema.get("optional", {})
    if not isinstance(required, Mapping) or not isinstance(optional, Mapping):
        raise PlanOperandContractError("request parameter declarations are malformed")
    supplied = set(request.parameters)
    missing = set(required) - supplied
    unknown = supplied - set(required) - set(optional)
    if missing or unknown:
        raise PlanOperandContractError(
            f"request parameters mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    type_checks = {
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "object": lambda value: isinstance(value, Mapping),
        "string": lambda value: isinstance(value, str),
    }
    for name, value in request.parameters.items():
        declaration = required.get(name, optional.get(name))
        expected = declaration.get("type") if isinstance(declaration, Mapping) else None
        if expected not in type_checks or not type_checks[expected](value):
            raise PlanOperandContractError(f"parameter {name!r} must be {expected!r}")
    gates = plan.get("gates", [])
    if set(request.gates) != set(gates) or any(
        request.gates.get(gate) is not True for gate in gates
    ):
        raise PlanOperandContractError("all and only declared gates must be true")


def _bundle(
    plan: Mapping[str, Any], facts: Sequence[CanonicalFact]
) -> dict[str, list[CanonicalFact]]:
    if not isinstance(facts, Sequence) or not all(
        isinstance(fact, CanonicalFact) for fact in facts
    ):
        raise PlanOperandContractError("facts must be CanonicalFact values")
    manifests = {
        source["relation"]: set(source["fields"])
        for source in plan.get("permitted_sources", [])
    }
    result: dict[str, list[CanonicalFact]] = defaultdict(list)
    for fact in facts:
        if fact.relation not in manifests:
            raise PlanOperandContractError(f"relation is not permitted: {fact.relation}")
        actual = set(fact.values)
        expected = manifests[fact.relation]
        if not actual.issubset(expected):
            raise PlanOperandContractError(
                f"{fact.relation} field manifest mismatch; "
                f"unknown={sorted(actual - expected)}"
            )
        result[fact.relation].append(fact)
    return result


def _window(request: PlanRequest) -> tuple[int, int] | None:
    value = request.parameters.get("window")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PlanOperandContractError("window must be an object")
    start, end = value.get("start_us"), value.get("end_us")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start >= end
    ):
        raise PlanOperandContractError("window must be a non-empty half-open interval")
    return start, end


def _scoped(facts: Sequence[CanonicalFact], request: PlanRequest) -> list[CanonicalFact]:
    window = _window(request)
    if window is None:
        return list(facts)
    start, end = window
    scoped = []
    for fact in facts:
        if fact.coordinates is None or fact.coordinates.event_at_us is None:
            raise PlanOperandContractError("windowed facts require event coordinates")
        if start <= fact.coordinates.event_at_us < end:
            scoped.append(fact)
    return scoped


def _number(value: Any, label: str) -> int | Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise PlanOperandContractError(f"{label} must be an exact number or null")
    _assert_finite(value, label)
    return value


def _sum(facts: Sequence[CanonicalFact], field: str) -> int | Decimal | None:
    if not facts:
        return None
    values = [_number(fact.values.get(field), field) for fact in facts]
    if any(value is None for value in values):
        return None
    exact_values = [value for value in values if value is not None]
    total = sum(exact_values, Decimal(0))
    return int(total) if isinstance(total, Decimal) and total == total.to_integral_value() else total


def _call(
    use: Mapping[str, Any],
    operands: Mapping[str, Any],
    *,
    suffix: str = "0",
) -> FormulaInvocation:
    bindings = dict(use["output_bindings"])
    if suffix != "0":
        if suffix not in bindings:
            raise PlanOperandContractError(
                f"formula call suffix has no output binding: {suffix}"
            )
        bindings = {suffix: bindings[suffix]}
    return FormulaInvocation(
        use_id=f"{use['use_id']}:{suffix}",
        formula_id=use["formula_id"],
        operands=MappingProxyType(dict(operands)),
        output_bindings=MappingProxyType(bindings),
        internal_only=use["internal_only"],
        consume_as=use.get("consume_as"),
    )


def _group(
    key: Mapping[str, Any],
    direct: Mapping[str, Any],
    calls: Sequence[FormulaInvocation],
    order: Sequence[Any],
) -> PlanGroup:
    return PlanGroup(
        key=tuple(key.items()),
        direct_slots=MappingProxyType(dict(direct)),
        formula_calls=tuple(calls),
        order_key=tuple(order),
    )


def _uses(plan: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {use["formula_id"]: use for use in plan["formula_uses"]}


def _derive_current_usage(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    calls = _scoped(bundle.get("canonical_call", []), request)
    call_ids = {fact.values["call_id"] for fact in calls}
    valuations = [
        fact
        for fact in bundle.get("valuation_match", [])
        if fact.values["call_id"] in call_ids
    ]
    direct = {
        "cached_input_tokens": _sum(calls, "cached_input_tokens"),
        "calls": len(calls),
        "configured_cost_usd": _sum(valuations, "configured_cost_usd"),
        "estimated_credits": _sum(valuations, "estimated_credits"),
        "output_tokens": _sum(calls, "output_tokens"),
        "reasoning_tokens": _sum(calls, "reasoning_tokens"),
        "uncached_input_tokens": _sum(calls, "uncached_input_tokens"),
    }
    formula = _uses(plan)["total_tokens_v1"]
    invocation = _call(
        formula,
        {
            "records": [
                {
                    "uncached_input_tokens": fact.values["uncached_input_tokens"],
                    "cached_input_tokens": fact.values["cached_input_tokens"],
                    "output_tokens": fact.values["output_tokens"],
                }
                for fact in calls
            ]
        },
    )
    return PlanMaterialization(plan["plan_id"], (_group({}, direct, [invocation], ()),))


def _derive_model_effort_mix(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    calls = _scoped(bundle.get("canonical_call", []), request)
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for fact in calls:
        grouped[fact.values["model_profile_id"]].append(fact)
    totals = {
        profile: sum(
            (_sum(rows, field) or 0)
            for field in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
        )
        for profile, rows in grouped.items()
    }
    denominator = sum(totals.values(), Decimal(0))
    use = _uses(plan)["observed_share_v1"]
    groups = []
    for profile, rows in grouped.items():
        direct = {
            "cached_input_tokens": _sum(rows, "cached_input_tokens"),
            "calls": len(rows),
            "output_tokens": _sum(rows, "output_tokens"),
            "reasoning_tokens": _sum(rows, "reasoning_tokens"),
            "uncached_input_tokens": _sum(rows, "uncached_input_tokens"),
        }
        groups.append(
            _group(
                {"model_profile_id": profile},
                direct,
                [_call(use, {"numerator": totals[profile], "denominator": denominator})],
                (-totals[profile], profile),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _complete_order(facts: Sequence[CanonicalFact]) -> list[CanonicalFact]:
    if any(fact.coordinates is None for fact in facts):
        raise PlanOperandContractError("complete event coordinates are required")
    keys = [fact.coordinates.key(fact.logical_id) for fact in facts if fact.coordinates]
    if len(set(keys)) != len(keys):
        raise PlanOperandContractError("event total-order coordinates must be unique")
    return sorted(facts, key=lambda fact: fact.coordinates.key(fact.logical_id))  # type: ignore[union-attr]


def _derive_allowance_events(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    observations = {fact.logical_id: fact for fact in bundle["allowance_observation"]}
    start = observations.get(request.parameters["start_observation"])
    end = observations.get(request.parameters["end_observation"])
    if start is None or end is None or start.coordinates is None or end.coordinates is None:
        raise PlanOperandContractError("selected allowance observations are unavailable")
    start_us, end_us = start.coordinates.event_at_us, end.coordinates.event_at_us
    if start_us is None or end_us is None or start_us > end_us:
        raise PlanOperandContractError("allowance observation order is invalid")
    compatibility = start.values["compatibility_basis"]
    events = _complete_order(
        [
            fact
            for relation, facts in bundle.items()
            if relation != "allowance_observation"
            for fact in facts
            if fact.coordinates is not None
            and fact.coordinates.event_at_us is not None
            and start_us <= fact.coordinates.event_at_us < end_us
        ]
    )
    use = _uses(plan)["half_open_interval_membership_v1"]
    groups = []
    for fact in events:
        event_us = fact.coordinates.event_at_us  # type: ignore[union-attr]
        groups.append(
            _group(
                {"logical_id": fact.logical_id},
                {
                    "boundary_compatibility": compatibility,
                    "event_kind": fact.relation,
                    "event_time_us": event_us,
                },
                [
                    _call(
                        use,
                        {
                            "start_us": start_us,
                            "end_us": end_us,
                            "event_time_us": event_us,
                        },
                    )
                ],
                fact.coordinates.key(fact.logical_id),  # type: ignore[union-attr]
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(groups))


def _resource_tools(
    tools: Sequence[CanonicalFact],
) -> dict[str, list[CanonicalFact]]:
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for fact in tools:
        links = fact.values["resource_links"]
        if not isinstance(links, (tuple, list)) or not all(
            isinstance(link, str) and link for link in links
        ):
            raise PlanOperandContractError("tool resource_links must be stable IDs")
        for link in links:
            grouped[link].append(fact)
    return grouped


def _derive_repeated_resources(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    tools = _complete_order(_scoped(bundle.get("tool_invocation", []), request))
    use = _uses(plan)["resource_revisit_v1"]
    groups = []
    for resource_id, rows in _resource_tools(tools).items():
        records = [
            {"resource": resource_id, "operation": row.values["semantic_operation"]}
            for row in rows
        ]
        groups.append(
            _group(
                {"resource_id": resource_id},
                {"operation_count": len(rows)},
                [_call(use, {"records": records})],
                (-len(rows), resource_id),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _event_stream(bundle: Mapping[str, list[CanonicalFact]], request: PlanRequest) -> list[CanonicalFact]:
    return _complete_order(
        _scoped(
            [
                fact
                for relation in ("canonical_call", "tool_invocation", "turn", "state_change")
                for fact in bundle.get(relation, [])
            ],
            request,
        )
    )


def _following_call_pairs(
    bundle: Mapping[str, list[CanonicalFact]], request: PlanRequest
) -> list[tuple[CanonicalFact, CanonicalFact]]:
    stream = _event_stream(bundle, request)
    return [
        (left, right)
        for left, right in zip(stream, stream[1:], strict=False)
        if left.relation == "tool_invocation" and right.relation == "canonical_call"
    ]


def _derive_tool_following(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    use = _uses(plan)["bounded_adjacency_v1"]
    groups = []
    for tool, call in _following_call_pairs(bundle, request):
        groups.append(
            _group(
                {"tool_id": tool.values["tool_id"]},
                {
                    "following_cached_input_tokens": call.values["cached_input_tokens"],
                    "following_output_tokens": call.values["output_tokens"],
                    "following_uncached_input_tokens": call.values["uncached_input_tokens"],
                    "tool_output_bytes": tool.values["output_bytes"],
                },
                [_call(use, {"records": [{"id": tool.logical_id}, {"id": call.logical_id}]})],
                (-(_number(tool.values["output_bytes"], "output_bytes") or 0), tool.logical_id),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _derive_tool_output_adjacency(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    stream = _event_stream(bundle, request)
    uses = _uses(plan)
    groups = []
    previous_call: CanonicalFact | None = None
    for index, fact in enumerate(stream):
        if fact.relation == "canonical_call":
            previous_call = fact
            continue
        if (
            fact.relation != "tool_invocation"
            or index + 1 >= len(stream)
            or stream[index + 1].relation != "canonical_call"
        ):
            continue
        following = stream[index + 1]
        previous_tokens = (
            previous_call.values["uncached_input_tokens"]
            if previous_call is not None
            else None
        )
        calls = [
            _call(
                uses["bounded_adjacency_v1"],
                {"records": [{"id": row.logical_id} for row in stream]},
            ),
            _call(
                uses["consecutive_delta_v1"],
                {
                    "current": following.values["uncached_input_tokens"],
                    "previous": previous_tokens,
                },
            ),
        ]
        groups.append(
            _group(
                {"tool_id": fact.values["tool_id"]},
                {"tool_output_bytes": fact.values["output_bytes"]},
                calls,
                (
                    -(
                        (
                            _number(
                                following.values["uncached_input_tokens"],
                                "uncached_input_tokens",
                            )
                            or 0
                        )
                        - (
                            _number(previous_tokens, "previous_uncached_input_tokens")
                            or 0
                        )
                    ),
                    fact.values["tool_id"],
                ),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _derive_tool_family(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    tools = _scoped(bundle.get("tool_invocation", []), request)
    pairs = _following_call_pairs(bundle, request)
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for tool in tools:
        grouped[tool.values["tool_family"]].append(tool)
    uses = _uses(plan)
    groups = []
    for family, rows in grouped.items():
        following = [
            call
            for tool, call in pairs
            if tool.values["tool_family"] == family
        ]
        direct = {
            "calls": len(rows),
            "failure_count": sum(row.values["lifecycle"] == "failed" for row in rows),
            "following_tokens": sum(
                (
                    (_number(call.values[field], field) or 0)
                    for call in following
                    for field in (
                        "uncached_input_tokens",
                        "cached_input_tokens",
                        "output_tokens",
                    )
                ),
                Decimal(0),
            ),
            "tool_output_bytes": _sum(rows, "output_bytes"),
        }
        duration = _call(
            uses["observed_duration_v1"],
            {"records": [{"duration_us": row.values["duration_us"]} for row in rows]},
        )
        adjacency = _call(
            uses["bounded_adjacency_v1"],
            {
                "records": [
                    {"id": fact.logical_id}
                    for fact in _event_stream(bundle, request)
                ]
            },
        )
        groups.append(
            _group(
                {"tool_name": family},
                direct,
                [adjacency, duration],
                (-len(rows), family),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _derive_resource_hotspots(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    tools = _scoped(bundle.get("tool_invocation", []), request)
    changes = _scoped(bundle.get("state_change", []), request)
    use = _uses(plan)["resource_operation_breakdown_v1"]
    groups = []
    for resource_id, rows in _resource_tools(tools).items():
        mutations = [
            change for change in changes if change.values["resource_id"] == resource_id
        ]
        records = [{"operation": row.values["semantic_operation"]} for row in rows]
        groups.append(
            _group(
                {"resource_id": resource_id},
                {
                    "duration_us": _sum(rows, "duration_us"),
                    "observed_mutations": len(mutations),
                    "tool_output_bytes": _sum(rows, "output_bytes"),
                },
                [_call(use, {"records": records})],
                (-len(records), resource_id),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _derive_tool_duration_gaps(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    stream = _event_stream(bundle, request)
    uses = _uses(plan)
    groups = []
    for tool, following in zip(stream, stream[1:], strict=False):
        if tool.relation != "tool_invocation" or tool.values["lifecycle"] != "completed":
            continue
        if tool.coordinates is None or following.coordinates is None:
            raise PlanOperandContractError("tool gap facts require coordinates")
        duration = tool.values["duration_us"]
        calls = [
            _call(
                uses["adjacent_event_gap_v1"],
                {
                    "current": following.coordinates.event_at_us,
                    "previous": tool.coordinates.event_at_us,
                },
            ),
            _call(
                uses["observed_duration_v1"],
                {"records": [{"duration_us": duration}]},
            ),
        ]
        groups.append(
            _group(
                {"tool_id": tool.values["tool_id"]},
                {"tool_status": tool.values["lifecycle"]},
                calls,
                (-(_number(duration, "duration_us") or 0), tool.logical_id),
            )
        )
    return PlanMaterialization(plan["plan_id"], tuple(sorted(groups, key=lambda x: x.order_key)))


def _derive_publication_delta(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    rows = bundle.get("publication_delta", [])
    if len(rows) != 1:
        raise PlanOperandContractError("latest publication requires exactly one accepted delta")
    fields = (
        "inserted_count",
        "removed_count",
        "corrected_count",
        "recanonicalized_count",
        "terminalized_count",
        "token_delta",
    )
    records = [{name: rows[0].values[name] for name in fields}]
    use = _uses(plan)["accepted_mutation_summary_v1"]
    return PlanMaterialization(
        plan["plan_id"], (_group({}, {}, [_call(use, {"records": records})], ()),)
    )


def _derive_evidence_timeline(
    plan: Mapping[str, Any],
    request: PlanRequest,
    bundle: Mapping[str, list[CanonicalFact]],
) -> PlanMaterialization:
    facts = _complete_order([fact for rows in bundle.values() for fact in rows])
    use = _uses(plan)["total_order_v1"]
    records = []
    groups = []
    for fact in facts:
        coordinate = fact.coordinates
        if coordinate is None:
            raise PlanOperandContractError("evidence facts require coordinates")
        record = {
            "event_at_us": coordinate.event_at_us,
            "source_rank": coordinate.source_rank,
            "source_order": coordinate.source_order,
            "event_kind_order": coordinate.event_kind_order,
            "logical_id": fact.logical_id,
            "transition_rank": coordinate.transition_rank,
        }
        records.append(record)
        groups.append(
            _group(
                {"logical_id": fact.logical_id},
                {
                    "event_kind": fact.relation,
                    "event_time_us": coordinate.event_at_us,
                    "lifecycle_basis": fact.values.get("lifecycle"),
                    "occurrence_coordinates": fact.values.get("occurrence_coordinates"),
                    "token_measurements": fact.values.get("token_measurements"),
                },
                [],
                coordinate.key(fact.logical_id),
            )
        )
    invocation = _call(use, {"records": records})
    if groups:
        first = groups[0]
        groups[0] = _group(dict(first.key), first.direct_slots, [invocation], first.order_key)
    return PlanMaterialization(plan["plan_id"], tuple(groups))


_DERIVATIONS: Mapping[
    str,
    Callable[
        [Mapping[str, Any], PlanRequest, Mapping[str, list[CanonicalFact]]],
        PlanMaterialization,
    ],
] = {
    "derive_current_usage_v1": _derive_current_usage,
    "derive_model_effort_mix_v1": _derive_model_effort_mix,
    "derive_allowance_interval_events_v1": _derive_allowance_events,
    "derive_repeated_resource_operations_v1": _derive_repeated_resources,
    "derive_tool_family_behavior_v1": _derive_tool_family,
    "derive_tool_following_activity_v1": _derive_tool_following,
    "derive_tool_output_adjacency_v1": _derive_tool_output_adjacency,
    "derive_resource_hotspots_v1": _derive_resource_hotspots,
    "derive_tool_duration_gaps_v1": _derive_tool_duration_gaps,
    "derive_latest_publication_delta_v1": _derive_publication_delta,
    "derive_evidence_timeline_v1": _derive_evidence_timeline,
}


def _derivation_registry() -> dict[
    str,
    Callable[
        [Mapping[str, Any], PlanRequest, Mapping[str, list[CanonicalFact]]],
        PlanMaterialization,
    ],
]:
    registry = dict(_DERIVATIONS)
    try:
        from codex_usage_tracker.agent_kernel.domain.plan_derivations_accounting import (
            DERIVATIONS as accounting_derivations,
        )
    except ImportError:
        accounting_derivations = {}
    try:
        from codex_usage_tracker.agent_kernel.domain.plan_derivations_structural import (
            DERIVATIONS as structural_derivations,
        )
    except ImportError:
        structural_derivations = {}
    for additions in (accounting_derivations, structural_derivations):
        overlap = set(registry).intersection(additions)
        if overlap:
            raise PlanOperandContractError(
                f"duplicate derivation symbols: {sorted(overlap)}"
            )
        registry.update(additions)
    return registry


def _validate_materialization(
    plan: Mapping[str, Any], materialization: PlanMaterialization
) -> PlanMaterialization:
    if materialization.plan_id != plan["plan_id"]:
        raise PlanOperandContractError("derivation returned the wrong plan_id")

    grouping = plan.get("grouping")
    if not isinstance(grouping, Mapping):
        raise PlanOperandContractError("grouping declaration is malformed")
    declared_keys = grouping.get("keys")
    cardinality = grouping.get("cardinality")
    if not isinstance(declared_keys, list) or not all(
        isinstance(key, str) and key for key in declared_keys
    ):
        raise PlanOperandContractError("grouping keys declaration is malformed")
    if cardinality not in {"single", "one_per_distinct_key"}:
        raise PlanOperandContractError("grouping cardinality is unsupported")
    if cardinality == "one_per_distinct_key" and not declared_keys:
        raise PlanOperandContractError(
            "one_per_distinct_key grouping requires at least one key"
        )
    if cardinality == "single" and (
        declared_keys or len(materialization.groups) != 1
    ):
        raise PlanOperandContractError(
            "single grouping must produce exactly one unkeyed group"
        )

    declared_uses = {use["use_id"]: use for use in plan.get("formula_uses", [])}
    result_order = plan.get("result_order")
    if not isinstance(result_order, list) or not all(
        isinstance(item, str) and item for item in result_order
    ):
        raise PlanOperandContractError("result_order declaration is malformed")
    seen_keys: set[tuple[tuple[str, Any], ...]] = set()
    order_keys: list[tuple[Any, ...]] = []
    for group in materialization.groups:
        actual_keys = [name for name, _ in group.key]
        if actual_keys != declared_keys:
            raise PlanOperandContractError(
                "grouping keys mismatch; "
                f"declared={declared_keys}, actual={actual_keys}"
            )
        try:
            duplicate = group.key in seen_keys
        except TypeError as error:
            raise PlanOperandContractError("group keys must be hashable") from error
        if duplicate:
            raise PlanOperandContractError(f"duplicate group key: {group.key!r}")
        seen_keys.add(group.key)
        _assert_finite(group.key, "group key")
        _assert_finite(group.direct_slots, "direct slots")
        _assert_finite(group.order_key, "result order key")
        order_keys.append(group.order_key)

        actual_counts = {use_id: 0 for use_id in declared_uses}
        for call in group.formula_calls:
            matches = [
                use_id
                for use_id in declared_uses
                if call.use_id.startswith(f"{use_id}:")
            ]
            if len(matches) != 1:
                raise PlanOperandContractError(
                    f"formula call does not resolve to one declared use: {call.use_id}"
                )
            use_id = matches[0]
            use = declared_uses[use_id]
            if call.formula_id != use["formula_id"]:
                raise PlanOperandContractError(
                    f"formula call identity mismatch: {call.use_id}"
                )
            actual_counts[use_id] += 1
        for use_id, use in declared_uses.items():
            expected = use["derivation_rule"]["calls_per_group"]
            if actual_counts[use_id] != expected:
                raise PlanOperandContractError(
                    "formula call multiplicity mismatch; "
                    f"use_id={use_id}, expected={expected}, "
                    f"actual={actual_counts[use_id]}"
                )

    try:
        if len(order_keys) > 1 and any(not key for key in order_keys):
            raise PlanOperandContractError(
                "multi-row results require executable deterministic order keys"
            )
        if order_keys != sorted(order_keys):
            raise PlanOperandContractError(
                "derivation did not honor deterministic declared result ordering"
            )
    except TypeError as error:
        raise PlanOperandContractError(
            "result order keys must be mutually comparable"
        ) from error
    if len(order_keys) > 1:
        try:
            if len(set(order_keys)) != len(order_keys):
                raise PlanOperandContractError(
                    "result order keys must include a deterministic tie-breaker"
                )
        except TypeError as error:
            raise PlanOperandContractError("result order keys must be hashable") from error
    return materialization


def compile_plan_operands(
    contract: Mapping[str, Any],
    request: PlanRequest,
    facts: Sequence[CanonicalFact],
) -> PlanMaterialization:
    """Gate, scope, group, and compile facts through one named derivation."""

    if not isinstance(request, PlanRequest):
        raise PlanOperandContractError("request must be a PlanRequest")
    plan = _plan(contract, request.plan_id)
    _validate_request(plan, request)
    if plan.get("status") != "resolved":
        raise PlanOperandContractError(
            f"plan derivation is blocked: {plan.get('blocked_reason')}"
        )
    symbol = plan.get("derivation_symbol")
    if not isinstance(symbol, str):
        raise PlanOperandContractError(f"unimplemented derivation symbol: {symbol}")
    derivation = _derivation_registry().get(symbol)
    if derivation is None:
        raise PlanOperandContractError(f"unimplemented derivation symbol: {symbol}")
    try:
        materialization = derivation(plan, request, _bundle(plan, facts))
        return _validate_materialization(plan, materialization)
    except KeyError as error:
        raise PlanOperandContractError(
            f"derivation {symbol} is missing required field: {error.args[0]}"
        ) from error


def _extract(value: Any, path: str) -> Any:
    if path == "$":
        return value
    if path.startswith("[]."):
        name = path[3:]
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) and name in item for item in value
        ):
            raise PlanOperandContractError(f"invalid list output path: {path}")
        return [item[name] for item in value]
    if not isinstance(value, Mapping) or path not in value:
        raise PlanOperandContractError(f"invalid output path: {path}")
    return value[path]


def evaluate_plan(
    contract: Mapping[str, Any],
    request: PlanRequest,
    facts: Sequence[CanonicalFact],
    *,
    formula_evaluator: Callable[[str, Mapping[str, Any]], Any] = evaluate_formula,
) -> PlanEvaluation:
    """Evaluate only compiler-produced calls and assemble declared bindings."""

    plan = _plan(contract, request.plan_id)
    materialization = compile_plan_operands(contract, request, facts)
    rows = []
    internal = []
    for group in materialization.groups:
        row = dict(group.key)
        row.update(group.direct_slots)
        for call in group.formula_calls:
            try:
                result = formula_evaluator(call.formula_id, call.operands)
            except (FormulaOperandError, KeyError, TypeError, ValueError) as error:
                raise PlanOperandContractError(
                    f"formula rejected compiler operands: {call.use_id}"
                ) from error
            _assert_finite(result, f"formula result {call.use_id}")
            if call.internal_only:
                internal.append(
                    MappingProxyType(
                        {
                            "consume_as": call.consume_as,
                            "result": result,
                            "use_id": call.use_id,
                        }
                    )
                )
            for field_name, path in call.output_bindings.items():
                row[field_name] = _extract(result, path)
        expected = set(plan["answer_fields"]) | set(plan["grouping"]["keys"])
        actual = set(row)
        missing, extra = expected - actual, actual - expected
        if missing or extra:
            raise PlanOperandContractError(
                "answer fields mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        rows.append(MappingProxyType(row))
    return PlanEvaluation(request.plan_id, tuple(rows), tuple(internal))
