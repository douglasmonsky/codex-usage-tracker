from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FactCoordinates,
    FormulaInvocation,
    PlanEvaluation,
    PlanMaterialization,
    PlanOperandContractError,
    PlanRequest,
    _validate_materialization,
    compile_plan_operands,
    evaluate_plan,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = _ROOT / "config/agent-kernel/plan-operand-contract-v1.json"
_SCHEMA = _ROOT / "config/agent-kernel/plan-operand-contract-v1.schema.json"
_CATALOG = _ROOT / "config/agent-kernel/question-catalog-v1.json"
_FORMULAS = _ROOT / "config/agent-kernel/formula-contract-v1.json"
_VECTORS = _ROOT / "tests/agent_kernel/contracts/vectors/plan-operands-v1.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"decimal"}:
        return Decimal(value["decimal"])
    if isinstance(value, dict):
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _normalized(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if is_dataclass(value):
        return {
            item.name: _normalized(getattr(value, item.name))
            for item in dataclass_fields(value)
        }
    if isinstance(value, Mapping):
        return {key: _normalized(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(
        _normalized(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _plan(contract: dict[str, Any], plan_id: str) -> dict[str, Any]:
    return next(item for item in contract["plans"] if item["plan_id"] == plan_id)


def _request(plan: dict[str, Any]) -> PlanRequest:
    values: dict[str, Any] = {}
    for name, declaration in plan["request_schema"]["required"].items():
        if name == "window":
            values[name] = {"start_us": 0, "end_us": 100}
        elif name == "current_window":
            values[name] = {"start_us": 50, "end_us": 100}
        elif name == "previous_window":
            values[name] = {"start_us": 0, "end_us": 50}
        elif name == "start_observation":
            values[name] = "observation:start"
        elif name == "end_observation":
            values[name] = "observation:end"
        elif declaration["type"] == "integer":
            values[name] = 100
        elif declaration["type"] == "object":
            values[name] = {
                "left": ["session:1"],
                "right": ["session:2"],
            }
        else:
            values[name] = "selected"
    values.update(
        {
            name: value
            for name, value in {
                "driver_dimension": "session",
                "entity_kind": "call",
                "family_mode": (
                    "root"
                    if plan["plan_id"] == "parent_subagent_usage"
                    else "project"
                ),
                "left_session": "session:1",
                "rate_card": "digest:1",
                "right_session": "session:2",
            }.items()
            if name in values
        }
    )
    if plan["plan_id"] == "token_acceleration":
        values["minimum_samples"] = 3
    return PlanRequest(
        plan["plan_id"],
        values,
        {gate: True for gate in plan["gates"]},
    )


def _coordinates(at: int, order: int) -> FactCoordinates:
    return FactCoordinates(at, 0, order, 10, 0)


def _fact(
    plan: dict[str, Any],
    relation: str,
    logical_id: str,
    at: int,
    order: int,
    **overrides: Any,
) -> CanonicalFact:
    manifest = next(
        source["fields"]
        for source in plan["permitted_sources"]
        if source["relation"] == relation
    )
    values: dict[str, Any] = {}
    for name in manifest:
        if name == "resource_links":
            values[name] = ["resource:1"]
        elif name in {"occurrence_coordinates", "token_measurements"}:
            values[name] = {"basis": "observed"}
        elif name in {
            "capabilities",
            "measurements",
            "valuation_coverage",
        }:
            values[name] = {"status": "observed"}
        elif name == "compatibility_basis":
            values[name] = "compatible"
        elif name == "lifecycle":
            values[name] = "completed"
        elif name == "semantic_operation":
            values[name] = "inspect"
        elif name == "resource_kind":
            values[name] = "file"
        elif name == "write_intent":
            values[name] = False
        elif name == "tool_family":
            values[name] = "shell"
        elif name.endswith("_id"):
            values[name] = {
                "call_id": "call:1",
                "model_profile_id": "profile:1",
                "project_id": "project:1",
                "resource_id": "resource:1",
                "session_id": "session:1",
                "state_change_id": "change:1",
                "tool_id": "tool:1",
                "turn_id": "turn:1",
            }.get(name, f"{name}:1")
        elif name == "rate_card_digest":
            values[name] = "digest:1"
        elif name in {
            "configured_cost_usd",
            "estimated_credits",
        }:
            values[name] = Decimal("0.2500")
        elif name in {"lifecycle", "completion_basis"} or name in {"lifecycle_state", "completion_status"}:
            values[name] = "completed"
        elif name == "parent_session_id":
            values[name] = None
        else:
            values[name] = 1
    values.update(overrides)
    return CanonicalFact(relation, logical_id, values, _coordinates(at, order))


def _facts(plan: dict[str, Any]) -> list[CanonicalFact]:
    plan_id = plan["plan_id"]
    if plan_id == "current_usage":
        return [
            _fact(plan, "canonical_call", "call:1", 10, 1),
            _fact(plan, "valuation_match", "valuation:1", 10, 2),
        ]
    if plan_id == "model_effort_mix":
        return [_fact(plan, "canonical_call", "call:1", 10, 1)]
    if plan_id == "context_pressure_trajectory":
        return [
            _fact(plan, "canonical_call", "call:1", 10, 1),
            _fact(
                plan,
                "canonical_call",
                "call:2",
                20,
                3,
                call_id="call:2",
                uncached_input_tokens=3,
            ),
            _fact(
                plan,
                "canonical_call",
                "call:3",
                15,
                2,
                call_id="call:3",
                session_id="session:2",
                turn_id="turn:3",
                uncached_input_tokens=2,
            ),
            _fact(
                plan,
                "canonical_call",
                "call:4",
                25,
                4,
                call_id="call:4",
                session_id="session:2",
                turn_id="turn:4",
                uncached_input_tokens=4,
            ),
            _fact(
                plan,
                "compaction_boundary",
                "compaction:1",
                18,
                5,
                compaction_id="compaction:1",
            ),
        ]
    if plan_id == "token_acceleration":
        sequence = [
            (1, "session:1", "turn:1"),
            (2, "session:1", "turn:2"),
            (3, "session:1", "turn:2"),
            (4, "session:1", "turn:3"),
            (5, "session:2", "turn:4"),
            (6, "session:2", "turn:5"),
            (7, "session:2", "turn:5"),
            (8, "session:2", "turn:6"),
        ]
        return [
            _fact(
                plan,
                "canonical_call",
                f"call:{index}",
                index * 10,
                index,
                call_id=f"call:{index}",
                session_id=session_id,
                turn_id=turn_id,
                uncached_input_tokens=index,
                cached_input_tokens=index,
                output_tokens=index,
            )
            for index, session_id, turn_id in sequence
        ]
    if plan_id == "model_effort_transitions":
        return [
            _fact(
                plan,
                "canonical_call",
                f"call:{index}",
                index * 10,
                index,
                call_id=f"call:{index}",
                session_id=f"session:{1 if index <= 3 else 2}",
                turn_id=f"turn:{index}",
                model_profile_id=f"profile:{index}",
                uncached_input_tokens=index,
            )
            for index in range(1, 7)
        ]
    if plan_id == "retry_cycles":
        stages = [
            ("inspect", "completed", "resource:1"),
            ("execute", "completed", "resource:1"),
            ("execute", "failed", "resource:1"),
            ("inspect", "completed", "resource:1"),
            ("execute", "completed", "resource:1"),
            ("inspect", "completed", "resource:2"),
        ]
        return [
            _fact(
                plan,
                "tool_invocation",
                f"tool:{index}",
                index * 10,
                index,
                tool_id=f"tool:{index}",
                semantic_operation=operation,
                lifecycle=lifecycle,
                resource_id=resource_id,
                resource_links=[resource_id],
            )
            for index, (operation, lifecycle, resource_id) in enumerate(stages, 1)
        ]
    if plan_id == "allowance_interval_events":
        return [
            _fact(
                plan, "allowance_observation", "observation:start", 0, 1
            ),
            _fact(plan, "allowance_observation", "observation:end", 20, 2),
            _fact(plan, "canonical_call", "call:1", 10, 3),
        ]
    if plan_id == "repeated_resource_operations":
        return [
            _fact(plan, "tool_invocation", "tool:1", 10, 1),
            _fact(
                plan,
                "tool_invocation",
                "tool:2",
                20,
                2,
                tool_id="tool:2",
            ),
        ]
    if plan_id == "tool_family_behavior":
        return [
            _fact(plan, "tool_invocation", "tool:1", 10, 1),
            _fact(plan, "canonical_call", "call:1", 20, 2),
        ]
    if plan_id == "tool_following_activity":
        return [
            _fact(plan, "tool_invocation", "tool:1", 10, 1),
            _fact(plan, "canonical_call", "call:1", 20, 2),
        ]
    if plan_id == "tool_output_adjacency":
        return [
            _fact(plan, "canonical_call", "call:previous", 10, 1),
            _fact(plan, "tool_invocation", "tool:1", 20, 2),
            _fact(
                plan,
                "canonical_call",
                "call:following",
                30,
                3,
                call_id="call:following",
                uncached_input_tokens=3,
            ),
        ]
    if plan_id == "resource_hotspots":
        return [
            _fact(plan, "tool_invocation", "tool:1", 10, 1),
            _fact(plan, "state_change", "change:1", 20, 2),
        ]
    if plan_id == "tool_duration_gaps":
        return [
            _fact(plan, "tool_invocation", "tool:1", 10, 1),
            _fact(plan, "turn", "turn:1", 20, 2),
        ]
    if plan_id == "latest_publication_delta":
        return [_fact(plan, "publication_delta", "delta:1", 10, 1)]
    if plan_id == "evidence_timeline":
        return [_fact(plan, "canonical_call", "call:1", 10, 1)]
    if plan_id == "context_composition":
        return [_fact(plan, "context_component", "component:1", 10, 1)]
    if plan_id == "growth_without_mutation":
        return [
            _fact(plan, "canonical_call", "call:1", 10, 1),
            _fact(
                plan,
                "canonical_call",
                "call:2",
                20,
                2,
                call_id="call:2",
                context_window_tokens=2,
            ),
            _fact(plan, "turn", "turn:1", 10, 3),
        ]
    if plan_id == "data_health":
        return [_fact(plan, "publication", "publication:1", 10, 1)]
    if plan_id == "first_action_mutation":
        return [
            _fact(
                plan,
                "canonical_call",
                "canonical_call:1",
                10,
                1,
                call_id="call:1",
                session_id="session:1",
                turn_id="turn:1",
            ),
            _fact(
                plan,
                "tool_invocation",
                "tool_invocation:1",
                10,
                2,
                tool_id="tool:1",
                session_id="session:1",
                turn_id="turn:1",
                lifecycle="succeeded",
                start_at_us=10,
                start_source_rank=0,
                start_source_order=2,
                start_event_kind_order=10,
                start_transition_rank=0,
                terminal_at_us=11,
                terminal_source_rank=0,
                terminal_source_order=3,
                terminal_event_kind_order=10,
                terminal_transition_rank=1,
            ),
            _fact(
                plan,
                "state_change",
                "state_change:1",
                10,
                3,
                state_change_id="state_change:1",
                session_id="session:1",
                turn_id="turn:1",
                mutation_kind="modified",
            ),
        ]
    if plan_id == "compare_sessions":
        facts: list[CanonicalFact] = [
            _fact(
                plan,
                "canonical_call",
                "canonical_call:1",
                10,
                1,
                call_id="call:1",
                session_id="session:1",
                turn_id="turn:1",
                measurement_mask=16,
            ),
            _fact(
                plan,
                "canonical_call",
                "canonical_call:2",
                20,
                2,
                call_id="call:2",
                session_id="session:2",
                turn_id="turn:2",
                measurement_mask=16,
            ),
            _fact(
                plan,
                "resource",
                "resource:1",
                10,
                3,
                resource_id="resource:1",
            ),
            _fact(
                plan,
                "resource",
                "resource:2",
                20,
                4,
                resource_id="resource:2",
            ),
            _fact(
                plan,
                "session",
                "session:1",
                10,
                5,
                session_id="session:1",
                root_session_id="session:1",
                parent_session_id=None,
                delegation_depth=0,
            ),
            _fact(
                plan,
                "session",
                "session:2",
                20,
                6,
                session_id="session:2",
                root_session_id="session:2",
                parent_session_id=None,
                delegation_depth=0,
            ),
            _fact(
                plan,
                "state_change",
                "state_change:1",
                10,
                7,
                state_change_id="state_change:1",
                session_id="session:1",
                resource_id="resource:1",
                mutation_kind="modified",
            ),
            _fact(
                plan,
                "state_change",
                "state_change:2",
                20,
                8,
                state_change_id="state_change:2",
                session_id="session:2",
                resource_id="resource:2",
                mutation_kind="modified",
            ),
            _fact(
                plan,
                "tool_invocation",
                "tool_invocation:1",
                10,
                9,
                tool_id="tool:1",
                session_id="session:1",
                resource_id="resource:1",
                resource_links=["resource:1"],
                lifecycle="succeeded",
            ),
            _fact(
                plan,
                "tool_invocation",
                "tool_invocation:2",
                20,
                10,
                tool_id="tool:2",
                session_id="session:2",
                resource_id="resource:2",
                resource_links=["resource:2"],
                lifecycle="succeeded",
            ),
            _fact(
                plan,
                "turn",
                "turn:1",
                10,
                11,
                turn_id="turn:1",
                session_id="session:1",
            ),
            _fact(
                plan,
                "turn",
                "turn:2",
                20,
                12,
                turn_id="turn:2",
                session_id="session:2",
            ),
            _fact(
                plan,
                "publication",
                "publication:1",
                0,
                0,
                publication_id="publication:1",
                capabilities={"structural_context": True},
            ),
        ]
        return facts
    facts: list[CanonicalFact] = []
    for relation_index, source in enumerate(plan["permitted_sources"]):
        for item_index in range(2):
            logical_id = f"{source['relation']}:{item_index + 1}"
            overrides: dict[str, Any] = {}
            for field_name in source["fields"]:
                if field_name.endswith("_id"):
                    prefix = field_name.removesuffix("_id")
                    overrides[field_name] = f"{prefix}:{item_index + 1}"
            if "session_id" in source["fields"]:
                overrides["session_id"] = f"session:{item_index + 1}"
            facts.append(
                _fact(
                    plan,
                    source["relation"],
                    logical_id,
                    10 + item_index * 40,
                    relation_index * 10 + item_index,
                    **overrides,
                )
            )
    return facts


def test_schema_and_exact_reconciliation() -> None:
    contract, schema, catalog, formulas, vectors = (
        _load(_CONTRACT),
        _load(_SCHEMA),
        _load(_CATALOG),
        _load(_FORMULAS),
        _load(_VECTORS),
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(contract)
    assert len(contract["plans"]) == 40
    assert {plan["plan_id"] for plan in contract["plans"]} == {
        question["plan_id"] for question in catalog["questions"]
    }
    assert sum(len(plan["formula_uses"]) for plan in contract["plans"]) == 61
    assert sum(
        binding["classification"] == "direct_fact"
        for plan in contract["plans"]
        for binding in plan["answer_bindings"]
    ) == 112
    assert sum(
        binding["classification"] == "formula_output"
        for plan in contract["plans"]
        for binding in plan["answer_bindings"]
    ) == 73
    assert sum(len(plan["answer_fields"]) for plan in contract["plans"]) == 185
    assert all(plan["status"] == "resolved" for plan in contract["plans"])
    assert vectors["coverage"]["formula_uses"] == [
        use["use_id"]
        for plan in contract["plans"]
        for use in plan["formula_uses"]
    ]
    formula_uses = {
        (use["question_id"], use["plan_id"], use["formula_id"])
        for use in formulas["formula_uses"]
    }
    for plan in contract["plans"]:
        for use in plan["formula_uses"]:
            assert (plan["question_id"], plan["plan_id"], use["formula_id"]) in formula_uses
            assert (use["consume_as"] is not None) is use["internal_only"]


def test_all_static_known_answer_vectors_execute_and_match() -> None:
    contract, vectors = _load(_CONTRACT), _load(_VECTORS)
    assert len(vectors["cases"]) == 40
    observed_uses: set[str] = set()
    observed_fields: set[str] = set()
    for case in vectors["cases"]:
        request = PlanRequest(
            case["plan_id"],
            _decode(case["request"]["parameters"]),
            case["request"]["gates"],
        )
        facts = [
            CanonicalFact(
                item["relation"],
                item["logical_id"],
                _decode(item["values"]),
                FactCoordinates(**item["coordinates"]),
            )
            for item in case["facts"]
        ]
        materialization = compile_plan_operands(contract, request, facts)
        evaluation = evaluate_plan(contract, request, facts)
        assert _digest(materialization) == case["expected_materialization_sha256"]
        assert _digest(evaluation) == case["expected_evaluation_sha256"]
        assert _normalized(materialization.groups) == case["expected_groups"]
        assert _normalized([dict(group.key) for group in materialization.groups]) == case[
            "expected_group_keys"
        ]
        assert _normalized(evaluation.rows) == case["expected_rows"]
        observed_uses.update(case["formula_use_ids"])
        observed_fields.update(
            f"{_plan(contract, case['plan_id'])['question_id']}:{field}"
            for field in case["answer_fields"]
        )
    assert observed_uses == set(vectors["coverage"]["formula_uses"])
    assert observed_fields == set(vectors["coverage"]["answer_fields"])


def _replay_case(case: dict[str, Any]) -> tuple[PlanRequest, list[CanonicalFact]]:
    request = PlanRequest(
        case["plan_id"],
        _decode(case["request"]["parameters"]),
        case["request"]["gates"],
    )
    facts = [
        CanonicalFact(
            item["relation"],
            item["logical_id"],
            _decode(item["values"]),
            FactCoordinates(**item["coordinates"]),
        )
        for item in case["facts"]
    ]
    return request, facts


def test_static_negative_and_boundary_vectors_execute() -> None:
    contract, vectors = _load(_CONTRACT), _load(_VECTORS)
    cases = {case["case_id"]: case for case in vectors["cases"]}
    for negative in vectors["negative_cases"]:
        local_contract = deepcopy(contract)
        request, facts = _replay_case(cases[negative["base_case"]])
        operation = negative["operation"]
        if operation == "unknown_plan":
            request = PlanRequest("unknown", request.parameters, request.gates)
        elif operation == "unimplemented_symbol":
            _plan(local_contract, request.plan_id)["derivation_symbol"] = (
                "derive_missing_v1"
            )
        elif operation == "missing_parameter":
            parameters = dict(request.parameters)
            parameters.pop(next(iter(parameters)))
            request = PlanRequest(request.plan_id, parameters, request.gates)
        elif operation == "unknown_parameter":
            request = PlanRequest(
                request.plan_id, dict(request.parameters) | {"unknown": 1}, request.gates
            )
        elif operation in {"missing_gate", "unknown_gate"}:
            gates = dict(request.gates)
            if operation == "missing_gate":
                gates.pop(next(iter(gates)))
            else:
                gates["unknown"] = True
            request = PlanRequest(request.plan_id, request.parameters, gates)
        elif operation == "forbidden_relation":
            fact = facts[0]
            facts[0] = CanonicalFact(
                "forbidden", fact.logical_id, fact.values, fact.coordinates
            )
        elif operation in {
            "missing_source_field",
            "unknown_source_field",
            "malformed_numeric",
            "null_numeric",
            "forbidden_oracle_input",
            "nan_decimal",
            "positive_infinity_decimal",
            "negative_infinity_decimal",
        }:
            fact = facts[0]
            values = dict(fact.values)
            if operation == "missing_source_field":
                values.pop("output_tokens")
            elif operation == "unknown_source_field":
                values["unknown"] = 1
            elif operation == "malformed_numeric":
                values["uncached_input_tokens"] = "malformed"
            elif operation == "null_numeric":
                values["cached_input_tokens"] = None
            elif operation == "nan_decimal":
                values["uncached_input_tokens"] = Decimal("NaN")
            elif operation == "positive_infinity_decimal":
                values["uncached_input_tokens"] = Decimal("Infinity")
            elif operation == "negative_infinity_decimal":
                values["uncached_input_tokens"] = Decimal("-Infinity")
            else:
                values["oracle"] = "forbidden"
            if operation in {
                "forbidden_oracle_input",
                "nan_decimal",
                "positive_infinity_decimal",
                "negative_infinity_decimal",
            }:
                with pytest.raises(
                    PlanOperandContractError, match=negative["expected_error"]
                ):
                    CanonicalFact(
                        fact.relation, fact.logical_id, values, fact.coordinates
                    )
                continue
            facts[0] = CanonicalFact(
                fact.relation, fact.logical_id, values, fact.coordinates
            )
        elif operation == "missing_coordinates":
            fact = facts[0]
            facts[0] = CanonicalFact(
                fact.relation, fact.logical_id, fact.values, None
            )
        elif operation == "duplicate_coordinates":
            facts[1] = CanonicalFact(
                facts[1].relation,
                facts[0].logical_id,
                facts[1].values,
                facts[0].coordinates,
            )
        elif operation == "empty_facts":
            facts = []
        else:
            raise AssertionError(operation)
        if negative["expected_error"] is None:
            evaluation = evaluate_plan(local_contract, request, facts)
            if operation == "null_numeric":
                assert evaluation.rows[0]["total_tokens"] is None
            continue
        with pytest.raises(PlanOperandContractError, match=negative["expected_error"]):
            evaluate_plan(local_contract, request, facts)


def test_post_normalization_origin_parity_for_all_static_cases() -> None:
    contract, vectors = _load(_CONTRACT), _load(_VECTORS)
    for case in vectors["cases"]:
        request, scenario_facts = _replay_case(case)
        database_facts = [
            CanonicalFact(
                fact.relation,
                fact.logical_id,
                dict(reversed(tuple(fact.values.items()))),
                fact.coordinates,
            )
            for fact in reversed(scenario_facts)
        ]
        assert _digest(
            compile_plan_operands(contract, request, scenario_facts)
        ) == _digest(compile_plan_operands(contract, request, database_facts))
        assert _digest(evaluate_plan(contract, request, scenario_facts)) == _digest(
            evaluate_plan(contract, request, database_facts)
        )


@pytest.mark.parametrize(
    "plan_id", [plan["plan_id"] for plan in _load(_CONTRACT)["plans"]]
)
def test_every_resolved_symbol_executes(plan_id: str) -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, plan_id)
    evaluation = evaluate_plan(contract, _request(plan), _facts(plan))
    assert evaluation.plan_id == plan_id
    assert all(
        set(plan["answer_fields"]).issubset(row)
        for row in evaluation.rows
    )


def test_contract_and_registry_cover_exactly_all_symbols() -> None:
    contract = _load(_CONTRACT)
    from codex_usage_tracker.agent_kernel.domain.plan_operands import (
        _derivation_registry,
    )

    assert set(_derivation_registry()) == {
        plan["derivation_symbol"] for plan in contract["plans"]
    }
    registry = _derivation_registry()
    for plan in contract["plans"]:
        assert plan["grouping"]["derivation_rule"] in registry
        assert all(
            use["derivation_rule"]["symbol"] in registry
            for use in plan["formula_uses"]
        )
        assert all(
            binding["derivation_rule"] in registry
            for binding in plan["answer_bindings"]
        )


def test_decimal_serialization_is_exact_and_deterministic() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "current_usage")
    evaluation = evaluate_plan(contract, _request(plan), _facts(plan))
    encoded = evaluation.to_json()
    assert '"configured_cost_usd":"0.2500"' in encoded
    assert encoded == evaluation.to_json()


def test_bounded_adjacency_uses_immediate_complete_fact_order() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "tool_following_activity")
    materialization = compile_plan_operands(contract, _request(plan), _facts(plan))
    call = materialization.groups[0].formula_calls[0]
    assert call.operands == {
        "records": [{"id": "tool:1"}, {"id": "call:1"}]
    }
    evaluation = evaluate_plan(contract, _request(plan), _facts(plan))
    assert evaluation.rows[0]["intervening_events"] == [0]


def test_token_acceleration_aggregates_ordered_turns_and_enforces_minimum_samples() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "token_acceleration")
    request = _request(plan)
    facts = _facts(plan)

    materialization = compile_plan_operands(contract, request, facts)
    assert [group.direct_slots["turn_tokens"] for group in materialization.groups] == [
        [Decimal("3"), Decimal("15"), Decimal("12")],
        [Decimal("15"), Decimal("39"), Decimal("24")],
    ]
    first_calls = {
        call.formula_id: call.operands
        for call in materialization.groups[0].formula_calls
    }
    assert first_calls["later_earlier_median_ratio_v1"] == {
        "earlier": [Decimal("3")],
        "later": [Decimal("15"), Decimal("12")],
    }
    assert first_calls["second_difference_v1"] == {
        "current": Decimal("12"),
        "middle": Decimal("15"),
        "previous": Decimal("3"),
    }

    below_threshold = PlanRequest(
        plan["plan_id"],
        dict(request.parameters) | {"minimum_samples": 4},
        request.gates,
    )
    assert compile_plan_operands(contract, below_threshold, facts).groups == ()

    malformed = PlanRequest(
        plan["plan_id"],
        dict(request.parameters) | {"minimum_samples": "3"},
        request.gates,
    )
    with pytest.raises(PlanOperandContractError, match="must be 'integer'"):
        compile_plan_operands(contract, malformed, facts)

    non_positive = PlanRequest(
        plan["plan_id"],
        dict(request.parameters) | {"minimum_samples": 0},
        request.gates,
    )
    with pytest.raises(PlanOperandContractError, match="positive integer"):
        compile_plan_operands(contract, non_positive, facts)


def test_context_pressure_exposes_the_ordered_epoch_input_series() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "context_pressure_trajectory")
    evaluation = evaluate_plan(contract, _request(plan), _facts(plan))
    session_two = next(
        row
        for row in evaluation.rows
        if row["session_id"] == "session:2"
    )
    assert session_two["ordered_input_tokens"] == [Decimal("3"), Decimal("5")]


def test_tied_total_order_fails_closed() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "tool_following_activity")
    facts = _facts(plan)
    facts[1] = CanonicalFact(
        facts[1].relation,
        facts[0].logical_id,
        facts[1].values,
        facts[0].coordinates,
    )
    with pytest.raises(PlanOperandContractError, match="must be unique"):
        compile_plan_operands(contract, _request(plan), facts)


