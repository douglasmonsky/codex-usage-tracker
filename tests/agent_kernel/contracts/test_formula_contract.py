from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from codex_usage_tracker.agent_kernel.domain.formulas import (
    FORMULA_IDS,
    FormulaOperandError,
    evaluate_formula,
)

_ROOT = Path(__file__).resolve().parents[3]
_CATALOG = _ROOT / "config/agent-kernel/question-catalog-v1.json"
_CONTRACT = _ROOT / "config/agent-kernel/formula-contract-v1.json"
_SCHEMA = _ROOT / "config/agent-kernel/formula-contract-v1.schema.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_ids() -> set[str]:
    catalog = _load(_CATALOG)
    return {
        formula
        for question in catalog["questions"]  # type: ignore[index]
        for formula in question["answers"].get("formulas", [])  # type: ignore[index,union-attr]
    }


def test_formula_contract_schema_and_catalog_reconcile_exactly() -> None:
    schema, contract = _load(_SCHEMA), _load(_CONTRACT)
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(contract)) == []
    contract_ids = {formula["id"] for formula in contract["formulas"]}  # type: ignore[index]
    assert contract_ids == _catalog_ids() == FORMULA_IDS
    assert len(contract_ids) == 45


def test_every_definition_carries_the_full_executable_semantic_contract() -> None:
    contract = _load(_CONTRACT)
    required = {
        "inputs",
        "fact_relations",
        "filtering",
        "grouping",
        "ordering",
        "null_empty_behavior",
        "numeric_types",
        "rounding",
        "units",
        "window_boundary_source",
        "result_shape",
        "operation",
        "symbol",
    }
    for formula in contract["formulas"]:  # type: ignore[index]
        assert required <= formula.keys()
        assert formula["operation"] == "evaluate_formula"
        assert formula["symbol"] == formula["id"]
        assert formula["inputs"] != ["normalized operands"]
        assert formula["fact_relations"] != ["canonical normalized facts named by inputs"]
        assert "Caller supplies grouping" not in formula["grouping"]
        assert (
            "No hidden filter is allowed" in formula["filtering"]
            or formula["id"] == "retry_sequence_matcher_v1"
        )
        assert "never from an emitted answer row" in formula["grouping"]
        assert formula["symbol"] in (
            _ROOT / "src/codex_usage_tracker/agent_kernel/domain/formulas.py"
        ).read_text(encoding="utf-8")


def test_answer_field_bindings_cover_catalog_fields_and_formula_uses() -> None:
    catalog, contract = _load(_CATALOG), _load(_CONTRACT)
    questions = {item["question_id"]: item for item in catalog["questions"]}  # type: ignore[index]
    bindings = {item["question_id"]: item for item in contract["answer_field_bindings"]}  # type: ignore[index]
    assert set(bindings) == set(questions)
    assert len(bindings) == 40
    assert sum(len(item["fields"]) for item in bindings.values()) == 185
    for question_id, binding in bindings.items():
        fields = binding["fields"]
        expected = set(questions[question_id]["answers"]["fields"])
        assert {item["field"] for item in fields} == expected
        assert len(fields) == len(expected)
        for item in fields:
            if item["classification"] == "formula_output":
                assert item["formula_id"] in questions[question_id]["answers"].get("formulas", [])
                assert item["formula_id"] in FORMULA_IDS
                assert item["output_key"]
        output_formulas = {
            item["formula_id"]
            for item in fields
            if item["classification"] == "formula_output"
        }
        internal_formulas = set(binding["internal_formula_ids"])
        question_formulas = set(
            questions[question_id]["answers"].get("formulas", [])
        )
        assert output_formulas.isdisjoint(internal_formulas)
        assert output_formulas | internal_formulas == question_formulas


def test_formula_use_contracts_lock_canonical_relations_and_request_gates() -> None:
    catalog, contract = _load(_CATALOG), _load(_CONTRACT)
    questions = {item["question_id"]: item for item in catalog["questions"]}  # type: ignore[index]
    uses = contract["formula_uses"]  # type: ignore[index]
    expected = {
        (question["question_id"], formula_id)
        for question in questions.values()
        for formula_id in question["answers"].get("formulas", [])
    }
    assert len(uses) == 61
    assert {(item["question_id"], item["formula_id"]) for item in uses} == expected
    for item in uses:
        question = questions[item["question_id"]]
        assert item["plan_id"] == question["plan_id"]
        assert item["canonical_relations"] == sorted(
            question["logical_plan"]["primitives"]
        )
        assert item["required_parameters"] == sorted(
            question["parameters"]["required"]
        )
        assert item["optional_parameters"] == sorted(
            question["parameters"]["optional"]
        )
        assert "answer, oracle, and grading fields are forbidden" in item[
            "operand_rule"
        ]
    for formula in contract["formulas"]:  # type: ignore[index]
        relations = sorted(
            {
                relation
                for item in uses
                if item["formula_id"] == formula["id"]
                for relation in item["canonical_relations"]
            }
        )
        assert formula["fact_relations"] == relations


