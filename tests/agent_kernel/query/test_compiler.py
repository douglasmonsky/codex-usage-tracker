from __future__ import annotations

import ast
import copy
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_operands import CanonicalFact, PlanRequest
from codex_usage_tracker.agent_kernel.query.compiler import (
    SQL_STATEMENTS,
    STATEMENT_IDS,
    DatabaseV1FactCompiler,
    FactCompilerError,
)
from tests.agent_kernel.fact_adapters.database import DatabaseV1FactAdapter
from tests.agent_kernel.fact_adapters.reference import StructuralReferenceFactAdapter
from tests.agent_kernel.fact_adapters.support import (
    HEAD_DIGEST,
    OLD_DIGEST,
    adapter_request,
    build_query_only_database,
    build_structural_v2,
    normalize_materialization,
    plan_contract,
    required_references,
    selector_contract,
)

_ROOT = Path(__file__).resolve().parents[3]
_COMPILER = _ROOT / "src/codex_usage_tracker/agent_kernel/query/compiler.py"


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return ("decimal", str(value))
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _normalize(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_normalize(item) for item in value)
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def _fact_signature(facts: Sequence[CanonicalFact]) -> tuple[Any, ...]:
    return tuple(
        sorted(
            (
                fact.relation,
                fact.logical_id,
                _normalize(fact.values),
                None
                if fact.coordinates is None
                else (
                    fact.coordinates.event_at_us,
                    fact.coordinates.source_rank,
                    fact.coordinates.source_order,
                    fact.coordinates.event_kind_order,
                    fact.coordinates.transition_rank,
                ),
            )
            for fact in facts
        )
    )


def _evidence_request(request: PlanRequest) -> tuple[dict[str, str], ...]:
    return required_references(request=request, include_window=True)


def _compile(
    request: PlanRequest,
    declaration: Mapping[str, Any] | None = None,
    *,
    required_evidence: Any = None,
    contract: Mapping[str, Any] | None = None,
    selector_provenance: Mapping[str, Any] | None = None,
) -> tuple[sqlite3.Connection, Any]:
    connection = build_query_only_database(declaration or build_structural_v2())
    # Keep the semantic parity checks on the compiler's description-based row
    # path; the default sqlite3.Row path has its own focused regression test.
    connection.row_factory = None
    connection.execute("BEGIN")
    compiler = DatabaseV1FactCompiler(
        contract or plan_contract(),
        selector_provenance,
    )
    return connection, compiler.compile(
        connection,
        request,
        required_evidence=required_evidence,
    )


def _mutated_connection(
    mutation: Callable[[sqlite3.Connection], None],
) -> sqlite3.Connection:
    connection = build_query_only_database(build_structural_v2())
    connection.row_factory = None
    connection.execute("PRAGMA query_only = OFF")
    mutation(connection)
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def _close_with_rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()
    connection.close()


def test_compiler_matches_both_independent_adapters_for_all_40_resolved_plans() -> None:
    declaration = build_structural_v2()
    contract = plan_contract()
    selectors = selector_contract()
    reference_adapter = StructuralReferenceFactAdapter(contract, selectors)
    database_adapter = DatabaseV1FactAdapter(contract, selectors)

    assert len(contract["plans"]) == 40
    assert all(plan["status"] == "resolved" for plan in contract["plans"])

    for plan in contract["plans"]:
        plan_id = plan["plan_id"]
        request = adapter_request(plan_id)
        evidence = _evidence_request(request)
        reference = reference_adapter.materialize(declaration, request, evidence)

        database_connection = build_query_only_database(declaration)
        database = database_adapter.materialize(database_connection, request, evidence)
        database_connection.close()

        compiler_connection, compilation = _compile(request, declaration)
        try:
            assert compilation.request == request, plan_id
            assert compilation.publication_id
            assert compilation.request_digest
            assert _fact_signature(compilation.facts) == _fact_signature(reference.facts), plan_id
            assert _fact_signature(compilation.facts) == _fact_signature(database.facts), plan_id
        finally:
            _close_with_rollback(compiler_connection)


def test_compiler_accepts_the_fixture_builders_default_sqlite_row_factory() -> None:
    connection = build_query_only_database(build_structural_v2())
    connection.execute("BEGIN")
    try:
        compilation = DatabaseV1FactCompiler(plan_contract()).compile(
            connection,
            adapter_request("current_usage"),
        )
        assert compilation.facts
    finally:
        _close_with_rollback(connection)


def test_compiler_resolves_owner_evidence_without_answer_backed_rows() -> None:
    declaration = build_structural_v2()
    request = adapter_request("current_usage")
    evidence = _evidence_request(request)
    reference = StructuralReferenceFactAdapter(plan_contract(), selector_contract()).materialize(
        declaration,
        request,
        evidence,
    )

    connection, compilation = _compile(
        request,
        declaration,
        required_evidence=evidence,
        selector_provenance=selector_contract(),
    )
    try:
        assert normalize_materialization(compilation) == normalize_materialization(reference)
        assert compilation.evidence_references
        assert compilation.snapshot_token == compilation.publication_id
    finally:
        _close_with_rollback(connection)


