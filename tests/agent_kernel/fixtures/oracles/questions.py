from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from tests.agent_kernel.fixtures.generator.profile import FixtureProfile
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger

_SHARE_FORMULAS = {
    "cached_share_v1",
    "completion_cohort_ratio_v1",
    "context_component_coverage_v1",
    "context_growth_v1",
    "context_pressure_v1",
    "hhi_v1",
    "later_earlier_median_ratio_v1",
    "mutation_density_v1",
    "observed_share_v1",
    "top_n_share_v1",
    "top_share_v1",
    "valuation_coverage_v1",
}
_DELTA_FORMULAS = {
    "consecutive_delta_v1",
    "equal_window_delta_v1",
    "side_by_side_delta_v1",
    "signed_driver_contribution_v1",
    "signed_driver_reconciliation_v1",
    "symmetric_boundary_comparison_v1",
}


def question_oracle_records(
    catalog: dict[str, Any],
    profile: FixtureProfile,
    *,
    ledger: SourceLedger,
) -> dict[str, dict[str, Any]]:
    """Derive every expected row from its explicit emitted structural case."""

    records: dict[str, dict[str, Any]] = {}
    for question in catalog["questions"]:
        for oracle_id in question["oracle_ids"]:
            source = ledger.question_cases[oracle_id]
            variant = oracle_id.rsplit(":", maxsplit=1)[-1]
            records[oracle_id] = {
                "caveats": source.caveats,
                "contract": source.contract,
                "expected": {
                    "coverage_requirements": question["coverage_requirements"],
                    "field_grades": question["answers"]["fields"],
                    "formulas": question["answers"]["formulas"],
                    "order": question["order"],
                    "row": source.observed_facts,
                },
                "limits": question["limits"],
                "lower_model_hint": question["lower_model_hint"],
                "oracle_id": oracle_id,
                "performance_classes": question["performance_classes"],
                "prohibited_claims": question["prohibited_claims"],
                "question_id": question["question_id"],
                "request": {
                    "parameters": source.inputs["parameters"],
                    "plan_id": question["plan_id"],
                },
                "required_selectors": question["evidence"]["selector_kinds"],
                "selectors": source.selectors,
                "source_case": {
                    "coordinate": source.coordinate,
                    "input_digest": source.input_digest,
                    "inputs": source.inputs,
                },
                "truth_case": source.contract["plan_id"],
                "variant": variant,
            }
    return dict(sorted(records.items()))


def _decimal_between_zero_and_one(value: Any) -> bool:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return Decimal(0) <= number <= Decimal(1)


def _check_token_formulas(
    row: dict[str, Any],
    inputs: dict[str, Any],
    formulas: set[str],
) -> list[str]:
    failures: list[str] = []
    tokens = inputs["tokens"]
    cached = tokens["cached_input_tokens"]
    uncached = tokens["uncached_input_tokens"]
    output = tokens["output_tokens"]
    expected_input = None if cached is None else uncached + cached
    expected_total = None if expected_input is None else expected_input + output
    if (
        "total_input_tokens_v1" in formulas
        and "total_input_tokens" in row
        and row["total_input_tokens"] != expected_input
    ):
        failures.append("total_input_tokens does not reconcile")
    if (
        "total_tokens_v1" in formulas
        and "total_tokens" in row
        and row["total_tokens"] != expected_total
    ):
        failures.append("total_tokens does not reconcile")
    if "cached_share_v1" in formulas:
        expected = (
            None
            if expected_input is None or cached is None
            else Decimal(cached) / Decimal(expected_input)
        )
        actual = row.get("cached_share")
        if expected is None:
            if actual is not None:
                failures.append("cached_share should be missing")
        elif Decimal(str(actual)) != expected:
            failures.append("cached_share does not reconcile")
    if "cached_output_ratio_v1" in formulas:
        expected = None if cached is None or output == 0 else Decimal(cached) / Decimal(
            output
        )
        actual = row.get("cached_output_ratio")
        if expected is None:
            if actual is not None:
                failures.append("cached_output_ratio should be missing")
        elif Decimal(str(actual)) != expected:
            failures.append("cached_output_ratio does not reconcile")
    return failures


def question_formula_failures(record: dict[str, Any]) -> list[str]:
    """Validate formula relationships independently of case generation."""

    failures: list[str] = []
    row = record["expected"]["row"]
    inputs = record["source_case"]["inputs"]
    formulas = set(record["expected"]["formulas"])
    if set(row) != set(record["expected"]["field_grades"]):
        failures.append("answer fields differ from contract")
    failures.extend(_check_token_formulas(row, inputs, formulas))

    if formulas & _DELTA_FORMULAS:
        expected = inputs["current"] - inputs["previous"]
        if "total_delta" in row and row["total_delta"] != expected:
            failures.append("total_delta does not reconcile")
        if (
            "driver_contribution" in row
            and "total_delta" in row
            and row["driver_contribution"] != row["total_delta"]
        ):
            failures.append("driver contribution does not reconcile")
        if "token_delta" in row and row["token_delta"] != expected:
            failures.append("token_delta does not reconcile")

    for field, value in row.items():
        if (
            (
                field.endswith(("_share", "_coverage"))
                or field
                in {
                    "context_growth",
                    "context_pressure",
                    "later_earlier_ratio",
                    "share",
                    "top_share",
                    "remainder_share",
                }
            )
            and value is not None
            and not _decimal_between_zero_and_one(value)
        ):
            failures.append(f"{field} is outside the closed ratio domain")

    if "second_difference_v1" in formulas and row.get("second_difference") != 0:
        failures.append("second_difference does not reconcile")
    if "half_open_interval_membership_v1" in formulas and not isinstance(
        row.get("included_in_interval"), bool
    ):
        failures.append("half-open membership is not boolean")
    if "observed_duration_v1" in formulas:
        duration = row.get("duration_us", row.get("tool_duration_us", 0))
        if duration <= 0:
            failures.append("observed duration is not positive")
    if "adjacent_event_gap_v1" in formulas and row.get("event_gap_us", 0) <= 0:
        failures.append("adjacent event gap is not positive")
    if "compatible_allowance_interval_v1" in formulas:
        compatibility = row.get("boundary_compatibility")
        if "boundary_compatibility" in row and not isinstance(compatibility, dict):
            failures.append("allowance compatibility facts are absent")
    return failures