_TOKEN_ROW = {"uncached_input_tokens": 4, "cached_input_tokens": 3, "output_tokens": 1}
_VECTORS = {
    "total_tokens_v1": ({"records": [_TOKEN_ROW]}, 8),
    "total_input_tokens_v1": ({"records": [_TOKEN_ROW]}, 7),
    "cached_share_v1": ({"numerator": 1, "denominator": 4}, Decimal("0.25")),
    "cached_output_ratio_v1": ({"numerator": 1, "denominator": 4}, Decimal("0.25")),
    "observed_share_v1": ({"numerator": 1, "denominator": 4}, Decimal("0.25")),
    "valuation_coverage_v1": ({"numerator": 1, "denominator": 4}, Decimal("0.25")),
    "completion_cohort_ratio_v1": ({"numerator": 1, "denominator": 4}, Decimal("0.25")),
    "equal_window_delta_v1": ({"current": 7, "previous": 4}, 3),
    "consecutive_delta_v1": ({"current": 7, "previous": 4}, 3),
    "side_by_side_delta_v1": ({"current": 7, "previous": 4}, 3),
    "adjacent_event_gap_v1": ({"current": 7, "previous": 4}, 3),
    "freshness_age_v1": ({"current": 7, "previous": 4}, 3),
    "second_difference_v1": ({"current": 7, "middle": 4, "previous": 2}, 1),
    "context_growth_v1": ({"last": 7, "first": 2}, 5),
    "trajectory_slope_v1": ({"values": [1, 3, 5]}, Decimal("2")),
    "later_earlier_median_ratio_v1": ({"later": [4, 6], "earlier": [1, 3]}, Decimal("2.5")),
    "context_pressure_v1": ({"input_tokens": 3, "context_window_tokens": 4}, Decimal("0.75")),
    "mutation_density_v1": ({"mutation_count": 3, "turn_count": 4}, Decimal("0.75")),
    "top_share_v1": ({"values": [1, 2, 3]}, Decimal("0.5")),
    "top_n_share_v1": (
        {"values": [1, 2, 3], "n": 2},
        {
            "top_share": Decimal("0.8333333333333333333333333333"),
            "remainder_share": Decimal("0.1666666666666666666666666667"),
        },
    ),
    "hhi_v1": ({"values": [1, 1]}, Decimal("0.50")),
    "accepted_mutation_summary_v1": (
        {
            "records": [
                {
                    "inserted_count": 1,
                    "removed_count": 2,
                    "corrected_count": 3,
                    "recanonicalized_count": 4,
                    "terminalized_count": 5,
                    "token_delta": 6,
                }
            ]
        },
        {
            "inserted_count": 1,
            "removed_count": 2,
            "corrected_count": 3,
            "recanonicalized_count": 4,
            "terminalized_count": 5,
            "token_delta": 6,
        },
    ),
    "half_open_interval_membership_v1": ({"start_us": 2, "end_us": 4, "event_time_us": 2}, True),
    "compatible_allowance_interval_v1": (
        {
            "left_provider": "codex",
            "right_provider": "codex",
            "left_limit": "weekly",
            "right_limit": "weekly",
            "left_plan": "team",
            "right_plan": "team",
            "left_window_kind": "rolling",
            "right_window_kind": "rolling",
            "left_reset": "r1",
            "right_reset": "r1",
            "left_observed_at_us": 1,
            "right_observed_at_us": 2,
        },
        True,
    ),
    "compatible_positive_allowance_ratio_v1": (
        {"compatible": True, "value": 8, "allowance_delta": 2},
        Decimal("4"),
    ),
    "signed_driver_contribution_v1": ({"current": 3, "previous": 5}, -2),
    "signed_driver_reconciliation_v1": (
        {"values": [2, 3], "total_delta": 7},
        {"drivers": 5, "unexplained": 2},
    ),
    "exclusive_inclusive_scope_v1": (
        {"inclusive": 10, "descendant": 3},
        {"exclusive": 7, "inclusive": 10},
    ),
    "current_valuation_v1": (
        {"records": [{"cost_usd": 2}, {"cost_usd": None}]},
        {"configured_cost_usd": 2, "rated_calls": 1, "unrated_calls": 1},
    ),
    "total_order_v1": (
        {
            "records": [
                {
                    "event_at_us": 1,
                    "source_rank": 0,
                    "source_order": 1,
                    "event_kind_order": 0,
                    "logical_id": "b",
                    "transition_rank": 0,
                },
                {
                    "event_at_us": 1,
                    "source_rank": 0,
                    "source_order": 1,
                    "event_kind_order": 0,
                    "logical_id": "a",
                    "transition_rank": 0,
                },
            ]
        },
        [
            {
                "event_at_us": 1,
                "source_rank": 0,
                "source_order": 1,
                "event_kind_order": 0,
                "logical_id": "a",
                "transition_rank": 0,
            },
            {
                "event_at_us": 1,
                "source_rank": 0,
                "source_order": 1,
                "event_kind_order": 0,
                "logical_id": "b",
                "transition_rank": 0,
            },
        ],
    ),
    "observed_duration_v1": ({"records": [{"duration_us": 4}, {"duration_us": 3}]}, 7),
    "bounded_adjacency_v1": (
        {"records": [{"id": "a"}, {"id": "b"}]},
        [{"left_id": "a", "right_id": "b", "intervening_events": 0}],
    ),
    "first_boundary_v1": (
        {
            "boundary_kind": "action",
            "records": [{"kind": "other", "tokens": 1}, {"kind": "action", "tokens": 2}],
        },
        2,
    ),
    "resource_revisit_v1": (
        {
            "records": [
                {"resource": "x", "operation": "read"},
                {"resource": "x", "operation": "read"},
            ]
        },
        {"revisit_count": 1, "revisit_distance": [1]},
    ),
    "retry_sequence_matcher_v1": (
        {
            "records": [
                {"id": str(index), "stage": stage, "resource": "file:a"}
                for index, stage in enumerate(
                    ("inspect", "attempt", "failure", "reinspect", "retry")
                )
            ]
        },
        {
            "retry_cycles": 1,
            "matched_events": [["0", "1", "2", "3", "4"]],
        },
    ),
    "consecutive_profile_transition_v1": (
        {
            "records": [
                {"profile": "a", "total_tokens": 2},
                {"profile": "b", "total_tokens": 5},
                {"profile": "b", "total_tokens": 7},
            ]
        },
        {"transition_count": 1, "token_delta": [3]},
    ),
    "resource_operation_breakdown_v1": (
        {"records": [{"operation": "read"}, {"operation": "read"}, {"operation": "write"}]},
        {"read": 2, "write": 1},
    ),
    "context_component_coverage_v1": (
        {"records": [{"bytes": 3}], "total_bytes": 5},
        {"component_bytes": 3, "unattributed_bytes": 2},
    ),
    "symmetric_boundary_comparison_v1": (
        {"before": 2, "after": 4},
        {"delta": 2, "mean": Decimal("3")},
    ),
    "explicit_cohort_comparison_v1": ({"left": 2, "right": 4}, {"left": 2, "right": 4, "delta": 2}),
    "observational_cohort_comparison_v1": (
        {"left": 2, "right": 4},
        {"left": 2, "right": 4, "delta": 2},
    ),
    "completed_allowance_cycle_comparison_v1": (
        {"left": 2, "right": 4},
        {"left": 2, "right": 4, "delta": 2},
    ),
    "structural_workflow_features_v1": (
        {
            "frequency": 2,
            "failure_count": 1,
            "mutation_count": 3,
            "observed_sequences": 4,
            "structural_features": {"tool_count": 2},
        },
        {
            "failure_coverage": Decimal("0.25"),
            "frequency": 2,
            "mutation_coverage": Decimal("0.75"),
            "structural_features": {"tool_count": 2},
        },
    ),
    "investigation_feature_vector_v1": (
        {"candidate_features": {"baseline_delta": 2, "coverage": 3}},
        {"baseline_delta": 2, "coverage": 3},
    ),
    "semantic_occurrence_reconciliation_v1": (
        {"manifestation_count": 5, "semantic_entity_count": 3},
        {"excluded_occurrence_count": 2, "semantic_entity_count": 3},
    ),
}


