from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest
from codex_usage_tracker.agent_kernel.query.compiler import request_digest
from codex_usage_tracker.agent_kernel.query.page_executor import (
    SUPPORTED_DIRECT_PLAN_IDS,
    PageExecutionRequest,
    PhysicalPageError,
    PhysicalPageExecutor,
    PhysicalPlanGapError,
    physical_gap,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.published_v2 import (
    publish_structural_snapshot,
    published_question_case,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG = _ROOT / "config" / "agent-kernel"


def _assert_indexed_explain(
    plan_id: str,
    details: tuple[str, ...],
) -> None:
    upper = tuple(detail.upper() for detail in details)
    assert details
    assert not any(
        forbidden in detail
        for detail in upper
        for forbidden in ("SCAN ", "AUTOMATIC", "USE TEMP B-TREE")
    )
    required = {
        "data_health": (
            "SEARCH h USING PRIMARY KEY (singleton=?)",
            "SEARCH p USING PRIMARY KEY (publication_id=?)",
        ),
        "latest_publication_delta": (
            "SEARCH h USING PRIMARY KEY (singleton=?)",
            "SEARCH d USING PRIMARY KEY (publication_id=?)",
        ),
    }
    assert all(item in details for item in required[plan_id])


def _catalog() -> dict[str, dict[str, object]]:
    payload = json.loads(
        (_CONFIG / "question-catalog-v1.json").read_text(encoding="utf-8")
    )
    return {item["question_id"]: item for item in payload["questions"]}


def _published_request(
    tmp_path: Path,
    *,
    question_id: str,
    variant: str,
) -> tuple[
    sqlite3.Connection,
    PlanRequest,
    dict[str, object],
    str,
]:
    original = next(
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] == question_id and item["variant"] == variant
    )
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database_path = tmp_path / question_id / variant / "database-v1.sqlite3"
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
    request = case["request"]
    assert isinstance(request, dict)
    plan_request = PlanRequest(
        plan_id=str(request["plan_id"]),
        parameters=request["parameters"],  # type: ignore[arg-type]
        gates=request["gates"],  # type: ignore[arg-type]
    )
    publication_id = str(
        connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()[0]
    )
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection, plan_request, _catalog()[question_id], publication_id


def _request(
    plan_request: PlanRequest,
    question: dict[str, object],
    publication_id: str,
    *,
    page_size: int,
    cursor_order: tuple[object, ...] | None = None,
    include_exact_count: bool = False,
) -> PageExecutionRequest:
    order = question["order"]
    assert isinstance(order, list)
    return PageExecutionRequest(
        plan_id=plan_request.plan_id,
        plan_version=int(question["version"]),
        publication_id=publication_id,
        request_digest=request_digest(plan_request),
        complete_order=tuple(str(item) for item in order),
        page_size=page_size,
        cursor_order=cursor_order,
        include_exact_count=include_exact_count,
        parameters=plan_request.parameters,
    )


@pytest.mark.parametrize(
    ("question_id", "variant", "order_sql"),
    [
        (
            "Q-OPS-01",
            "no_change",
            "ORDER BY _order_change_kind ASC, _order_logical_id ASC",
        ),
        (
            "Q-OPS-02",
            "deferred_history",
            "ORDER BY p.committed_at_us DESC",
        ),
    ],
)
def test_executor_uses_complete_keyset_order_and_limit_before_bounded_decode(
    tmp_path: Path,
    question_id: str,
    variant: str,
    order_sql: str,
) -> None:
    connection, plan_request, question, publication_id = _published_request(
        tmp_path,
        question_id=question_id,
        variant=variant,
    )
    trace: list[str] = []
    connection.set_trace_callback(trace.append)
    result = PhysicalPageExecutor().execute(
        connection,
        _request(
            plan_request,
            question,
            publication_id,
            page_size=100,
        ),
        plan_request,
    )
    connection.close()

    assert order_sql in result.sql
    assert "LIMIT ?" in result.sql
    assert result.parameters[-1] == 101
    assert result.returned_rows == 1
    assert result.stage_measurements["rows_examined"] <= 101
    assert result.stage_measurements["rows_decoded"] <= 101
    assert result.exact_count is None
    assert not any("COUNT(" in statement.upper() for statement in trace)
    _assert_indexed_explain(
        plan_request.plan_id,
        tuple(item.detail for item in result.explain),
    )


def test_latest_publication_delta_accepts_catalog_entity_kind_parameter(
    tmp_path: Path,
) -> None:
    connection, original, question, publication_id = _published_request(
        tmp_path,
        question_id="Q-OPS-01",
        variant="no_change",
    )
    filtered = PlanRequest(
        plan_id=original.plan_id,
        parameters={**original.parameters, "entity_kind": "call"},
        gates=original.gates,
    )

    result = PhysicalPageExecutor().execute(
        connection,
        _request(filtered, question, publication_id, page_size=1),
        filtered,
    )
    connection.close()

    assert result.returned_rows == 1
    assert result.rows[0]["inserted_count"] >= 0


def test_executor_rejects_parameters_not_bound_by_request_digest(
    tmp_path: Path,
) -> None:
    connection, plan_request, question, publication_id = _published_request(
        tmp_path,
        question_id="Q-OPS-02",
        variant="deferred_history",
    )
    page_request = _request(
        plan_request,
        question,
        publication_id,
        page_size=1,
    )

    with pytest.raises(PhysicalPageError, match="parameters do not match"):
        PhysicalPageExecutor().execute(
            connection,
            replace(
                page_request,
                parameters={**page_request.parameters, "as_of_us": 200},
            ),
            plan_request,
        )
    connection.close()


def test_executor_validates_keyset_anchor_and_exact_count_is_opt_in(
    tmp_path: Path,
) -> None:
    connection, plan_request, question, publication_id = _published_request(
        tmp_path,
        question_id="Q-OPS-02",
        variant="deferred_history",
    )
    first = PhysicalPageExecutor().execute(
        connection,
        _request(
            plan_request,
            question,
            publication_id,
            page_size=1,
            include_exact_count=True,
        ),
        plan_request,
    )
    assert first.exact_count == 1
    committed_at_us = int(
        connection.execute(
            "SELECT committed_at_us FROM publications WHERE publication_id = ?",
            (publication_id,),
        ).fetchone()[0]
    )

    deep = PhysicalPageExecutor().execute(
        connection,
        _request(
            plan_request,
            question,
            publication_id,
            page_size=1,
            cursor_order=(committed_at_us,),
        ),
        plan_request,
    )
    assert deep.rows == ()
    assert deep.exact_count is None

    with pytest.raises(PhysicalPageError, match="stale or replaced"):
        PhysicalPageExecutor().execute(
            connection,
            _request(
                plan_request,
                question,
                publication_id,
                page_size=1,
                cursor_order=(committed_at_us + 1,),
            ),
            plan_request,
        )
    connection.close()


def test_executor_rejects_page_sizes_above_frozen_maximum() -> None:
    with pytest.raises(PhysicalPageError, match="between 1 and 100"):
        PageExecutionRequest(
            plan_id="data_health",
            plan_version=1,
            publication_id="publication:synthetic",
            request_digest="0" * 64,
            complete_order=("publication_committed_at_desc",),
            page_size=101,
            cursor_order=None,
        )


def test_typed_order_oracle_preserves_ties_across_deep_keyset_page() -> None:
    connection = sqlite3.connect(":memory:")
    rows = connection.execute(
        """
        WITH synthetic(change_kind, logical_id) AS (
            VALUES ('inserted', 'entity:a'),
                   ('inserted', 'entity:b'),
                   ('removed', 'entity:a')
        )
        SELECT change_kind, logical_id
          FROM synthetic
         WHERE change_kind > ?
            OR (change_kind = ? AND logical_id > ?)
         ORDER BY change_kind ASC, logical_id ASC
         LIMIT ?
        """,
        ("inserted", "inserted", "entity:a", 2),
    ).fetchall()
    connection.close()

    assert rows == [
        ("inserted", "entity:b"),
        ("removed", "entity:a"),
    ]


def test_all_other_admitted_plans_report_exact_gap_without_projection(
    tmp_path: Path,
) -> None:
    connection, _, _, publication_id = _published_request(
        tmp_path,
        question_id="Q-OPS-02",
        variant="deferred_history",
    )
    catalog = _catalog()
    plan_orders = {
        str(question["plan_id"]): tuple(str(item) for item in question["order"])
        for question in catalog.values()
        if question["stage"] in {"Foundation", "Cutover"}
    }
    unsupported = sorted(set(plan_orders) - SUPPORTED_DIRECT_PLAN_IDS)
    assert len(unsupported) == 19

    for plan_id in unsupported:
        plan_request = PlanRequest(plan_id=plan_id, parameters={}, gates={})
        request = PageExecutionRequest(
            plan_id=plan_id,
            plan_version=1,
            publication_id=publication_id,
            request_digest=request_digest(plan_request),
            complete_order=plan_orders[plan_id],
            page_size=1,
            cursor_order=None,
        )
        with pytest.raises(PhysicalPlanGapError) as caught:
            PhysicalPageExecutor().execute(connection, request, plan_request)
        message = str(caught.value)
        assert f"plan_id={plan_id}" in message
        assert f"gap={physical_gap(plan_id)}" in message
        assert "projection_added=false" in message

    assert "temporary sort" in physical_gap("resource_hotspots")
    connection.close()