def test_missing_unknown_and_forbidden_fact_fields_fail_closed() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "current_usage")
    facts = _facts(plan)
    malformed = dict(facts[0].values)
    malformed.pop("output_tokens")
    facts[0] = CanonicalFact("canonical_call", "call:1", malformed, _coordinates(10, 1))
    with pytest.raises(PlanOperandContractError, match="missing required field"):
        compile_plan_operands(contract, _request(plan), facts)
    with pytest.raises(PlanOperandContractError, match="forbidden fact values"):
        CanonicalFact("canonical_call", "call:1", {"oracle": "forbidden"})


def test_unknown_or_unimplemented_derivation_fails_closed() -> None:
    contract = deepcopy(_load(_CONTRACT))
    plan = _plan(contract, "current_usage")
    plan["derivation_symbol"] = "derive_not_implemented_v1"
    with pytest.raises(PlanOperandContractError, match="unimplemented derivation"):
        compile_plan_operands(contract, _request(plan), _facts(plan))


def test_materialization_contract_fails_closed_on_group_formula_and_order_drift() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "top_sessions")
    materialization = compile_plan_operands(contract, _request(plan), _facts(plan))

    wrong_keys = deepcopy(plan)
    wrong_keys["grouping"]["keys"] = ["wrong_id"]
    with pytest.raises(PlanOperandContractError, match="grouping keys mismatch"):
        _validate_materialization(wrong_keys, materialization)

    wrong_cardinality = deepcopy(plan)
    wrong_cardinality["grouping"] = {
        "keys": [],
        "cardinality": "single",
        "derivation_rule": plan["derivation_symbol"],
    }
    with pytest.raises(PlanOperandContractError, match="single grouping"):
        _validate_materialization(wrong_cardinality, materialization)

    wrong_calls = deepcopy(plan)
    wrong_calls["formula_uses"][0]["derivation_rule"]["calls_per_group"] = 2
    with pytest.raises(PlanOperandContractError, match="multiplicity mismatch"):
        _validate_materialization(wrong_calls, materialization)

    reversed_groups = PlanMaterialization(
        materialization.plan_id, tuple(reversed(materialization.groups))
    )
    with pytest.raises(PlanOperandContractError, match="result ordering"):
        _validate_materialization(plan, reversed_groups)


