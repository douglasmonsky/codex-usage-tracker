from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.query.contracts import (
    EvidenceSelection,
    QueryPage,
    QueryRequest,
)
from codex_usage_tracker.agent_kernel.query.registry import (
    QueryPlanNotAdmittedError,
    QueryRegistryError,
    build_registry,
)

_FACT_ORDER = [
    "event_at_us_is_null",
    "event_at_us",
    "source_rank",
    "source_order",
    "event_kind_order",
    "logical_id",
    "transition_rank",
]
_ROOT = Path(__file__).resolve().parents[3]


def _authorities() -> tuple[dict, dict, dict, dict]:
    questions = []
    plans = []
    bindings = []
    for index in range(40):
        if index == 0:
            question_id, plan_id, required = "Q-ALW-02", "allowance_interval_events", ["start_observation", "end_observation"]
        elif index == 1:
            question_id, plan_id, required = "Q-OPS-01", "latest_publication_delta", []
        else:
            question_id, plan_id, required = f"Q-SYN-{index:02d}", f"synthetic_plan_{index:02d}", ["window"]
        optional = []
        parameter_declarations = {name: {"type": "string"} for name in required}
        question = {
            "question_id": question_id,
            "version": 1,
            "title": f"Synthetic question {index}",
            "plan_id": plan_id,
            "support_classes": ["N"],
            "stage": "Foundation",
            "intent_phrases": [f"synthetic intent {index}"],
            "parameters": {"required": required, "optional": optional},
            "required_capabilities": ["synthetic_capability"],
            "required_measurements": ["synthetic_measurement"],
            "logical_plan": {"primitives": ["synthetic_fact"], "operations": ["rows"], "compiler_id": None},
            "answers": {"fields": {"value": "exact"}, "formulas": [], "kernel_conclusion_fields": []},
            "coverage_requirements": ["history"],
            "evidence": {"classes": ["E0"], "selector_kinds": ["publication"]},
            "order": ["logical_id_asc"],
            "limits": {"default_rows": 1, "maximum_rows": 10, "exact_count_default": False},
            "performance_classes": ["P0"],
        }
        questions.append(question)
        plans.append({
            "question_id": question_id,
            "plan_id": plan_id,
            "status": "resolved",
            "blocked_reason": None,
            "request_schema": {"required": parameter_declarations, "optional": {}, "additional_parameters": False},
            "permitted_sources": [{"relation": "synthetic_fact", "fields": ["logical_id", "value"]}],
            "gates": ["history"],
            "fact_order": _FACT_ORDER,
            "result_order": ["logical_id_asc"],
        })
        bindings.append({"question_id": question_id, "fields": [{"field": "value", "classification": "direct_fact"}], "internal_formula_ids": []})
    return (
        {
            "schema": "codex-usage-tracker.question-catalog.v1",
            "version": 1,
            "questions": questions,
            "evidence_classes": [{"id": "E0", "selector_kinds": ["publication"]}],
            "performance_classes": [{"id": "P0", "sql_p95_ms": 10, "mcp_p95_ms": 250, "query_calls": 1, "evidence_calls": 0, "response_bytes": 4096}],
        },
        {
            "schema": "codex-usage-tracker.plan-operand-contract.v1",
            "version": 1,
            "plans": plans,
        },
        {
            "schema": "codex-usage-tracker.formula-contract.v1",
            "version": 1,
            "formulas": [],
            "answer_field_bindings": bindings,
            "formula_uses": [],
        },
        {
            "schema": "codex-usage-tracker.selector-provenance.v1",
            "version": 1,
            "selector_kinds": ["publication"],
            "ownership": [{"kind": "publication", "provenance_kind": "publication_identity"}],
            "provenance_contracts": [{"kind": "publication_identity"}],
            "plan_scope_sources": [
                {"question_id": "Q-ALW-02", "plan_id": "allowance_interval_events", "variants": ["empty_interval", "same_time_boundary"], "scope_source": "allowance_observation_pair"},
                {"question_id": "Q-OPS-01", "plan_id": "latest_publication_delta", "variants": ["no_change", "recanonicalized_owner"], "scope_source": "latest_accepted_publication_delta"},
            ],
        },
    )


def _request(question_id: str, plan_id: str, parameters: dict[str, object]) -> QueryRequest:
    return QueryRequest(
        question_id,
        plan_id,
        1,
        parameters,
        {"history": True},
        (EvidenceSelection("publication", "publication", "publication:v1:synthetic"),),
        page=QueryPage(limit=5),
    )


def test_registry_reconciles_exactly_40_entries_and_keeps_owner_scopes_windowless() -> None:
    registry = build_registry(*_authorities())
    assert len(registry.entries) == 40
    assert registry.get("Q-ALW-02").request_schema["required"] == {
        "start_observation": {"type": "string"},
        "end_observation": {"type": "string"},
    }
    assert registry.get("Q-OPS-01").request_schema["required"] == {}
    registry.validate(_request("Q-ALW-02", "allowance_interval_events", {"start_observation": "a", "end_observation": "b"}))
    registry.validate(_request("Q-OPS-01", "latest_publication_delta", {}))


@pytest.mark.parametrize("mutation", [
    lambda authorities: authorities[0]["questions"].pop(),
    lambda authorities: authorities[1]["plans"][0].update({"status": "blocked"}),
    lambda authorities: authorities[1]["plans"][0].update({"plan_id": "wrong_plan"}),
    lambda authorities: authorities[3]["plan_scope_sources"].pop(),
])
def test_registry_fails_closed_on_unresolved_or_mismatched_authority(mutation) -> None:
    authorities = deepcopy(_authorities())
    mutation(authorities)
    with pytest.raises(QueryRegistryError):
        build_registry(*authorities)


def test_request_validation_rejects_unknown_parameters_wrong_plan_and_excess_page() -> None:
    registry = build_registry(*_authorities())
    with pytest.raises(QueryRegistryError, match="parameters mismatch"):
        registry.validate(_request("Q-SYN-02", "synthetic_plan_02", {"unknown": "value"}))
    with pytest.raises(QueryRegistryError, match="does not match"):
        registry.validate(_request("Q-SYN-02", "wrong_plan", {"window": "value"}))
    with pytest.raises(QueryRegistryError, match="maximum"):
        registry.validate(
            QueryRequest(
                "Q-SYN-02",
                "synthetic_plan_02",
                1,
                {"window": "value"},
                {"history": True},
                (EvidenceSelection("publication", "publication", "publication:v1:synthetic"),),
                page=QueryPage(limit=11),
        )
    )


def test_real_registry_admits_only_21_foundation_and_cutover_plans() -> None:
    def load(name: str) -> dict[str, object]:
        return json.loads(
            (_ROOT / "config" / "agent-kernel" / name).read_text(encoding="utf-8")
        )

    registry = build_registry(
        load("question-catalog-v1.json"),
        load("plan-operand-contract-v1.json"),
        load("formula-contract-v1.json"),
        load("selector-provenance-v1.json"),
    )

    assert len(registry.entries) == 40
    assert sum(entry.admitted for entry in registry.entries) == 21
    advanced = registry.get("Q-CTX-03")
    assert advanced.stage == "Advanced"
    with pytest.raises(QueryPlanNotAdmittedError, match="not admitted"):
        registry.validate(
            QueryRequest(
                advanced.question_id,
                advanced.plan_id,
                advanced.plan_version,
                {},
                {},
                (),
            )
        )
