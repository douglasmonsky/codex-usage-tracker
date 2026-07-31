from __future__ import annotations

import importlib
import inspect
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.fixtures.oracles import database_replay
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.oracles.reference import evaluate_question_case
from tests.agent_kernel.fixtures.published_v2 import (
    publish_structural_snapshot,
    published_question_case,
)

ROOT = Path(__file__).resolve().parents[4]
EXPERIMENT_ROOT = ROOT / "experiments" / "physical-architecture"
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

queries = importlib.import_module("candidate_a.queries")

CATALOG = json.loads(
    (ROOT / "config/agent-kernel/question-catalog-v1.json").read_text(encoding="utf-8")
)


class _LegacyAuthorizerConnection(sqlite3.Connection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.authorizers: list[Any] = []

    def set_authorizer(self, callback: Any) -> None:
        if callback is None:
            raise AssertionError("legacy sqlite3 cannot safely accept a None authorizer")
        self.authorizers.append(callback)
        super().set_authorizer(callback)


def test_candidate_a_requalifies_all_80_from_permitted_database_v1_facts(
    tmp_path: Path,
) -> None:
    questions = {question["question_id"]: question for question in CATALOG["questions"]}
    comparison_digests: list[str] = []
    field_bindings = sum(len(question["answers"]["fields"]) for question in CATALOG["questions"])
    selector_kinds: set[str] = set()
    provenance_kinds: set[str] = set()
    source_tables: set[str] = set()
    response_bytes: list[int] = []
    plan_rows = 0

    for index, original in enumerate(build_question_scenarios()["cases"]):
        profile = original["source_profile"]
        mutation = original["semantic_mutation"]
        case_root = tmp_path / f"case-{index:02d}"
        database_path = case_root / "database-v1.sqlite3"
        publish_structural_snapshot(
            case_root / "fixture",
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
        result = queries.run_fact_backed_question(
            connection,
            request=case["request"],
            required_evidence=tuple(case["required_evidence"]),
            question_contract=question,
            oracle_id=case["oracle_id"],
            variant=case["variant"],
        )
        connection.close()

        envelope = result.payload["results"][0]
        assert envelope["request_digest"] == expected["request_digest"]
        assert envelope["rows"] == expected["rows"]
        assert envelope["evidence_references"] == expected["references"]
        assert envelope["comparison_digest"] == expected["comparison_digest"]
        assert json.loads(result.encoded) == result.payload
        assert result.oracle_equivalent
        assert result.automatic_index_count == 0
        assert result.query_plans
        assert not queries._FORBIDDEN_FACT_BACKED_TABLES.intersection(  # noqa: SLF001
            result.source_tables
        )
        assert set(result.source_tables).issubset(queries.FACT_BACKED_SOURCE_TABLE_ALLOWLIST)
        assert all(
            forbidden not in statement.lower()
            for statement in result.sql_statements
            for forbidden in ("oracle_case", "question_cases")
        )

        comparison_digests.append(envelope["comparison_digest"])
        selector_kinds.update(
            reference["selector_kind"] for reference in envelope["evidence_references"]
        )
        provenance_kinds.update(
            reference["provenance_kind"] for reference in envelope["evidence_references"]
        )
        source_tables.update(result.source_tables)
        response_bytes.append(len(result.encoded))
        plan_rows += len(result.query_plans)

    assert len(comparison_digests) == 80
    assert len(set(comparison_digests)) == 80
    assert field_bindings == 185
    assert len(selector_kinds) == 14
    assert len(provenance_kinds) == 6
    assert source_tables == set(queries.FACT_BACKED_SOURCE_TABLE_ALLOWLIST)
    assert max(response_bytes) <= 20_480
    assert plan_rows > 0


def test_legacy_authorizer_stays_guarded_then_restores_normal_query_only_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = build_question_scenarios()["cases"][0]
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database_path = tmp_path / "database-v1.sqlite3"
    publish_structural_snapshot(
        tmp_path / "fixture",
        database_path,
        include_late_call=profile["late_event"],
        null_cached_tokens=profile["missing_cached_input"],
        variant_native_turn_id=mutation["native_turn_id"],
    )
    connection = sqlite3.connect(database_path, factory=_LegacyAuthorizerConnection)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    questions = {question["question_id"]: question for question in CATALOG["questions"]}
    question = questions[case["question_id"]]
    guarded_probe_denied = False
    evaluate = database_replay.evaluate_published_question_case

    def evaluate_with_forbidden_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal guarded_probe_denied
        guarded_connection = args[0]
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            guarded_connection.execute("SELECT 1 FROM source_diagnostics LIMIT 1").fetchall()
        guarded_probe_denied = True
        return evaluate(*args, **kwargs)

    monkeypatch.setattr(queries, "_AUTHORIZER_NONE_SUPPORTED", False)
    monkeypatch.setattr(
        database_replay,
        "evaluate_published_question_case",
        evaluate_with_forbidden_probe,
    )
    connection.execute("PRAGMA query_only = ON")
    result = queries.run_fact_backed_question(
        connection,
        request=case["request"],
        required_evidence=tuple(case["required_evidence"]),
        question_contract=question,
        oracle_id=case["oracle_id"],
        variant=case["variant"],
    )

    assert result.oracle_equivalent
    assert guarded_probe_denied
    assert len(connection.authorizers) == 2
    assert connection.authorizers[-1] is queries._allow_all_authorizer  # noqa: SLF001
    assert connection.execute(
        "EXPLAIN QUERY PLAN SELECT 1 FROM source_diagnostics LIMIT 1"
    ).fetchall()
    with pytest.raises(sqlite3.DatabaseError):
        connection.execute("DELETE FROM source_diagnostics")
    connection.close()


def test_fact_backed_candidate_has_no_generic_sql_or_refresh_parameter() -> None:
    parameters = inspect.signature(queries.run_fact_backed_question).parameters
    assert "sql" not in parameters
    assert "refresh" not in parameters
    assert "write" not in parameters
