from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.evidence.cursors import CursorCodec
from codex_usage_tracker.agent_kernel.query.contracts import (
    EvidenceSelection,
    QueryBatchRequest,
    QueryPage,
    QueryRequest,
)
from codex_usage_tracker.agent_kernel.query.registry import (
    QueryRegistryError,
    build_registry,
)
from codex_usage_tracker.agent_kernel.query.service import QueryService, QueryServiceError
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.oracles.exact import exact_sha256
from tests.agent_kernel.fixtures.oracles.reference import evaluate_question_case
from tests.agent_kernel.fixtures.published_v2 import (
    publish_structural_snapshot,
    published_question_case,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _ROOT / "config" / "agent-kernel"
_SECRET = b"ck08-query-service-synthetic-secret"


def _load(name: str) -> dict[str, object]:
    return json.loads((_CONFIG / name).read_text(encoding="utf-8"))


def _service() -> QueryService:
    catalog = _load("question-catalog-v1.json")
    operands = _load("plan-operand-contract-v1.json")
    formulas = _load("formula-contract-v1.json")
    selectors = _load("selector-provenance-v1.json")
    return QueryService(
        build_registry(catalog, operands, formulas, selectors),
        operands,
        selectors,
        CursorCodec(_SECRET, clock=lambda: 500),
        clock=lambda: 500,
    )


def _request(case: dict[str, object], question: dict[str, object]) -> QueryRequest:
    request = case["request"]
    assert isinstance(request, dict)
    required = case["required_evidence"]
    assert isinstance(required, list)
    limits = question["limits"]
    assert isinstance(limits, dict)
    return QueryRequest(
        question_id=str(case["question_id"]),
        plan_id=str(request["plan_id"]),
        plan_version=int(question["version"]),
        parameters=request["parameters"],  # type: ignore[arg-type]
        gates=request["gates"],  # type: ignore[arg-type]
        required_evidence=tuple(
            EvidenceSelection.from_mapping(item, index)
            for index, item in enumerate(required)
        ),
        page=QueryPage(limit=int(limits["maximum_rows"])),
    )


def test_service_replays_all_42_admitted_foundation_cutover_variants(
    tmp_path: Path,
) -> None:
    catalog = _load("question-catalog-v1.json")
    questions = {
        item["question_id"]: item
        for item in catalog["questions"]  # type: ignore[index]
        if item["stage"] in {"Foundation", "Cutover"}
    }
    cases = [
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] in questions
    ]
    assert len(cases) == 42
    comparison_digests: list[str] = []

    for index, original in enumerate(cases):
        profile = original["source_profile"]
        mutation = original["semantic_mutation"]
        database_path = tmp_path / f"case-{index:02d}" / "database-v1.sqlite3"
        publish_structural_snapshot(
            database_path.parent / "fixture",
            database_path,
            include_late_call=profile["late_event"],
            null_cached_tokens=profile["missing_cached_input"],
            variant_native_turn_id=mutation["native_turn_id"],
        )
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        case = published_question_case(connection, original)
        question = questions[case["question_id"]]
        expected = evaluate_question_case(case, question)
        connection.execute("PRAGMA query_only = ON")
        result = _service().execute(
            connection,
            QueryBatchRequest(
                request_id=f"synthetic-{index}",
                plans=(_request(case, question),),
            ),
        ).results[0]
        connection.close()

        references = [item.to_mapping() for item in result.evidence_selectors]
        result_rows = result.to_mapping()["rows"]
        assert result_rows == expected["rows"], case["oracle_id"]
        assert dict(result.grades) == question["answers"]["fields"], case["oracle_id"]
        assert references == expected["references"], case["oracle_id"]
        assert result.request_digest == expected["request_digest"]
        comparison = exact_sha256(
            {
                "oracle_id": case["oracle_id"],
                "question_id": case["question_id"],
                "variant": case["variant"],
                "request_digest": result.request_digest,
                "rows": result_rows,
                "references": references,
            }
        )
        assert comparison == expected["comparison_digest"]
        comparison_digests.append(comparison)

    assert len(set(comparison_digests)) == 42


def test_service_rejects_reduced_or_reframed_evidence_sequence(
    tmp_path: Path,
) -> None:
    connection, case, question = _published_case(
        tmp_path,
        question_id="Q-ACC-01",
        variant="boundaries",
    )
    base = _request(case, question)
    publication = base.required_evidence[0]
    reduced = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        (publication,),
        page=base.page,
    )
    with pytest.raises(QueryRegistryError, match="role/kind sequence"):
        _service().execute(connection, QueryBatchRequest("reduced-evidence", (reduced,)))

    reframed = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        (
            EvidenceSelection(
                role="unrelated",
                selector_kind=publication.selector_kind,
                selector_id=publication.selector_id,
                selector=publication.selector,
            ),
            *base.required_evidence[1:],
        ),
        page=base.page,
    )
    with pytest.raises(QueryRegistryError, match="role/kind sequence"):
        _service().execute(connection, QueryBatchRequest("reframed-evidence", (reframed,)))
    connection.close()


