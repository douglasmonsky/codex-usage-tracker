"""Pure, fail-closed, normalized-fact formula operations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


class FormulaOperandError(ValueError):
    """A required normalized operand is absent or malformed."""


FORMULA_IDS = frozenset(
    {
        "accepted_mutation_summary_v1",
        "adjacent_event_gap_v1",
        "bounded_adjacency_v1",
        "cached_output_ratio_v1",
        "cached_share_v1",
        "compatible_allowance_interval_v1",
        "compatible_positive_allowance_ratio_v1",
        "completed_allowance_cycle_comparison_v1",
        "completion_cohort_ratio_v1",
        "consecutive_delta_v1",
        "consecutive_profile_transition_v1",
        "context_component_coverage_v1",
        "context_growth_v1",
        "context_pressure_v1",
        "current_valuation_v1",
        "equal_window_delta_v1",
        "exclusive_inclusive_scope_v1",
        "explicit_cohort_comparison_v1",
        "first_boundary_v1",
        "freshness_age_v1",
        "half_open_interval_membership_v1",
        "hhi_v1",
        "investigation_feature_vector_v1",
        "later_earlier_median_ratio_v1",
        "mutation_density_v1",
        "observational_cohort_comparison_v1",
        "observed_duration_v1",
        "observed_share_v1",
        "resource_operation_breakdown_v1",
        "resource_revisit_v1",
        "retry_sequence_matcher_v1",
        "second_difference_v1",
        "semantic_occurrence_reconciliation_v1",
        "side_by_side_delta_v1",
        "signed_driver_contribution_v1",
        "signed_driver_reconciliation_v1",
        "structural_workflow_features_v1",
        "symmetric_boundary_comparison_v1",
        "top_n_share_v1",
        "top_share_v1",
        "total_input_tokens_v1",
        "total_order_v1",
        "total_tokens_v1",
        "trajectory_slope_v1",
        "valuation_coverage_v1",
    }
)


def _d(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise FormulaOperandError("numeric operand is required")
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise FormulaOperandError("invalid numeric operand") from error


def _int(value: Decimal) -> int | Decimal:
    return int(value) if value == value.to_integral_value() else value


def _ratio(a: Any, b: Any) -> Decimal | None:
    if a is None or b is None:
        return None
    numerator, denominator = _d(a), _d(b)
    return None if denominator == 0 else numerator / denominator


def _rows(o: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = o.get("records")
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise FormulaOperandError("records must be a list of objects")
    return value


def _sum(rows: list[Mapping[str, Any]], *names: str) -> int | Decimal | None:
    result = Decimal(0)
    for row in rows:
        for name in names:
            if row.get(name) is None:
                return None
            result += _d(row[name])
    return _int(result)


def _values(o: Mapping[str, Any]) -> list[Decimal]:
    values = o.get("values")
    if not isinstance(values, list):
        raise FormulaOperandError("values must be a list")
    return [_d(value) for value in values]


def _nullable_delta(current: Any, previous: Any) -> int | Decimal | None:
    if current is None or previous is None:
        return None
    return _int(_d(current) - _d(previous))


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def _window(o: Mapping[str, Any]) -> tuple[int, int]:
    start, end = o.get("start_us"), o.get("end_us")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start > end
    ):
        raise FormulaOperandError("start_us and end_us must form a half-open integer window")
    return start, end


def evaluate_formula(formula_id: str, operands: Mapping[str, Any]) -> Any:
    """Evaluate one named contract symbol; never query storage or a clock."""
    if formula_id not in FORMULA_IDS:
        raise FormulaOperandError(f"unknown formula ID: {formula_id}")
    if not isinstance(operands, Mapping):
        raise FormulaOperandError("operands must be an object")
    if formula_id == "total_tokens_v1":
        return _sum(
            _rows(operands), "uncached_input_tokens", "cached_input_tokens", "output_tokens"
        )
    if formula_id == "total_input_tokens_v1":
        return _sum(_rows(operands), "uncached_input_tokens", "cached_input_tokens")
    if formula_id in {
        "cached_share_v1",
        "observed_share_v1",
        "valuation_coverage_v1",
        "completion_cohort_ratio_v1",
        "cached_output_ratio_v1",
    }:
        return _ratio(operands.get("numerator"), operands.get("denominator"))
    if formula_id in {
        "equal_window_delta_v1",
        "consecutive_delta_v1",
        "side_by_side_delta_v1",
        "adjacent_event_gap_v1",
        "freshness_age_v1",
    }:
        return _nullable_delta(
            operands.get("current"),
            operands.get("previous"),
        )
    if formula_id == "second_difference_v1":
        if any(operands.get(name) is None for name in ("current", "middle", "previous")):
            return None
        return _int(
            _d(operands.get("current"))
            - 2 * _d(operands.get("middle"))
            + _d(operands.get("previous"))
        )
    if formula_id == "context_growth_v1":
        return _nullable_delta(operands.get("last"), operands.get("first"))
    if formula_id == "trajectory_slope_v1":
        values = _values(operands)
        return None if len(values) < 2 else (values[-1] - values[0]) / Decimal(len(values) - 1)
    if formula_id == "later_earlier_median_ratio_v1":
        return _ratio(
            _median([_d(x) for x in operands.get("later", [])]),
            _median([_d(x) for x in operands.get("earlier", [])]),
        )
    if formula_id == "context_pressure_v1":
        return _ratio(operands.get("input_tokens"), operands.get("context_window_tokens"))
    if formula_id == "mutation_density_v1":
        return _ratio(operands.get("mutation_count"), operands.get("turn_count"))
    if formula_id in {"top_share_v1", "top_n_share_v1"}:
        values, n = _values(operands), operands.get("n", 1)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise FormulaOperandError("n must be a positive integer")
        top_share = _ratio(
            sum(sorted(values, reverse=True)[:n], Decimal(0)),
            sum(values, Decimal(0)),
        )
        if formula_id == "top_share_v1":
            return top_share
        return {
            "top_share": top_share,
            "remainder_share": None if top_share is None else Decimal(1) - top_share,
        }
    if formula_id == "hhi_v1":
        values = _values(operands)
        total = sum(values, Decimal(0))
        return None if not total else sum((value / total) ** 2 for value in values)
    if formula_id == "accepted_mutation_summary_v1":
        rows = _rows(operands)
        names = (
            "inserted_count",
            "removed_count",
            "corrected_count",
            "recanonicalized_count",
            "terminalized_count",
            "token_delta",
        )
        return {name: _sum(rows, name) for name in names}
    if formula_id == "half_open_interval_membership_v1":
        start, end = _window(operands)
        event = operands.get("event_time_us")
        if event is None:
            return False
        if isinstance(event, bool) or not isinstance(event, int):
            raise FormulaOperandError("event_time_us must be an integer or null")
        return start <= event < end
    if formula_id == "compatible_allowance_interval_v1":
        allowance_fields = (
            "left_provider",
            "right_provider",
            "left_limit",
            "right_limit",
            "left_plan",
            "right_plan",
            "left_window_kind",
            "right_window_kind",
            "left_reset",
            "right_reset",
            "left_observed_at_us",
            "right_observed_at_us",
        )
        if any(operands.get(name) is None for name in allowance_fields):
            raise FormulaOperandError("allowance compatibility operands are required")
        return (
            operands["left_provider"] == operands["right_provider"]
            and operands["left_limit"] == operands["right_limit"]
            and operands["left_plan"] == operands["right_plan"]
            and operands["left_window_kind"] == operands["right_window_kind"]
            and operands["left_reset"] == operands["right_reset"]
            and _d(operands["left_observed_at_us"])
            <= _d(operands["right_observed_at_us"])
        )
    if formula_id == "compatible_positive_allowance_ratio_v1":
        return (
            None
            if not operands.get("compatible") or _d(operands.get("allowance_delta")) <= 0
            else _ratio(operands.get("value"), operands.get("allowance_delta"))
        )
    if formula_id == "signed_driver_contribution_v1":
        return _nullable_delta(
            operands.get("current"),
            operands.get("previous"),
        )
    if formula_id == "signed_driver_reconciliation_v1":
        drivers = _values(operands)
        total = _d(operands.get("total_delta"))
        return {
            "drivers": _int(sum(drivers, Decimal(0))),
            "unexplained": _int(total - sum(drivers, Decimal(0))),
        }
    if formula_id == "exclusive_inclusive_scope_v1":
        return {
            "exclusive": _int(_d(operands.get("inclusive")) - _d(operands.get("descendant"))),
            "inclusive": _int(_d(operands.get("inclusive"))),
        }
    if formula_id == "current_valuation_v1":
        rows = _rows(operands)
        rated = [row for row in rows if row.get("cost_usd") is not None]
        return {
            "configured_cost_usd": _sum(rated, "cost_usd") or 0,
            "rated_calls": len(rated),
            "unrated_calls": len(rows) - len(rated),
        }
    if formula_id == "total_order_v1":
        rows = _rows(operands)
        order_fields = (
            "source_rank",
            "source_order",
            "event_kind_order",
            "logical_id",
            "transition_rank",
        )
        if any(any(key not in row for key in order_fields) for row in rows):
            raise FormulaOperandError("total-order coordinates are required")
        return [
            dict(row)
            for row in sorted(
                rows,
                key=lambda r: (
                    r.get("event_at_us") is None,
                    r.get("event_at_us") if r.get("event_at_us") is not None else 0,
                    r["source_rank"],
                    r["source_order"],
                    r["event_kind_order"],
                    str(r["logical_id"]),
                    r["transition_rank"],
                ),
            )
        ]
    if formula_id == "observed_duration_v1":
        return _sum(_rows(operands), "duration_us")
    if formula_id == "bounded_adjacency_v1":
        rows = _rows(operands)
        return [
            {
                "left_id": row.get("id"),
                "right_id": rows[index + 1].get("id"),
                "intervening_events": 0,
            }
            for index, row in enumerate(rows[:-1])
        ]
    if formula_id == "first_boundary_v1":
        rows = _rows(operands)
        matches = [row for row in rows if row.get("kind") == operands.get("boundary_kind")]
        return None if not matches else matches[0].get("tokens")
    if formula_id == "resource_revisit_v1":
        rows = _rows(operands)
        seen: dict[tuple[Any, Any], int] = {}
        distances = []
        for index, row in enumerate(rows):
            key = (row.get("resource"), row.get("operation"))
            if key in seen:
                distances.append(index - seen[key])
            seen[key] = index
        return {"revisit_count": len(distances), "revisit_distance": distances}
    if formula_id == "retry_sequence_matcher_v1":
        rows = _rows(operands)
        matched_events = [
            [row.get("id") for row in rows[index : index + 5]]
            for index in range(max(0, len(rows) - 4))
            if tuple(row.get("stage") for row in rows[index : index + 5])
            == ("inspect", "attempt", "failure", "reinspect", "retry")
            and len(
                {
                    row.get("resource")
                    for row in rows[index : index + 5]
                }
            )
            == 1
            and rows[index].get("resource") not in (None, "")
        ]
        if any(any(event_id in (None, "") for event_id in match) for match in matched_events):
            raise FormulaOperandError("matched retry events require stable IDs")
        return {
            "retry_cycles": len(matched_events),
            "matched_events": matched_events,
        }
    if formula_id == "consecutive_profile_transition_v1":
        rows = _rows(operands)
        transitions = [
            (left, right)
            for left, right in zip(rows, rows[1:], strict=False)
            if left.get("profile") != right.get("profile")
        ]
        token_delta: list[int | Decimal | None] = []
        for left, right in transitions:
            if left.get("total_tokens") is None or right.get("total_tokens") is None:
                token_delta.append(None)
            else:
                token_delta.append(
                    _int(_d(right["total_tokens"]) - _d(left["total_tokens"]))
                )
        return {
            "transition_count": len(transitions),
            "token_delta": token_delta,
        }
    if formula_id == "resource_operation_breakdown_v1":
        out: dict[str, int] = {}
        for row in _rows(operands):
            operation = row.get("operation")
            if not isinstance(operation, str) or not operation:
                raise FormulaOperandError("resource operations must be non-empty strings")
            out[operation] = out.get(operation, 0) + 1
        return dict(sorted(out.items()))
    if formula_id == "context_component_coverage_v1":
        component_bytes = _sum(_rows(operands), "bytes")
        total_bytes = operands.get("total_bytes")
        return {
            "component_bytes": component_bytes,
            "unattributed_bytes": (
                None
                if component_bytes is None or total_bytes is None
                else _int(_d(total_bytes) - _d(component_bytes))
            ),
        }
    if formula_id == "symmetric_boundary_comparison_v1":
        before, after = operands.get("before"), operands.get("after")
        if before is None or after is None:
            return {"delta": None, "mean": None}
        return {
            "delta": _int(_d(after) - _d(before)),
            "mean": (_d(after) + _d(before)) / 2,
        }
    if formula_id in {
        "explicit_cohort_comparison_v1",
        "observational_cohort_comparison_v1",
        "completed_allowance_cycle_comparison_v1",
    }:
        cohort_left = operands.get("left")
        cohort_right = operands.get("right")
        return {
            "left": cohort_left,
            "right": cohort_right,
            "delta": (
                None
                if cohort_left is None or cohort_right is None
                else _int(_d(cohort_right) - _d(cohort_left))
            ),
        }
    if formula_id == "structural_workflow_features_v1":
        features = operands.get("structural_features")
        if not isinstance(features, Mapping):
            raise FormulaOperandError("structural_features must be an object")
        frequency = operands.get("frequency")
        if frequency is None:
            raise FormulaOperandError("frequency is required")
        return {
            "failure_coverage": _ratio(
                operands.get("failure_count"),
                operands.get("observed_sequences"),
            ),
            "frequency": _int(_d(frequency)),
            "mutation_coverage": _ratio(
                operands.get("mutation_count"),
                operands.get("observed_sequences"),
            ),
            "structural_features": {
                key: features[key]
                for key in sorted(features)
            },
        }
    if formula_id == "investigation_feature_vector_v1":
        features = operands.get("candidate_features")
        if not isinstance(features, Mapping) or not features:
            raise FormulaOperandError("candidate_features must be a nonempty object")
        normalized = {}
        for key in sorted(features):
            value = features[key]
            normalized[key] = None if value is None else _int(_d(value))
        return normalized
    if formula_id == "semantic_occurrence_reconciliation_v1":
        manifestation_count = operands.get("manifestation_count")
        semantic_entity_count = operands.get("semantic_entity_count")
        return {
            "excluded_occurrence_count": (
                None
                if manifestation_count is None or semantic_entity_count is None
                else _int(_d(manifestation_count) - _d(semantic_entity_count))
            ),
            "semantic_entity_count": semantic_entity_count,
        }
    raise FormulaOperandError(f"formula has no operation: {formula_id}")