def test_current_valuation_uses_effective_time_and_preserves_typed_missingness() -> None:
    request = adapter_request("pricing_coverage", with_window=False)
    connection, compilation = _compile(
        request,
        build_structural_v2(include_late_call=True, null_cached_tokens=True),
    )
    try:
        matches = {
            fact.values["call_id"]: fact
            for fact in compilation.facts
            if fact.relation == "valuation_match"
        }
        assert matches["call:before"].values["rate_card_digest"] == OLD_DIGEST
        assert matches["call:late"].values["rate_card_digest"] == OLD_DIGEST
        assert matches["call:other"].values["rate_card_digest"] == OLD_DIGEST
        assert matches["call:boundary"].values["rate_card_digest"] == HEAD_DIGEST
        assert matches["call:boundary"].values["match_basis"] == "model_alias"
        assert matches["call:before"].values["configured_cost_usd"] == Decimal("0.000115")
        assert matches["call:before"].values["estimated_credits"] == Decimal("0.000115")
        assert matches["call:before"].values["cost_unpriced_reason"] == "missing_measurement"

        assert matches["call:late"].values["configured_cost_usd"] == Decimal("0.0001")
        assert matches["call:boundary"].values["configured_cost_usd"] == Decimal("0.00054")
        assert matches["call:other"].values["configured_cost_usd"] == Decimal("0.000405")
    finally:
        _close_with_rollback(connection)


def test_allowance_facts_use_remaining_percent_and_keep_same_time_observations() -> None:
    request = adapter_request("allowance_interval_events", with_window=False)
    connection, compilation = _compile(request)
    try:
        observations = {
            fact.logical_id: fact
            for fact in compilation.facts
            if fact.relation == "allowance_observation"
        }
        assert {
            key: fact.values["allowance_percent"] for key, fact in observations.items()
        } == {
            "allowance-observation:1": Decimal("90"),
            "allowance-observation:2": Decimal("80"),
            "allowance-observation:3": Decimal("80"),
            "allowance-observation:4": Decimal("70"),
        }
        assert observations["allowance-observation:2"].coordinates is not None
        assert observations["allowance-observation:3"].coordinates is not None
        assert observations["allowance-observation:2"].coordinates.event_at_us == 190
        assert observations["allowance-observation:3"].coordinates.event_at_us == 190
        assert observations["allowance-observation:2"].coordinates.transition_rank != observations[
            "allowance-observation:3"
        ].coordinates.transition_rank
    finally:
        _close_with_rollback(connection)


@pytest.mark.parametrize(
    ("label", "mutation", "message"),
    [
        (
            "missing source coverage",
            lambda connection: connection.execute(
                "DELETE FROM publication_source_coverage WHERE source_id = 'source:active'"
            ),
            "coverage",
        ),
        (
            "missing capability coverage",
            lambda connection: connection.execute(
                "DELETE FROM publication_capability_coverage WHERE capability_id = 'valuation'"
            ),
            "coverage",
        ),
        (
            "noncommitted publication",
            lambda connection: connection.execute(
                "UPDATE publications SET status = 'rolled_back' WHERE publication_id = 'publication:ck07e'"
            ),
            "committed",
        ),
        (
            "publication and source bound mismatch",
            lambda connection: connection.execute(
                "UPDATE publication_source_coverage SET guaranteed_complete_through_us = 599 WHERE source_id = 'source:active'"
            ),
            "bounds",
        ),
    ],
)
def test_publication_and_capability_authority_fail_closed(
    label: str,
    mutation: Callable[[sqlite3.Connection], None],
    message: str,
) -> None:
    connection = _mutated_connection(mutation)
    try:
        with pytest.raises(FactCompilerError, match=message):
            DatabaseV1FactCompiler(plan_contract()).compile(
                connection,
                adapter_request("data_health", with_window=False),
            )
    finally:
        _close_with_rollback(connection)


@pytest.mark.parametrize(
    ("label", "mutation", "message"),
    [
        (
            "missing active head revision",
            lambda connection: connection.execute(
                "DELETE FROM rate_card_revisions WHERE rate_card_id = 'rate-card:new'"
            ),
            "rate-card",
        ),
        (
            "cyclic lineage",
            lambda connection: connection.execute(
                "UPDATE rate_card_revisions SET predecessor_rate_card_id = 'rate-card:new' WHERE rate_card_id = 'rate-card:old'"
            ),
            "snapshot cannot be compiled|frontier",
        ),
        (
            "noncanonical rate map",
            lambda connection: connection.execute(
                "UPDATE rate_card_revisions SET four_class_rates_json = '{ \"uncached_input_tokens\": \"2\" }' WHERE rate_card_id = 'rate-card:new'"
            ),
            "snapshot cannot be compiled|frontier",
        ),
    ],
)
def test_publication_rate_card_frontier_fail_closed(
    label: str,
    mutation: Callable[[sqlite3.Connection], None],
    message: str,
) -> None:
    connection = _mutated_connection(mutation)
    try:
        with pytest.raises(FactCompilerError, match=message):
            DatabaseV1FactCompiler(plan_contract()).compile(
                connection,
                adapter_request("pricing_coverage", with_window=False),
            )
    finally:
        _close_with_rollback(connection)


