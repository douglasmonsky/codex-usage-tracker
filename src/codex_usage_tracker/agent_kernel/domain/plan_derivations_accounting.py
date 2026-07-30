"""Pure accounting, context, and allowance plan derivations.

This module deliberately contains no database, clock, or evaluator access.  It
only turns already gated canonical facts into the operands declared by a plan.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .plan_operands import (
    CanonicalFact,
    FactCoordinates,
    FormulaInvocation,
    PlanMaterialization,
    PlanOperandContractError,
    PlanRequest,
    _call,
    _complete_order,
    _group,
    _number,
    _scoped,
    _sum,
    _uses,
)


def _need(fact: CanonicalFact, name: str) -> Any:
    if name not in fact.values:
        raise PlanOperandContractError(f"{fact.relation} {fact.logical_id} is missing {name}")
    return fact.values[name]


def _calls(bundle: Mapping[str, list[CanonicalFact]], request: PlanRequest) -> list[CanonicalFact]:
    return _scoped(bundle.get("canonical_call", []), request)


def _tokens(rows: Sequence[CanonicalFact]) -> list[dict[str, Any]]:
    return [
        {
            name: _need(row, name)
            for name in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
        }
        for row in rows
    ]


def _total(rows: Sequence[CanonicalFact]) -> int | Decimal | None:
    if not rows:
        return _sum(rows, "uncached_input_tokens")
    values = [
        _number(_need(row, name), name)
        for row in rows
        for name in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
    ]
    if any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), Decimal(0))


def _required_number(value: Any, name: str) -> int | Decimal:
    numeric = _number(value, name)
    if numeric is None:
        raise PlanOperandContractError(f"{name} must not be null for this derivation")
    return numeric


def _zeroed(value: int | Decimal | None) -> int | Decimal:
    return value if value is not None else 0


def _difference(left: int | Decimal | None, right: int | Decimal | None) -> int | Decimal:
    left_value, right_value = _zeroed(left), _zeroed(right)
    if isinstance(left_value, Decimal):
        return left_value - Decimal(right_value)
    if isinstance(right_value, Decimal):
        return Decimal(left_value) - right_value
    return left_value - right_value


def _descending(value: int | Decimal) -> int | Decimal:
    return -value


def _absolute(value: int | Decimal) -> int | Decimal:
    if isinstance(value, Decimal):
        return abs(value)
    return abs(value)


def _coordinates(fact: CanonicalFact) -> FactCoordinates:
    if fact.coordinates is None:
        raise PlanOperandContractError("complete event coordinates are required")
    return fact.coordinates


def _materialize(plan: Mapping[str, Any], groups: list[Any]) -> PlanMaterialization:
    return PlanMaterialization(
        plan["plan_id"], tuple(sorted(groups, key=lambda group: group.order_key))
    )


def _ratio_call(
    use: Mapping[str, Any], operands: Mapping[str, Any], output: str
) -> FormulaInvocation:
    """Materialize the ALW03 five-call expansion from its one catalog use."""
    return FormulaInvocation(
        use_id=f"{use['use_id']}:{output}",
        formula_id=use["formula_id"],
        operands=MappingProxyType(dict(operands)),
        output_bindings=MappingProxyType({output: "$"}),
        internal_only=False,
        consume_as=None,
    )


def derive_top_sessions_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for call in _calls(bundle, request):
        grouped[_need(call, "session_id")].append(call)
    totals = {key: _total(rows) for key, rows in grouped.items()}
    values = list(totals.values())
    uses = _uses(plan)
    n = request.parameters.get("limit", 1)
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise PlanOperandContractError("limit must be a positive integer")
    out = []
    for session_id, rows in grouped.items():
        direct = {
            "calls": len(rows),
            **{
                field: _sum(rows, field)
                for field in (
                    "cached_input_tokens",
                    "uncached_input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                )
            },
        }
        out.append(
            _group(
                {"session_id": session_id},
                direct,
                [
                    _call(uses["hhi_v1"], {"values": values}),
                    _call(uses["top_n_share_v1"], {"values": values, "n": n}),
                    _call(uses["total_tokens_v1"], {"records": _tokens(rows)}),
                ],
                (-(totals[session_id] or 0), session_id),
            )
        )
    return _materialize(plan, out)


def derive_period_drivers_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    dimension = request.parameters["driver_dimension"]
    names = {
        "model_profile": "model_profile_id",
        "project": "project_id",
        "session": "session_id",
        "tool": "tool_id",
    }
    field = names.get(dimension)
    if field is None:
        raise PlanOperandContractError("driver_dimension is unsupported")
    windows = (request.parameters["previous_window"], request.parameters["current_window"])

    def in_window(row: CanonicalFact, window: Mapping[str, Any]) -> bool:
        at = row.coordinates.event_at_us if row.coordinates else None
        return isinstance(at, int) and window["start_us"] <= at < window["end_us"]

    grouped: dict[str, tuple[list[CanonicalFact], list[CanonicalFact]]] = {}
    for row in _calls(bundle, request):
        key = _need(row, field)
        previous, current = grouped.setdefault(key, ([], []))
        if in_window(row, windows[0]):
            previous.append(row)
        if in_window(row, windows[1]):
            current.append(row)
    uses = _uses(plan)
    out = []
    for key, (previous, current) in grouped.items():
        prior, now = _total(previous), _total(current)
        delta = _difference(now, prior)
        out.append(
            _group(
                {"driver_id": key},
                {"previous_total_tokens": prior, "current_total_tokens": now},
                [
                    _call(uses["equal_window_delta_v1"], {"previous": prior, "current": now}),
                    _call(
                        uses["signed_driver_reconciliation_v1"],
                        {
                            "values": [delta],
                            "total_delta": delta,
                        },
                    ),
                ],
                (_descending(_absolute(delta)), key),
            )
        )
    return _materialize(plan, out)


def derive_project_family_usage_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    mode = request.parameters["family_mode"]
    if mode not in {"project", "root_session"}:
        raise PlanOperandContractError("family_mode must be project or root_session")
    sessions = {row.logical_id: row for row in bundle.get("session", [])}

    def family(call: CanonicalFact) -> str:
        if mode == "project":
            return _need(call, "project_id")
        session = sessions.get(_need(call, "session_id"))
        return _need(session, "root_session_id") if session else _need(call, "session_id")

    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for call in _calls(bundle, request):
        grouped[family(call)].append(call)
    denominator = sum((_total(rows) or 0 for rows in grouped.values()), Decimal(0))
    uses = _uses(plan)
    out = []
    for key, rows in grouped.items():
        inclusive = _total(rows)
        descendant = 0
        out.append(
            _group(
                {"family_id": key},
                {"session_count": len({_need(row, "session_id") for row in rows})},
                [
                    _call(
                        uses["exclusive_inclusive_scope_v1"],
                        {"inclusive": inclusive, "descendant": descendant},
                    ),
                    _call(
                        uses["observed_share_v1"],
                        {"numerator": inclusive, "denominator": denominator},
                    ),
                ],
                (-(inclusive or 0), key),
            )
        )
    return _materialize(plan, out)


def derive_top_valued_entities_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    kind = request.parameters["entity_kind"]
    fields = {"call": "call_id", "turn": "turn_id", "session": "session_id"}
    if kind not in fields:
        raise PlanOperandContractError("entity_kind must be call, turn, or session")
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for row in _calls(bundle, request):
        grouped[_need(row, fields[kind])].append(row)
    valuation = {_need(row, "call_id"): row for row in bundle.get("valuation_match", [])}
    uses = _uses(plan)
    out = []
    for key, rows in grouped.items():
        rated = []
        for row in rows:
            matched = valuation.get(_need(row, "call_id"))
            rated.append(
                {"cost_usd": matched.values.get("configured_cost_usd") if matched else None}
            )
        credits = [valuation.get(_need(row, "call_id")) for row in rows]
        direct = {
            "estimated_credits": _sum([x for x in credits if x], "estimated_credits")
            if all(credits)
            else None
        }
        out.append(
            _group(
                {"entity_id": key},
                direct,
                [
                    _call(uses["current_valuation_v1"], {"records": rated}),
                    _call(uses["total_tokens_v1"], {"records": _tokens(rows)}),
                ],
                (-sum((x["cost_usd"] or 0 for x in rated), Decimal(0)), key),
            )
        )
    return _materialize(plan, out)


def derive_pricing_coverage_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = _calls(bundle, request)
    valuations = {_need(v, "call_id"): v for v in bundle.get("valuation_match", [])}
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for row in calls:
        grouped[_need(row, "model_profile_id")].append(row)
    use = _uses(plan)["valuation_coverage_v1"]
    out = []
    for profile, rows in grouped.items():
        priced = [row for row in rows if _need(row, "call_id") in valuations]
        unpriced = [row for row in rows if _need(row, "call_id") not in valuations]
        out.append(
            _group(
                {"model_profile_id": profile},
                {
                    "priced_calls": len(priced),
                    "unpriced_calls": len(unpriced),
                    "unpriced_tokens": _total(unpriced),
                },
                [_call(use, {"numerator": len(priced), "denominator": len(rows)})],
                (-(_total(unpriced) or 0), profile),
            )
        )
    return _materialize(plan, out)


def derive_cache_reuse_candidates_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = _calls(bundle, request)
    use = _uses(plan)
    out = []
    for row in calls:
        cached = _need(row, "cached_input_tokens")
        uncached = _need(row, "uncached_input_tokens")
        key = _need(row, "call_id")
        out.append(
            _group(
                {"call_id": key},
                {"cached_input_tokens": cached, "uncached_input_tokens": uncached},
                [
                    _call(
                        use["cached_share_v1"],
                        {"numerator": cached, "denominator": (cached or 0) + (uncached or 0)},
                    ),
                    _call(use["total_input_tokens_v1"], {"records": _tokens([row])}),
                ],
                (-((cached or 0) + (uncached or 0)), key),
            )
        )
    return _materialize(plan, out)


def derive_context_pressure_trajectory_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    rows = _complete_order(_calls(bundle, request))
    boundaries = _complete_order(_scoped(bundle.get("compaction_boundary", []), request))
    grouped: dict[tuple[str, str], list[CanonicalFact]] = defaultdict(list)
    for row in rows:
        session_id = _need(row, "session_id")
        row_key = _coordinates(row).key(row.logical_id)
        preceding = [
            boundary
            for boundary in boundaries
            if _need(boundary, "session_id") == session_id
            and _coordinates(boundary).key(boundary.logical_id) <= row_key
        ]
        context_epoch_id = (
            _need(preceding[-1], "compaction_id") if preceding else "initial"
        )
        grouped[(session_id, context_epoch_id)].append(row)
    uses = _uses(plan)
    out = []
    for (session_id, context_epoch_id), epoch_rows in grouped.items():
        cached = _sum(epoch_rows, "cached_input_tokens")
        uncached = _sum(epoch_rows, "uncached_input_tokens")
        ordered_inputs = [
            _required_number(_need(row, "cached_input_tokens"), "cached_input_tokens")
            + _required_number(
                _need(row, "uncached_input_tokens"), "uncached_input_tokens"
            )
            for row in epoch_rows
        ]
        input_tokens = ordered_inputs[-1]
        last = epoch_rows[-1]
        out.append(
            _group(
                {
                    "session_id": session_id,
                    "context_epoch_id": context_epoch_id,
                },
                {
                    "context_window_tokens": _need(last, "context_window_tokens"),
                    "ordered_input_tokens": ordered_inputs,
                },
                [
                    _call(
                        uses["cached_share_v1"],
                        {
                            "numerator": cached,
                            "denominator": (cached or 0) + (uncached or 0),
                        },
                    ),
                    _call(
                        uses["context_pressure_v1"],
                        {
                            "input_tokens": input_tokens,
                            "context_window_tokens": _need(last, "context_window_tokens"),
                        },
                    ),
                    _call(
                        uses["trajectory_slope_v1"],
                        {"values": ordered_inputs},
                    ),
                ],
                (-input_tokens, session_id, context_epoch_id),
            )
        )
    return _materialize(plan, out)


def derive_token_acceleration_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    minimum_samples = request.parameters["minimum_samples"]
    if (
        isinstance(minimum_samples, bool)
        or not isinstance(minimum_samples, int)
        or minimum_samples < 1
    ):
        raise PlanOperandContractError("minimum_samples must be a positive integer")
    rows = _complete_order(_calls(bundle, request))
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for row in rows:
        grouped[_need(row, "session_id")].append(row)
    uses = _uses(plan)
    out = []
    for session_id, session_rows in grouped.items():
        by_turn: dict[str, list[CanonicalFact]] = defaultdict(list)
        for row in session_rows:
            turn_id = _need(row, "turn_id")
            if not isinstance(turn_id, str) or not turn_id:
                raise PlanOperandContractError("turn_id must be a non-empty stable ID")
            by_turn[turn_id].append(row)
        totals = [_total(turn_rows) for turn_rows in by_turn.values()]
        if len(totals) < minimum_samples:
            continue
        midpoint = max(1, len(totals) // 2)
        earlier = totals[:midpoint]
        later = totals[midpoint:]
        operands = {
            "current": totals[-1],
            "middle": totals[-2] if len(totals) > 1 else None,
            "previous": totals[-3] if len(totals) > 2 else None,
        }
        acceleration = (
            (operands["current"] or 0)
            - 2 * (operands["middle"] or 0)
            + (operands["previous"] or 0)
        )
        out.append(
            _group(
                {"session_id": session_id},
                {"turn_tokens": totals},
                [
                    _call(
                        uses["later_earlier_median_ratio_v1"], {"earlier": earlier, "later": later}
                    ),
                    _call(uses["second_difference_v1"], operands),
                ],
                (-acceleration, session_id),
            )
        )
    return _materialize(plan, out)


def derive_uncached_input_jumps_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    rows = _complete_order(_calls(bundle, request))
    use = _uses(plan)["consecutive_delta_v1"]
    return _materialize(
        plan,
        [
            _group(
                {"call_id": _need(current, "call_id")},
                {
                    "previous_uncached_input_tokens": _need(previous, "uncached_input_tokens"),
                    "current_uncached_input_tokens": _need(current, "uncached_input_tokens"),
                },
                [
                    _call(
                        use,
                        {
                            "previous": _need(previous, "uncached_input_tokens"),
                            "current": _need(current, "uncached_input_tokens"),
                        },
                    )
                ],
                _coordinates(current).key(current.logical_id),
            )
            for previous, current in zip(rows, rows[1:], strict=False)
        ],
    )


def derive_cached_replay_small_output_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    threshold = request.parameters["threshold"]
    if not isinstance(threshold, (int, Decimal)) or isinstance(threshold, bool):
        raise PlanOperandContractError("threshold must be exact numeric")
    use = _uses(plan)["cached_output_ratio_v1"]
    out = []
    for row in _calls(bundle, request):
        output = _need(row, "output_tokens")
        if _required_number(output, "output_tokens") > threshold:
            continue
        out.append(
            _group(
                {"call_id": _need(row, "call_id")},
                {"cached_input_tokens": _need(row, "cached_input_tokens"), "output_tokens": output},
                [
                    _call(
                        use, {"numerator": _need(row, "cached_input_tokens"), "denominator": output}
                    )
                ],
                (-_need(row, "cached_input_tokens"), _need(row, "call_id")),
            )
        )
    return _materialize(plan, out)


def derive_context_composition_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    rows = _scoped(bundle.get("context_component", []), request)
    grouped: dict[str, list[CanonicalFact]] = defaultdict(list)
    for row in rows:
        grouped[_need(row, "category")].append(row)
    use = _uses(plan)["context_component_coverage_v1"]
    out = []
    for category, items in grouped.items():
        totals = {_need(row, "total_context_utf8_bytes") for row in items}
        if len(totals) != 1:
            raise PlanOperandContractError(
                "context component denominator must be stable per category"
            )
        observed = _sum(items, "observed_utf8_bytes")
        out.append(
            _group(
                {"component_kind": category},
                {
                    "component_count": len(items),
                    "estimated_component_tokens": _sum(items, "estimated_tokens"),
                },
                [
                    _call(
                        use,
                        {
                            "records": [
                                {"bytes": _need(row, "observed_utf8_bytes")} for row in items
                            ],
                            "total_bytes": next(iter(totals)),
                        },
                    )
                ],
                (-(observed or 0), category),
            )
        )
    return _materialize(plan, out)


def derive_compaction_comparison_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    boundaries = _complete_order(_scoped(bundle.get("compaction_boundary", []), request))
    calls = _complete_order(_calls(bundle, request))
    use = _uses(plan)["symmetric_boundary_comparison_v1"]
    out = []
    for boundary in boundaries:
        at = _coordinates(boundary).event_at_us
        if at is None:
            raise PlanOperandContractError("compaction boundaries require event timestamps")
        before = [
            x
            for x in calls
            if x.coordinates is not None
            and x.coordinates.event_at_us is not None
            and x.coordinates.event_at_us < at
        ]
        after = [
            x
            for x in calls
            if x.coordinates is not None
            and x.coordinates.event_at_us is not None
            and x.coordinates.event_at_us >= at
        ]
        before_value = _need(before[-1], "context_window_tokens") if before else None
        after_value = _need(after[0], "context_window_tokens") if after else None
        out.append(
            _group(
                {"compaction_id": _need(boundary, "compaction_id")},
                {"before_tokens": before_value, "after_tokens": after_value},
                [_call(use, {"before": before_value, "after": after_value})],
                _coordinates(boundary).key(boundary.logical_id),
            )
        )
    return _materialize(plan, out)


def derive_growth_without_mutation_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    calls = _complete_order(_calls(bundle, request))
    by_session: dict[str, list[CanonicalFact]] = defaultdict(list)
    for row in calls:
        by_session[_need(row, "session_id")].append(row)
    changes = _scoped(bundle.get("state_change", []), request)
    turns = _scoped(bundle.get("turn", []), request)
    uses = _uses(plan)
    out = []
    for session, rows in by_session.items():
        mutations = [x for x in changes if _need(x, "session_id") == session]
        count = len({_need(x, "turn_id") for x in turns if _need(x, "session_id") == session})
        out.append(
            _group(
                {"session_id": session},
                {"mutation_count": len(mutations), "turn_count": count},
                [
                    _call(
                        uses["context_growth_v1"],
                        {
                            "first": _need(rows[0], "context_window_tokens"),
                            "last": _need(rows[-1], "context_window_tokens"),
                        },
                    ),
                    _call(
                        uses["mutation_density_v1"],
                        {"mutation_count": len(mutations), "turn_count": count},
                    ),
                ],
                (
                    -(
                        _need(rows[-1], "context_window_tokens")
                        - _need(rows[0], "context_window_tokens")
                    ),
                    session,
                ),
            )
        )
    return _materialize(plan, out)


def derive_long_vs_split_cohorts_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    cohort = request.parameters["cohort"]
    if (
        not isinstance(cohort, Mapping)
        or set(cohort) != {"left", "right"}
        or not all(isinstance(cohort[x], (list, tuple)) for x in ("left", "right"))
    ):
        raise PlanOperandContractError("cohort must be an explicit {left, right} object")
    calls = _calls(bundle, request)
    uses = _uses(plan)
    out = []
    for side in ("left", "right"):
        ids = set(cohort[side])
        rows = [x for x in calls if _need(x, "session_id") in ids]
        other = [
            x
            for x in calls
            if _need(x, "session_id") in set(cohort["right" if side == "left" else "left"])
        ]
        context = _total(rows)
        usage = _total(rows)
        out.append(
            _group(
                {"cohort": side},
                {
                    "cohort_size": len(ids),
                    "context_features": {"total_context_tokens": context},
                    "usage_features": {"total_tokens": usage},
                },
                [
                    _call(
                        uses["explicit_cohort_comparison_v1"],
                        {"left": _total(rows), "right": _total(other)},
                    )
                ],
                (side,),
            )
        )
    return _materialize(plan, out)


def _ordered_observations(
    bundle: Mapping[str, list[CanonicalFact]], request: PlanRequest
) -> list[CanonicalFact]:
    return _complete_order(_scoped(bundle.get("allowance_observation", []), request))


def _allowance_operands(left: CanonicalFact, right: CanonicalFact) -> dict[str, Any]:
    fields = (
        ("provider", "provider"),
        ("limit", "limit_id"),
        ("plan", "plan"),
        ("window_kind", "window_kind"),
        ("reset", "reset_identity"),
        ("observed_at_us", "observed_at_us"),
    )
    return {
        f"{side}_{target}": _need(row, source)
        for side, row in (("left", left), ("right", right))
        for target, source in fields
    }


def _intervals(
    bundle: Mapping[str, list[CanonicalFact]], request: PlanRequest
) -> list[tuple[CanonicalFact, CanonicalFact, list[CanonicalFact]]]:
    observations = _ordered_observations(bundle, request)
    calls = _calls(bundle, request)
    result = []
    for left, right in zip(observations, observations[1:], strict=False):
        start, end = _need(left, "observed_at_us"), _need(right, "observed_at_us")
        result.append(
            (
                left,
                right,
                [
                    row
                    for row in calls
                    if row.coordinates
                    and row.coordinates.event_at_us is not None
                    and start <= row.coordinates.event_at_us < end
                ],
            )
        )
    return result


def _interval_direct(
    rows: Sequence[CanonicalFact], bundle: Mapping[str, list[CanonicalFact]]
) -> dict[str, Any]:
    valuations = {_need(x, "call_id"): x for x in bundle.get("valuation_match", [])}
    valuations_rows = [valuations.get(_need(x, "call_id")) for x in rows]
    turns = {_need(x, "turn_id") for x in rows if "turn_id" in x.values}
    return {
        "calls": len(rows),
        "turns": len(turns),
        "cached_input_tokens": _sum(rows, "cached_input_tokens"),
        "uncached_input_tokens": _sum(rows, "uncached_input_tokens"),
        "output_tokens": _sum(rows, "output_tokens"),
        "reasoning_tokens": _sum(rows, "reasoning_tokens"),
        "configured_cost_usd": _sum([x for x in valuations_rows if x], "configured_cost_usd")
        if all(valuations_rows)
        else None,
        "estimated_credits": _sum([x for x in valuations_rows if x], "estimated_credits")
        if all(valuations_rows)
        else None,
    }


def derive_allowance_movement_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    uses = _uses(plan)
    out = []
    for left, right, rows in _intervals(bundle, request):
        direct = _interval_direct(rows, bundle)
        direct["allowance_percent"] = _need(
            right, "allowance_percent"
        )  # intervals attach to their ending observation
        out.append(
            _group(
                {"allowance_observation_id": right.logical_id},
                direct,
                [
                    _call(
                        uses["compatible_allowance_interval_v1"], _allowance_operands(left, right)
                    ),
                    _call(uses["total_tokens_v1"], {"records": _tokens(rows)}),
                ],
                (_need(right, "observed_at_us"), right.logical_id),
            )
        )
    return _materialize(plan, out)


def derive_allowance_local_efficiency_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    uses = _uses(plan)
    ratio = uses["compatible_positive_allowance_ratio_v1"]
    out = []
    for left, right, rows in _intervals(bundle, request):
        delta = _need(left, "allowance_percent") - _need(right, "allowance_percent")
        direct = {"allowance_delta": delta}
        compatibility_operands = _allowance_operands(left, right)
        compatible = (
            compatibility_operands["left_provider"] == compatibility_operands["right_provider"]
            and compatibility_operands["left_limit"] == compatibility_operands["right_limit"]
            and compatibility_operands["left_plan"] == compatibility_operands["right_plan"]
            and compatibility_operands["left_window_kind"]
            == compatibility_operands["right_window_kind"]
            and compatibility_operands["left_reset"] == compatibility_operands["right_reset"]
            and compatibility_operands["left_observed_at_us"]
            <= compatibility_operands["right_observed_at_us"]
        )
        base = {"compatible": compatible, "allowance_delta": delta}
        # The catalog may declare this internal audit total; it is not fed back
        # into the ratio calls, whose values are canonical-row sums.
        calls = (
            [_call(uses["total_tokens_v1"], {"records": _tokens(rows)})]
            if "total_tokens_v1" in uses
            else []
        )
        # Five independent ratio calls keep each answer field bound to one scalar invocation.
        for field, value in (
            ("calls_per_point", len(rows)),
            ("cost_per_point", _interval_direct(rows, bundle)["configured_cost_usd"]),
            ("credits_per_point", _interval_direct(rows, bundle)["estimated_credits"]),
            ("tokens_per_point", _total(rows)),
            ("turns_per_point", _interval_direct(rows, bundle)["turns"]),
        ):
            calls.append(_ratio_call(ratio, {**base, "value": value}, field))
        out.append(
            _group(
                {"allowance_interval_id": f"{left.logical_id}:{right.logical_id}"},
                direct,
                calls,
                (_need(left, "observed_at_us"), left.logical_id),
            )
        )
    return _materialize(plan, out)


def derive_allowance_cycle_comparison_v1(
    plan: Mapping[str, Any], request: PlanRequest, bundle: Mapping[str, list[CanonicalFact]]
) -> PlanMaterialization:
    uses = _uses(plan)
    out = []
    for left, right, rows in _intervals(bundle, request):
        if _need(right, "completion_status") != "completed":
            continue
        direct = {
            key: value
            for key, value in _interval_direct(rows, bundle).items()
            if key in plan["answer_fields"]
        }
        direct["cycle_duration_us"] = _need(right, "observed_at_us") - _need(left, "observed_at_us")
        out.append(
            _group(
                {"allowance_interval_id": f"{left.logical_id}:{right.logical_id}"},
                direct,
                [
                    _call(
                        uses["completed_allowance_cycle_comparison_v1"],
                        {
                            "left": _need(left, "allowance_percent"),
                            "right": _need(right, "allowance_percent"),
                        },
                    ),
                    _call(uses["total_tokens_v1"], {"records": _tokens(rows)}),
                ],
                (_need(left, "observed_at_us"), left.logical_id),
            )
        )
    return _materialize(plan, out)


DERIVATIONS: Mapping[
    str,
    Callable[
        [Mapping[str, Any], PlanRequest, Mapping[str, list[CanonicalFact]]], PlanMaterialization
    ],
] = {
    "derive_top_sessions_v1": derive_top_sessions_v1,
    "derive_period_drivers_v1": derive_period_drivers_v1,
    "derive_project_family_usage_v1": derive_project_family_usage_v1,
    "derive_top_valued_entities_v1": derive_top_valued_entities_v1,
    "derive_pricing_coverage_v1": derive_pricing_coverage_v1,
    "derive_cache_reuse_candidates_v1": derive_cache_reuse_candidates_v1,
    "derive_context_pressure_trajectory_v1": derive_context_pressure_trajectory_v1,
    "derive_token_acceleration_v1": derive_token_acceleration_v1,
    "derive_uncached_input_jumps_v1": derive_uncached_input_jumps_v1,
    "derive_cached_replay_small_output_v1": derive_cached_replay_small_output_v1,
    "derive_context_composition_v1": derive_context_composition_v1,
    "derive_compaction_comparison_v1": derive_compaction_comparison_v1,
    "derive_growth_without_mutation_v1": derive_growth_without_mutation_v1,
    "derive_long_vs_split_cohorts_v1": derive_long_vs_split_cohorts_v1,
    "derive_allowance_movement_v1": derive_allowance_movement_v1,
    "derive_allowance_local_efficiency_v1": derive_allowance_local_efficiency_v1,
    "derive_allowance_cycle_comparison_v1": derive_allowance_cycle_comparison_v1,
}