def test_every_catalog_formula_has_an_expected_synthetic_vector() -> None:
    assert set(_VECTORS) == FORMULA_IDS
    for formula_id, (operands, expected) in _VECTORS.items():
        assert evaluate_formula(formula_id, operands) == expected


def test_formula_output_bindings_name_real_evaluator_outputs() -> None:
    contract = _load(_CONTRACT)
    for question in contract["answer_field_bindings"]:  # type: ignore[index]
        for binding in question["fields"]:
            if binding["classification"] != "formula_output":
                continue
            expected = _VECTORS[binding["formula_id"]][1]
            output_key = binding["output_key"]
            if output_key == "$":
                continue
            if output_key.startswith("[]."):
                assert isinstance(expected, list)
                key = output_key.removeprefix("[].")
                assert all(key in row for row in expected)
            else:
                assert isinstance(expected, dict)
                assert output_key in expected


def test_numeric_ratios_and_token_totals_preserve_exact_types() -> None:
    assert (
        evaluate_formula(
            "total_tokens_v1",
            {
                "records": [
                    {
                        "uncached_input_tokens": 1,
                        "cached_input_tokens": 2,
                        "reasoning_tokens": 3,
                        "output_tokens": 4,
                    }
                ]
            },
        )
        == 7
    )
    assert (
        evaluate_formula(
            "total_tokens_v1",
            {
                "records": [
                    {
                        "uncached_input_tokens": 1,
                        "cached_input_tokens": None,
                        "reasoning_tokens": 3,
                        "output_tokens": 4,
                    }
                ]
            },
        )
        is None
    )
    assert evaluate_formula("cached_share_v1", {"numerator": 1, "denominator": 3}) == Decimal(
        1
    ) / Decimal(3)
    assert evaluate_formula("cached_share_v1", {"numerator": 0, "denominator": 0}) is None


