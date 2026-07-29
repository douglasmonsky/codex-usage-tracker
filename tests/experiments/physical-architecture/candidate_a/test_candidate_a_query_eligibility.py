from __future__ import annotations

import importlib
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_a = importlib.import_module("candidate_a")
adapter_module = importlib.import_module("candidate_a.adapter")
queries_module = importlib.import_module("candidate_a.queries")
schema_module = importlib.import_module("candidate_a.schema")

Adapter = adapter_module.Adapter
database = schema_module.database
run_question = queries_module.run_question

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_PHYSICAL_CORES = 10


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


@pytest.fixture
def built(
    fixture: Any,
    tmp_path: Path,
) -> tuple[Any, Any]:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "candidate-a.sqlite")
    return fixture, artifact


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _expected_rows(fixture: Any, question_id: str) -> list[dict[str, Any]]:
    return [
        {
            "oracle_id": str(oracle_id),
            "variant": str(question["variant"]),
            "metrics": _plain(question["expected"]["row"]),
            "grades": _plain(question["expected"]["field_grades"]),
            "evidence_selectors": sorted(str(value) for value in question["selectors"]),
            "caveats": _plain(question["caveats"]),
        }
        for oracle_id, question in sorted(fixture.oracle["questions"].items())
        if question["question_id"] == question_id
    ]


def _request(
    *,
    fixture: Any,
    case: Any,
    run_root: Path,
) -> Any:
    run_root.mkdir()
    return shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=run_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )


def test_every_required_question_envelope_is_sql_derived_and_oracle_exact(
    built: tuple[Any, Any],
) -> None:
    fixture, artifact = built
    question_ids = sorted(set(shared.P1_QUESTION_IDS) | set(shared.REQUIRED_SLICE_QUESTION_IDS))

    with database(artifact.path, read_only=True) as connection:
        for question_id in question_ids:
            plan_id, _ = shared.QUESTION_WORKLOAD_CONTRACTS[question_id]
            result = run_question(
                connection,
                fixture,
                question_id=question_id,
                plan_id=plan_id,
            )

            assert result.payload["schema"] == "codex-usage-tracker.result.v1"
            envelope = result.payload["results"][0]
            assert envelope["question_id"] == question_id
            assert envelope["plan_id"] == plan_id
            assert envelope["plan_version"] == 1
            assert envelope["rows"] == _expected_rows(fixture, question_id)
            assert envelope["page"] == {
                "returned_rows": 2,
                "has_more": False,
                "next_cursor": None,
            }
            assert result.oracle_equivalent
            assert result.automatic_index_count == 0
            assert len(result.encoded) <= 16_384


def test_fixture_oracle_can_grade_but_cannot_construct_query_rows(
    built: tuple[Any, Any],
) -> None:
    fixture, artifact = built
    question_id = "Q-ACC-01"
    plan_id = "current_usage"
    with database(artifact.path, read_only=True) as connection:
        baseline = run_question(
            connection,
            fixture,
            question_id=question_id,
            plan_id=plan_id,
        )

        questions = dict(fixture.oracle["questions"])
        oracle_id = "oracle:q-acc-01:boundaries"
        tampered_question = dict(questions[oracle_id])
        tampered_expected = dict(tampered_question["expected"])
        tampered_metrics = dict(tampered_expected["row"])
        tampered_metrics["calls"] = int(tampered_metrics["calls"]) + 1
        tampered_expected["row"] = tampered_metrics
        tampered_question["expected"] = tampered_expected
        questions[oracle_id] = tampered_question
        tampered_oracle = dict(fixture.oracle)
        tampered_oracle["questions"] = questions
        tampered_fixture = replace(fixture, oracle=tampered_oracle)

        graded = run_question(
            connection,
            tampered_fixture,
            question_id=question_id,
            plan_id=plan_id,
        )

    assert graded.payload == baseline.payload
    assert not graded.oracle_equivalent


def test_database_question_facts_drive_missingness_and_values(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "mutated.sqlite")
    oracle_id = "oracle:q-acc-01:missing_measurement"
    with database(artifact.path) as connection:
        connection.execute(
            """
            UPDATE question_cases
            SET observed_facts_json = json_set(
                observed_facts_json,
                '$.uncached_input_tokens',
                999999
            )
            WHERE oracle_id = ?
            """,
            (oracle_id,),
        )
        connection.commit()
    with database(artifact.path, read_only=True) as connection:
        result = run_question(
            connection,
            fixture,
            question_id="Q-ACC-01",
            plan_id="current_usage",
        )

    by_id = {row["oracle_id"]: row for row in result.payload["results"][0]["rows"]}
    assert by_id[oracle_id]["metrics"]["uncached_input_tokens"] == 999999
    assert by_id[oracle_id]["metrics"]["cached_input_tokens"] is None
    assert not result.oracle_equivalent


