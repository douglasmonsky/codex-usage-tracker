"""Independent query-only database-v1 question evaluator for CK-07A."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    PlanRequest,
    evaluate_plan,
)
from codex_usage_tracker.agent_kernel.query.compiler import DatabaseV1FactCompiler
from tests.agent_kernel.fact_adapters.support import plan_contract, selector_contract
from tests.agent_kernel.fixtures.oracles.exact import exact_sha256, normalize_exact


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


def evaluate_published_question_case(
    connection: sqlite3.Connection,
    request_value: Mapping[str, Any],
    required_evidence: Sequence[Mapping[str, Any]],
    question_contract: Mapping[str, Any],
    *,
    oracle_id: str,
    variant: str,
) -> dict[str, Any]:
    """Evaluate one request from one query-only database-v1 snapshot."""

    request = PlanRequest(
        plan_id=str(request_value["plan_id"]),
        parameters=dict(request_value["parameters"]),
        gates=dict(request_value["gates"]),
    )
    contract = plan_contract()
    if connection.in_transaction:
        raise RuntimeError("published replay requires a caller-free read transaction")
    connection.execute("BEGIN")
    try:
        materialized = DatabaseV1FactCompiler(
            contract,
            selector_contract(),
            required_evidence,
        ).compile(
            connection,
            request,
            required_evidence=required_evidence,
        )
        evaluation = evaluate_plan(contract, materialized.request, materialized.facts)
    finally:
        connection.execute("ROLLBACK")
    rows = normalize_exact(evaluation.rows)
    result = {
        "oracle_id": oracle_id,
        "question_id": str(question_contract["question_id"]),
        "variant": variant,
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
