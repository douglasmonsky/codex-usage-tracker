"""Independent structural-v2 question evaluator for CK-07A."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    PlanRequest,
    evaluate_plan,
)
from tests.agent_kernel.fact_adapters.reference import (
    StructuralReferenceFactAdapter,
)
from tests.agent_kernel.fact_adapters.support import plan_contract, selector_contract
from tests.agent_kernel.fixtures.oracles.exact import exact_sha256, normalize_exact


def _request(value: Mapping[str, Any]) -> PlanRequest:
    return PlanRequest(
        plan_id=str(value["plan_id"]),
        parameters=dict(value["parameters"]),
        gates=dict(value["gates"]),
    )


def _references(materialized: Any) -> list[dict[str, Any]]:
    return [
        normalize_exact(
            {
                "role": item.role,
                "selector_kind": item.selector_kind,
                "selector": item.selector,
                "logical_id": item.logical_id,
                "provenance_kind": item.provenance_kind,
                "provenance": item.provenance,
            }
        )
        for item in materialized.evidence_references
    ]


def evaluate_question_case(
    case: Mapping[str, Any],
    question_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one case without SQLite, database replay, or grading output."""

    request = _request(case["request"])
    contract = plan_contract()
    materialized = StructuralReferenceFactAdapter(
        contract,
        selector_contract(),
    ).materialize(
        case["declaration"],
        request,
        case["required_evidence"],
    )
    evaluation = evaluate_plan(contract, materialized.request, materialized.facts)
    rows = normalize_exact(evaluation.rows)
    result = {
        "oracle_id": str(case["oracle_id"]),
        "question_id": str(case["question_id"]),
        "variant": str(case["variant"]),
        "request_digest": exact_sha256(
            {
                "gates": request.gates,
                "parameters": request.parameters,
                "plan_id": request.plan_id,
            }
        ),
        "rows": rows,
        "references": _references(materialized),
    }
    result["comparison_digest"] = exact_sha256(result)
    return result