def test_evaluator_rejects_missing_and_extra_answer_fields() -> None:
    contract = _load(_CONTRACT)
    plan = _plan(contract, "current_usage")

    missing = deepcopy(contract)
    _plan(missing, plan["plan_id"])["answer_fields"].append("undeclared_result")
    with pytest.raises(PlanOperandContractError, match="missing=.*undeclared_result"):
        evaluate_plan(missing, _request(plan), _facts(plan))

    extra = deepcopy(contract)
    _plan(extra, plan["plan_id"])["answer_fields"].remove("calls")
    with pytest.raises(PlanOperandContractError, match="extra=.*calls"):
        evaluate_plan(extra, _request(plan), _facts(plan))


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_nonfinite_numbers_fail_at_fact_operand_result_and_serialization_boundaries(
    value: Decimal,
) -> None:
    with pytest.raises(PlanOperandContractError, match="finite"):
        CanonicalFact("canonical_call", "call:1", {"value": value})
    with pytest.raises(PlanOperandContractError, match="finite"):
        FormulaInvocation("use:0", "formula", {"value": value}, {}, False, None)

    contract = _load(_CONTRACT)
    plan = _plan(contract, "current_usage")
    with pytest.raises(PlanOperandContractError, match="finite"):
        evaluate_plan(
            contract,
            _request(plan),
            _facts(plan),
            formula_evaluator=lambda _formula_id, _operands: value,
        )

    evaluation = PlanEvaluation(
        "synthetic",
        ({"value": value},),
    )
    with pytest.raises(PlanOperandContractError, match="finite"):
        evaluation.to_json()