def test_compiler_requires_query_only_and_caller_owned_active_transaction() -> None:
    request = adapter_request("current_usage")
    connection = build_query_only_database(build_structural_v2())
    try:
        with pytest.raises(FactCompilerError, match="active deferred read transaction"):
            DatabaseV1FactCompiler(plan_contract()).compile(connection, request)
    finally:
        connection.close()

    connection = build_query_only_database(build_structural_v2())
    connection.execute("PRAGMA query_only = OFF")
    connection.execute("BEGIN")
    try:
        with pytest.raises(FactCompilerError, match="query_only"):
            DatabaseV1FactCompiler(plan_contract()).compile(connection, request)
    finally:
        _close_with_rollback(connection)


def test_compiler_keeps_transaction_ownership_on_success_and_failure() -> None:
    request = adapter_request("current_usage")
    connection = build_query_only_database(build_structural_v2())
    connection.row_factory = None
    connection.execute("BEGIN")
    compilation = DatabaseV1FactCompiler(plan_contract()).compile(connection, request)
    assert compilation.facts
    assert connection.in_transaction
    connection.rollback()
    assert not connection.in_transaction
    connection.close()

    connection = build_query_only_database(build_structural_v2())
    connection.execute("BEGIN")
    try:
        with pytest.raises(FactCompilerError, match="plan must resolve exactly once"):
            DatabaseV1FactCompiler(plan_contract()).compile(
                connection,
                PlanRequest("not-a-resolved-plan"),
            )
        assert connection.in_transaction
    finally:
        _close_with_rollback(connection)


def test_sql_sources_are_closed_ids_with_exact_explain_capture() -> None:
    connection, compilation = _compile(adapter_request("current_usage"))
    try:
        assert compilation.sql_sources
        assert {source.statement_id for source in compilation.sql_sources} <= set(STATEMENT_IDS)
        assert {source.statement_id for source in compilation.sql_sources} >= {
            "snapshot_publication",
            "active_rate_card",
            "canonical_call",
            "valuation_calls",
            "valuation_profiles",
        }
        for source in compilation.sql_sources:
            assert source.source_id == source.statement_id
            assert source.statement == SQL_STATEMENTS[source.statement_id]
            assert isinstance(source.parameters, tuple)
            assert source.explain
            assert all(detail.detail for detail in source.explain)
            assert all(isinstance(detail.select_id, int) for detail in source.explain)
            assert all(isinstance(detail.order, int) for detail in source.explain)
            assert all(isinstance(detail.from_id, int) for detail in source.explain)
        assert compilation.explain == tuple(
            detail for source in compilation.sql_sources for detail in source.explain
        )
    finally:
        _close_with_rollback(connection)


def test_forbidden_source_cannot_be_reached_and_closed_sql_has_no_oracle_tables() -> None:
    forbidden_sql = re.compile(r"\b(?:oracle_case|question_cases|experiment)\b", re.IGNORECASE)
    assert all(not forbidden_sql.search(sql) for sql in SQL_STATEMENTS.values())

    contract = copy.deepcopy(plan_contract())
    current_usage = next(plan for plan in contract["plans"] if plan["plan_id"] == "current_usage")
    current_usage["permitted_sources"].append(
        {"relation": "question_cases", "fields": ["answer"]}
    )
    connection = build_query_only_database(build_structural_v2())
    connection.execute("BEGIN")
    try:
        with pytest.raises(FactCompilerError, match="allowlist"):
            DatabaseV1FactCompiler(contract).compile(
                connection,
                adapter_request("current_usage"),
            )
    finally:
        _close_with_rollback(connection)


def test_compiler_has_no_test_experiment_or_old_kernel_imports() -> None:
    tree = ast.parse(_COMPILER.read_text(encoding="utf-8"), filename=str(_COMPILER))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")

    assert all(
        not name.startswith("tests")
        and not name.startswith("experiments")
        and not name.startswith("codex_usage_tracker.kernel")
        for name in imported
    )


@pytest.mark.parametrize("parameter_name", ["sql", "refresh", "write"])
def test_generic_sql_refresh_and_write_parameters_are_rejected(parameter_name: str) -> None:
    base = adapter_request("current_usage")
    parameters = dict(base.parameters)
    parameters[parameter_name] = "synthetic-forbidden-value"
    request = PlanRequest(base.plan_id, parameters, base.gates)
    connection = build_query_only_database(build_structural_v2())
    connection.row_factory = None
    connection.execute("BEGIN")
    try:
        with pytest.raises(FactCompilerError, match="parameter|SQL|refresh|write"):
            DatabaseV1FactCompiler(plan_contract()).compile(connection, request)
    finally:
        _close_with_rollback(connection)
