from __future__ import annotations

from decimal import Decimal

import pytest

from codex_usage_tracker.agent_kernel.query.contracts import (
    EvidenceSelection,
    Publication,
    QueryBatchRequest,
    QueryBatchResult,
    QueryContractError,
    QueryPage,
    QueryRequest,
    QueryResult,
    request_sha256,
    result_sha256,
    serialize_batch_result,
    serialize_request,
    serialize_result,
)


def _request(parameters: dict[str, object] | None = None) -> QueryRequest:
    return QueryRequest(
        question_id="Q-SYN-01",
        plan_id="synthetic_plan",
        plan_version=1,
        parameters=parameters or {"window": {"start_us": 0, "end_us": 10}},
        gates={"history": True},
        required_evidence=(
            EvidenceSelection(
                role="publication",
                selector_kind="publication",
                selector_id="publication:v1:synthetic",
            ),
        ),
        page=QueryPage(limit=5),
    )


def test_request_and_result_are_deeply_immutable_and_decimal_serialization_is_canonical() -> None:
    parameters = {"window": {"start_us": 0, "end_us": 10}, "ratio": Decimal("1.00")}
    request = _request(parameters)
    parameters["window"]["start_us"] = 99  # type: ignore[index]

    assert request.parameters["window"]["start_us"] == 0  # type: ignore[index]
    assert b'"ratio":"1"' in serialize_request(request)
    assert request_sha256(request) == request_sha256(_request({"window": {"start_us": 0, "end_us": 10}, "ratio": Decimal("1") }))

    result = QueryResult(
        question_id=request.question_id,
        plan_id=request.plan_id,
        plan_version=request.plan_version,
        publication=Publication("publication:v1:synthetic", 20, 10),
        grades={"ratio": "deterministic"},
        metrics={"ratio": Decimal("2.5000")},
        rows=({"value": Decimal("0.00")},),
        evidence_selectors=request.required_evidence,
        request_digest=request_sha256(request),
    )
    assert b'"ratio":"2.5"' in serialize_result(result)
    assert len(result_sha256(result)) == 64

    batch = QueryBatchResult(
        request_id="synthetic-batch",
        publication=result.publication,
        results=(result,),
    )
    encoded = serialize_batch_result(batch)
    assert b'"request_id":"synthetic-batch"' in encoded
    assert encoded.count(b'"publication":{') == 1


def test_batch_is_atomic_bounded_and_publication_bound() -> None:
    request = _request()
    batch = QueryBatchRequest("synthetic-batch", (request,))
    assert batch.plans == (request,)

    with pytest.raises(QueryContractError, match="1 through 8"):
        QueryBatchRequest("empty", ())
    with pytest.raises(QueryContractError, match="repeat"):
        QueryBatchRequest("duplicate", (request, request))
    with pytest.raises(QueryContractError, match="publication"):
        QueryBatchRequest(
            "mismatch",
            (
                QueryRequest(
                    request.question_id,
                    request.plan_id,
                    request.plan_version,
                    request.parameters,
                    request.gates,
                    request.required_evidence,
                    expected_publication_id="publication:v1:other",
                ),
            ),
            expected_publication_id="publication:v1:synthetic",
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: QueryPage(limit=0),
        lambda: QueryPage(limit=101),
        lambda: QueryPage(cursor=" "),
        lambda: EvidenceSelection("role", "window", "placeholder"),
        lambda: Publication("publication", 1, 2),
        lambda: _request({"sql": "SELECT 1"}),
    ],
)
def test_contracts_reject_unbounded_or_malformed_values(factory) -> None:
    with pytest.raises(QueryContractError):
        factory()


def test_result_rejects_non_contract_grades_and_non_digest_request_binding() -> None:
    with pytest.raises(QueryContractError, match="unsupported grade"):
        QueryResult(
            "Q-SYN-01",
            "synthetic_plan",
            1,
            Publication("publication:v1:synthetic", 20, 10),
            {"value": "approximate"},
        )
    with pytest.raises(QueryContractError, match="SHA-256"):
        QueryResult(
            "Q-SYN-01",
            "synthetic_plan",
            1,
            Publication("publication:v1:synthetic", 20, 10),
            {"value": "exact"},
            request_digest="not-a-digest",
        )