def _published_case(
    tmp_path: Path,
    *,
    question_id: str,
    variant: str,
) -> tuple[sqlite3.Connection, dict[str, object], dict[str, object]]:
    catalog = _load("question-catalog-v1.json")
    questions = {
        item["question_id"]: item
        for item in catalog["questions"]  # type: ignore[index]
    }
    original = next(
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] == question_id and item["variant"] == variant
    )
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database_path = tmp_path / "service" / "database-v1.sqlite3"
    publish_structural_snapshot(
        database_path.parent / "fixture",
        database_path,
        include_late_call=profile["late_event"],
        null_cached_tokens=profile["missing_cached_input"],
        variant_native_turn_id=mutation["native_turn_id"],
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    connection.execute("PRAGMA query_only = ON")
    return connection, case, questions[question_id]


def test_service_keyset_pages_have_no_gaps_or_duplicates_and_exact_count_is_opt_in(
    tmp_path: Path,
) -> None:
    connection, case, question = _published_case(
        tmp_path,
        question_id="Q-OPS-04",
        variant="equal_time_event",
    )
    base = _request(case, question)
    first_request = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        base.required_evidence,
        page=QueryPage(limit=7, include_exact_count=True),
    )
    first = _service().execute(
        connection,
        QueryBatchRequest("page-1", (first_request,)),
    ).results[0]
    assert first.page.returned_rows == 7
    assert first.page.exact_count == 31
    assert first.page.next_cursor is not None

    rows = list(first.rows)
    cursor = first.page.next_cursor
    page_number = 2
    while cursor is not None:
        request = QueryRequest(
            base.question_id,
            base.plan_id,
            base.plan_version,
            base.parameters,
            base.gates,
            base.required_evidence,
            expected_publication_id=first.publication.publication_id,
            page=QueryPage(limit=7, cursor=cursor),
        )
        page = _service().execute(
            connection,
            QueryBatchRequest(
                f"page-{page_number}",
                (request,),
                expected_publication_id=first.publication.publication_id,
            ),
        ).results[0]
        assert page.page.exact_count is None
        rows.extend(page.rows)
        cursor = page.page.next_cursor
        page_number += 1
    connection.close()

    assert len(rows) == 31
    assert len({exact_sha256(row) for row in rows}) == 31


def test_service_rejects_tampered_cursor_replacement_and_writer_connection(
    tmp_path: Path,
) -> None:
    connection, case, question = _published_case(
        tmp_path,
        question_id="Q-OPS-04",
        variant="equal_time_event",
    )
    base = _request(case, question)
    first_request = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        base.required_evidence,
        page=QueryPage(limit=1),
    )
    first = _service().execute(
        connection,
        QueryBatchRequest("cursor-source", (first_request,)),
    ).results[0]
    assert first.page.next_cursor is not None
    version, payload, signature = first.page.next_cursor.split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = ".".join((version, payload, signature))
    tampered_request = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        base.required_evidence,
        page=QueryPage(limit=1, cursor=tampered),
    )
    with pytest.raises(ValueError, match="signature|encoding"):
        _service().execute(
            connection,
            QueryBatchRequest("tampered", (tampered_request,)),
        )

    cursor_request = QueryRequest(
        base.question_id,
        base.plan_id,
        base.plan_version,
        base.parameters,
        base.gates,
        base.required_evidence,
        expected_publication_id="publication:v1:replacement",
        page=QueryPage(limit=1, cursor=first.page.next_cursor),
    )
    with pytest.raises(QueryServiceError, match="stale or replaced"):
        _service().execute(
            connection,
            QueryBatchRequest(
                "replacement",
                (cursor_request,),
                expected_publication_id="publication:v1:replacement",
            ),
        )

    connection.execute("PRAGMA query_only = OFF")
    with pytest.raises(QueryServiceError, match="query_only"):
        _service().execute(
            connection,
            QueryBatchRequest("writer", (base,)),
        )
    connection.close()


def test_service_rejects_unknown_and_unadmitted_plans_before_opening_snapshot(
    tmp_path: Path,
) -> None:
    connection, case, question = _published_case(
        tmp_path,
        question_id="Q-OPS-04",
        variant="equal_time_event",
    )
    base = _request(case, question)
    unknown = QueryRequest(
        "Q-UNKNOWN",
        "unknown_plan",
        1,
        {},
        {},
        base.required_evidence,
    )
    with pytest.raises(ValueError, match="unknown"):
        _service().execute(
            connection,
            QueryBatchRequest("unknown", (unknown,)),
        )

    catalog = _load("question-catalog-v1.json")
    advanced = next(
        item
        for item in catalog["questions"]  # type: ignore[index]
        if item["stage"] == "Advanced"
    )
    unadmitted = QueryRequest(
        str(advanced["question_id"]),
        str(advanced["plan_id"]),
        int(advanced["version"]),
        {},
        {},
        base.required_evidence,
    )
    with pytest.raises(ValueError, match="not admitted"):
        _service().execute(
            connection,
            QueryBatchRequest("unadmitted", (unadmitted,)),
        )
    connection.close()