def test_query_matrix_declares_all_plan_allowances() -> None:
    matrix = shared.build_workload_matrix(physical_cores=_PHYSICAL_CORES)
    plan_metrics = {
        shared.StopMetric.FULL_SCAN_COUNT,
        shared.StopMetric.AUTOMATIC_INDEX_COUNT,
        shared.StopMetric.TEMPORARY_SORT_COUNT,
    }

    for case in matrix.cases:
        if case.group is not shared.WorkloadGroup.QUERY:
            continue
        limits = {limit.metric: limit.maximum for limit in case.early_stop_limits}
        assert plan_metrics <= limits.keys(), case.case_id
        assert limits[shared.StopMetric.AUTOMATIC_INDEX_COUNT] == 0
        assert limits[shared.StopMetric.FULL_SCAN_COUNT] == int(
            case.parameter("maximum_full_scans")
        )
        assert limits[shared.StopMetric.TEMPORARY_SORT_COUNT] == int(
            case.parameter("maximum_temporary_sorts")
        )

    exact_count = matrix.by_id("query.feature.exact_count")
    assert exact_count.parameter("plan_allowance_reason") == (
        "explicit_exact_count_across_13_evidence_domains"
    )
    assert exact_count.parameter("maximum_full_scans") == 13
    selected_timeline = matrix.by_id("query.feature.selected_session_timeline")
    assert selected_timeline.parameter("plan_allowance_reason") == (
        "selector_scoped_merge_over_at_most_11_rows_per_stream"
    )
    assert selected_timeline.parameter("maximum_temporary_sorts") == 6
    bounded_sort = matrix.by_id("query.feature.bounded_full_sort")
    assert bounded_sort.parameter("plan_allowance_reason") == (
        "scan_and_complete_sort_over_at_most_100_admitted_rows"
    )
    assert bounded_sort.parameter("maximum_full_scans") == 1
    assert bounded_sort.parameter("maximum_temporary_sorts") == 1


def test_all_69_candidate_a_query_cases_pass_explicit_plan_gates(
    fixture: Any,
    tmp_path: Path,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=_PHYSICAL_CORES)
    query_cases = [case for case in matrix.cases if case.group is shared.WorkloadGroup.QUERY]

    assert len(query_cases) == 69
    for case in query_cases:
        request = _request(
            fixture=fixture,
            case=case,
            run_root=tmp_path / case.case_id,
        )
        result = Adapter().execute(request)

        assert result.outcome is shared.RunOutcome.PASSED, case.case_id
        assert result.measurements.oracle_equivalent, case.case_id
        assert result.measurements.full_scan_count <= int(case.parameter("maximum_full_scans"))
        assert result.measurements.automatic_index_count <= int(
            case.parameter("maximum_automatic_indexes")
        )
        assert result.measurements.temporary_sort_count <= int(
            case.parameter("maximum_temporary_sorts")
        )


def test_plan_counter_distinguishes_automatic_indexes_and_bounded_sorts() -> None:
    assert queries_module._plan_counts(  # noqa: SLF001
        (
            "SEARCH child USING AUTOMATIC COVERING INDEX (parent_id=?)",
            "USE TEMP B-TREE FOR ORDER BY",
        )
    ) == (0, 1, 1)


def test_candidate_stops_before_finishing_a_disallowed_sort(
    fixture: Any,
    tmp_path: Path,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=_PHYSICAL_CORES)
    admitted = matrix.by_id("query.feature.bounded_full_sort")
    disallowed = replace(
        admitted,
        early_stop_limits=tuple(
            shared.MetricLimit(
                limit.metric,
                (0 if limit.metric is shared.StopMetric.TEMPORARY_SORT_COUNT else limit.maximum),
            )
            for limit in admitted.early_stop_limits
        ),
    )
    request = _request(
        fixture=fixture,
        case=disallowed,
        run_root=tmp_path / "disallowed-sort",
    )

    result = Adapter().execute(request)

    assert result.outcome is shared.RunOutcome.STOPPED
    assert request.stop.decision is not None
    assert request.stop.decision.metric is shared.StopMetric.TEMPORARY_SORT_COUNT
    assert result.measurements.temporary_sort_count == 1
