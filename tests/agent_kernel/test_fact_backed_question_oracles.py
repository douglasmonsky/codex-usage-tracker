from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.agent_kernel.fact_adapters.support import (
    adapter_request,
    build_query_only_database,
    build_structural_v2,
    required_references,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (
    FIXTURE_REVISION,
    SCENARIO_SCHEMA,
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.oracles.database_replay import (
    evaluate_published_question_case,
)
from tests.agent_kernel.fixtures.oracles.reference import evaluate_question_case

ROOT = Path(__file__).resolve().parents[2]
TINY_V2 = ROOT / "tests/agent_kernel/fixtures/tiny-v2"
CATALOG = json.loads(
    (ROOT / "config/agent-kernel/question-catalog-v1.json").read_text(encoding="utf-8")
)
CURRENT_USAGE = next(
    question for question in CATALOG["questions"] if question["question_id"] == "Q-ACC-01"
)


def _case(oracle_id: str, *, missing_cached: bool) -> dict[str, object]:
    request = adapter_request("current_usage")
    required_kinds = set(CURRENT_USAGE["evidence"]["selector_kinds"])
    evidence = [
        item
        for item in required_references(request=request, include_window=True)
        if item["selector_kind"] in required_kinds
    ]
    return {
        "oracle_id": oracle_id,
        "question_id": "Q-ACC-01",
        "variant": oracle_id.rsplit(":", 1)[-1],
        "request": {
            "plan_id": request.plan_id,
            "parameters": dict(request.parameters),
            "gates": dict(request.gates),
        },
        "declaration": build_structural_v2(null_cached_tokens=missing_cached),
        "required_evidence": evidence,
    }


@pytest.mark.parametrize(
    ("oracle_id", "missing_cached"),
    [
        ("oracle:q-acc-01:boundaries", False),
        ("oracle:q-acc-01:missing_measurement", True),
    ],
)
def test_q_acc_01_reconciles_independent_consumers(
    oracle_id: str,
    missing_cached: bool,
) -> None:
    case = _case(oracle_id, missing_cached=missing_cached)
    reference = evaluate_question_case(case, CURRENT_USAGE)
    connection = build_query_only_database(case["declaration"])
    database = evaluate_published_question_case(
        connection,
        case["request"],
        case["required_evidence"],
        CURRENT_USAGE,
        oracle_id=oracle_id,
        variant=str(case["variant"]),
    )

    assert reference == database
    assert reference["request_digest"]
    assert reference["rows"]
    assert [item["selector_kind"] for item in reference["references"]] == [
        "publication",
        "window",
    ]


def test_grading_output_cannot_change_either_consumer() -> None:
    case = _case("oracle:q-acc-01:boundaries", missing_cached=False)
    reference = evaluate_question_case(case, CURRENT_USAGE)
    connection = build_query_only_database(case["declaration"])
    database = evaluate_published_question_case(
        connection,
        case["request"],
        case["required_evidence"],
        CURRENT_USAGE,
        oracle_id=str(case["oracle_id"]),
        variant=str(case["variant"]),
    )
    mutated_contract = copy.deepcopy(CURRENT_USAGE)
    mutated_contract["answers"]["fields"] = {
        field: "mutated-grade" for field in mutated_contract["answers"]["fields"]
    }

    assert evaluate_question_case(case, mutated_contract) == reference
    assert (
        evaluate_published_question_case(
            connection,
            case["request"],
            case["required_evidence"],
            mutated_contract,
            oracle_id=str(case["oracle_id"]),
            variant=str(case["variant"]),
        )
        == database
    )


def test_canonical_fact_mutation_breaks_equivalence() -> None:
    case = _case("oracle:q-acc-01:boundaries", missing_cached=False)
    original = evaluate_question_case(case, CURRENT_USAGE)
    mutated = copy.deepcopy(case)
    call = next(
        fact for fact in mutated["declaration"]["facts"] if fact["relation"] == "canonical_call"
    )
    call["values"]["uncached_input_tokens"] += 1

    assert evaluate_question_case(mutated, CURRENT_USAGE) != original


def test_all_80_declared_variants_reconcile_exactly() -> None:
    scenarios = build_question_scenarios()
    questions = {question["question_id"]: question for question in CATALOG["questions"]}
    frozen = json.loads((TINY_V2 / "oracle-bundle.json").read_text(encoding="utf-8"))
    comparisons: list[str] = []
    references: list[dict[str, object]] = []

    assert list(scenarios) == ["schema", "fixture_revision", "authority", "cases"]
    assert scenarios["authority"] == {
        "basis": "frozen_pre_ck06_ck07_structural_declaration",
        "database_export_prohibited": True,
        "variant_mutations": 80,
        "variant_predicates": 160,
    }
    assert scenarios["schema"] == SCENARIO_SCHEMA
    assert scenarios["fixture_revision"] == FIXTURE_REVISION
    assert len(scenarios["cases"]) == 80
    assert len({case["semantic_mutation"]["native_turn_id"] for case in scenarios["cases"]}) == 80
    assert all(len(case["variant_predicates"]) == 2 for case in scenarios["cases"])
    assert sum(len(question["answers"]["fields"]) for question in CATALOG["questions"]) == 185

    for case in scenarios["cases"]:
        question = questions[case["question_id"]]
        reference = evaluate_question_case(case, question)
        frozen_case = frozen["questions"][case["oracle_id"]]
        assert reference["request_digest"] == frozen_case["request_digest"]
        assert reference["rows"] == frozen_case["expected_rows"]
        assert reference["references"] == frozen_case["references"]
        assert reference["comparison_digest"] == frozen_case["comparison_digest"]
        comparisons.append(reference["comparison_digest"])
        references.extend(reference["references"])

    assert len(set(comparisons)) == 80
    assert len({item["selector_kind"] for item in references}) == 14
    assert len({item["provenance_kind"] for item in references}) == 6


def test_the_four_frozen_owner_scoped_cases_have_no_fabricated_window() -> None:
    scenarios = build_question_scenarios()
    no_window = [
        (case["question_id"], case["variant"])
        for case in scenarios["cases"]
        if not any(
            key in case["request"]["parameters"]
            for key in ("window", "current_window", "previous_window")
        )
    ]
    assert [
        ("Q-ALW-02", "empty_interval"),
        ("Q-ALW-02", "same_time_boundary"),
        ("Q-OPS-01", "no_change"),
        ("Q-OPS-01", "recanonicalized_owner"),
    ] == [item for item in no_window if item[0] in {"Q-ALW-02", "Q-OPS-01"}]


def test_committed_structural_v2_bundle_contains_80_reference_results() -> None:
    scenarios = json.loads((TINY_V2 / "question-scenarios.json").read_text(encoding="utf-8"))
    oracle = json.loads((TINY_V2 / "oracle-bundle.json").read_text(encoding="utf-8"))
    questions = {question["question_id"]: question for question in CATALOG["questions"]}
    assert list(scenarios) == ["schema", "fixture_revision", "cases"]
    assert len(scenarios["cases"]) == 80
    assert len(oracle["questions"]) == 80
    for case in scenarios["cases"]:
        evaluated = evaluate_question_case(
            case,
            questions[case["question_id"]],
        )
        frozen = oracle["questions"][case["oracle_id"]]
        assert evaluated["request_digest"] == frozen["request_digest"]
        assert evaluated["rows"] == frozen["expected_rows"]
        assert evaluated["references"] == frozen["references"]
        assert evaluated["comparison_digest"] == frozen["comparison_digest"]


def test_structural_v2_sources_and_scenarios_are_body_and_answer_free() -> None:
    forbidden_source_tokens = (
        b'"oracle_case"',
        b'"expected"',
        b'"grade"',
        b'"grading"',
        b'"comparison"',
        b'"answer_cache"',
        b'"prompt"',
        b'"response"',
        b'"reasoning":',
        b'"command"',
        b'"patch"',
    )
    for source in sorted((TINY_V2 / "sources").glob("*.jsonl")):
        payload = source.read_bytes().lower()
        assert not any(token in payload for token in forbidden_source_tokens)

    scenarios = json.loads((TINY_V2 / "question-scenarios.json").read_text(encoding="utf-8"))
    forbidden_keys = {
        "answer_cache",
        "expected",
        "grades",
        "grading",
        "oracle_case",
    }

    def visit(value) -> None:
        if isinstance(value, dict):
            assert not forbidden_keys.intersection(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(scenarios)