def test_empty_ties_boundaries_and_invalid_operands_are_explicit() -> None:
    assert evaluate_formula("top_n_share_v1", {"values": []}) == {
        "top_share": None,
        "remainder_share": None,
    }
    assert (
        evaluate_formula(
            "total_order_v1",
            {
                "records": [
                    {
                        "event_at_us": None,
                        "source_rank": 0,
                        "source_order": 0,
                        "event_kind_order": 0,
                        "logical_id": "z",
                        "transition_rank": 0,
                    },
                    {
                        "event_at_us": 1,
                        "source_rank": 0,
                        "source_order": 0,
                        "event_kind_order": 0,
                        "logical_id": "a",
                        "transition_rank": 0,
                    },
                ]
            },
        )[0]["logical_id"]
        == "a"
    )
    assert (
        evaluate_formula(
            "half_open_interval_membership_v1", {"start_us": 1, "end_us": 2, "event_time_us": 2}
        )
        is False
    )
    with pytest.raises(FormulaOperandError, match="unknown formula ID"):
        evaluate_formula("unknown_v1", {})
    assert (
        evaluate_formula(
            "total_tokens_v1",
            {
                "records": [
                    {
                        "uncached_input_tokens": None,
                        "cached_input_tokens": 1,
                        "output_tokens": 1,
                    }
                ]
            },
        )
        is None
    )


def test_allowance_compatibility_requires_full_identity_and_time_order() -> None:
    compatible = dict(_VECTORS["compatible_allowance_interval_v1"][0])
    assert evaluate_formula("compatible_allowance_interval_v1", compatible) is True
    assert (
        evaluate_formula(
            "compatible_allowance_interval_v1",
            {**compatible, "right_reset": "r2"},
        )
        is False
    )
    assert (
        evaluate_formula(
            "compatible_allowance_interval_v1",
            {**compatible, "right_observed_at_us": 0},
        )
        is False
    )


def test_mutation_summary_preserves_missing_token_delta() -> None:
    row = dict(_VECTORS["accepted_mutation_summary_v1"][0]["records"][0])
    result = evaluate_formula(
        "accepted_mutation_summary_v1",
        {"records": [{**row, "token_delta": None}]},
    )
    assert result["inserted_count"] == 1
    assert result["token_delta"] is None


def test_retry_match_requires_all_five_contiguous_same_resource_stages() -> None:
    valid = _VECTORS["retry_sequence_matcher_v1"][0]["records"]
    different_resource = [
        {**row, "resource": "file:b" if index == 4 else row["resource"]}
        for index, row in enumerate(valid)
    ]
    interleaved = [*valid[:2], {"id": "x", "stage": "other", "resource": "file:a"}, *valid[2:]]
    open_retry = valid[:-1]
    for records in (different_resource, interleaved, open_retry):
        assert evaluate_formula(
            "retry_sequence_matcher_v1",
            {"records": records},
        ) == {"retry_cycles": 0, "matched_events": []}


def test_missing_measurements_propagate_null_without_false_zero() -> None:
    assert evaluate_formula(
        "context_component_coverage_v1",
        {"records": [{"bytes": None}], "total_bytes": 10},
    ) == {"component_bytes": None, "unattributed_bytes": None}
    assert evaluate_formula(
        "context_component_coverage_v1",
        {"records": [], "total_bytes": 10},
    ) == {"component_bytes": 0, "unattributed_bytes": 10}
    assert evaluate_formula(
        "context_growth_v1",
        {"first": 1, "last": None},
    ) is None
    assert evaluate_formula(
        "second_difference_v1",
        {"previous": 1, "middle": None, "current": 3},
    ) is None
    assert evaluate_formula(
        "symmetric_boundary_comparison_v1",
        {"before": None, "after": 3},
    ) == {"delta": None, "mean": None}


def test_formula_module_does_not_depend_on_other_evaluators() -> None:
    source = (_ROOT / "src/codex_usage_tracker/agent_kernel/domain/formulas.py").read_text(
        encoding="utf-8"
    )
    assert "sqlite" not in source.lower()
    assert "experiments" not in source
    assert "kernel." not in source
