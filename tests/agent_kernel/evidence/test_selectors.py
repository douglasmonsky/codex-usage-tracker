from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest
from codex_usage_tracker.agent_kernel.evidence.selectors import (
    EvidenceSelectorError,
    resolve_evidence_references,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.oracles.exact import normalize_exact
from tests.agent_kernel.fixtures.oracles.reference import evaluate_question_case
from tests.agent_kernel.fixtures.published_v2 import (
    PUBLICATION_ID,
    publish_structural_snapshot,
    published_question_case,
)

_ROOT = Path(__file__).resolve().parents[3]
_SELECTOR_CONTRACT = _ROOT / "config/agent-kernel/selector-provenance-v1.json"


def _contract() -> dict[str, object]:
    return json.loads(_SELECTOR_CONTRACT.read_text(encoding="utf-8"))


def _request(case: dict[str, object]) -> PlanRequest:
    request = case["request"]
    assert isinstance(request, dict)
    return PlanRequest(
        plan_id=str(request["plan_id"]),
        parameters=request["parameters"],  # type: ignore[arg-type]
        gates=request["gates"],  # type: ignore[arg-type]
    )


def _published_case(
    tmp_path: Path,
    case: dict[str, object],
    index: int,
) -> tuple[sqlite3.Connection, dict[str, object]]:
    profile = case["source_profile"]
    mutation = case["semantic_mutation"]
    assert isinstance(profile, dict)
    assert isinstance(mutation, dict)
    case_root = tmp_path / f"case-{index:02d}"
    database = case_root / "database-v1.sqlite3"
    publish_structural_snapshot(
        case_root / "fixture",
        database,
        include_late_call=bool(profile["late_event"]),
        null_cached_tokens=bool(profile["missing_cached_input"]),
        variant_native_turn_id=str(mutation["native_turn_id"]),
    )
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection, published_question_case(connection, case)


def _reference_mappings(references: object) -> list[dict[str, object]]:
    assert isinstance(references, tuple)
    return [
        {
            "role": reference.role,
            "selector_kind": reference.selector_kind,
            "selector": reference.selector,
            "logical_id": reference.logical_id,
            "provenance_kind": reference.provenance_kind,
            "provenance": reference.provenance,
        }
        for reference in references
    ]


def test_all_80_structural_variants_match_independent_ordered_references(
    tmp_path: Path,
) -> None:
    cases = build_question_scenarios()["cases"]
    assert len(cases) == 80

    for index, original in enumerate(cases):
        assert isinstance(original, dict)
        connection, case = _published_case(tmp_path, original, index)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            resolved = resolve_evidence_references(
                connection,
                _request(case),
                _contract(),
                case["required_evidence"],
                publication_id=PUBLICATION_ID,
            )
            expected = evaluate_question_case(case, {})["references"]
            assert normalize_exact(_reference_mappings(resolved)) == expected, case["oracle_id"]
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def test_rejects_malformed_extra_and_reordered_contract_metadata(tmp_path: Path) -> None:
    original = build_question_scenarios()["cases"][2]
    assert isinstance(original, dict)
    connection, case = _published_case(tmp_path, original, 0)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        extra = copy.deepcopy(_contract())
        extra["unexpected"] = True
        with pytest.raises(EvidenceSelectorError, match="invalid shape"):
            resolve_evidence_references(connection, _request(case), extra, case["required_evidence"])

        reordered = copy.deepcopy(_contract())
        selector_kinds = reordered["selector_kinds"]
        assert isinstance(selector_kinds, list)
        reordered["selector_kinds"] = list(reversed(selector_kinds))
        with pytest.raises(EvidenceSelectorError, match="ordered contract"):
            resolve_evidence_references(
                connection,
                _request(case),
                reordered,
                case["required_evidence"],
            )

        malformed = [dict(case["required_evidence"][0], unexpected=True)]
        with pytest.raises(EvidenceSelectorError, match="extra fields"):
            resolve_evidence_references(connection, _request(case), _contract(), malformed)
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def test_aliases_and_publication_mismatch_fail_closed(tmp_path: Path) -> None:
    original = build_question_scenarios()["cases"][2]
    assert isinstance(original, dict)
    connection, case = _published_case(tmp_path, original, 0)
    session = next(
        item["logical_id"]
        for item in case["required_evidence"]
        if item["selector_kind"] == "session"
    )
    assert isinstance(session, str)
    alias_selector = "session:legacy-session"
    canonical_selector = f"session:{session}"
    connection.execute(
        """
        INSERT INTO selector_aliases(
            alias_selector, canonical_selector, logical_id, reason,
            first_seen_publication_id
        ) VALUES (?, ?, ?, 'recanonicalization', ?)
        """,
        (alias_selector, canonical_selector, session, PUBLICATION_ID),
    )
    connection.commit()
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        required = [dict(item) for item in case["required_evidence"]]
        selected = next(item for item in required if item["selector_kind"] == "session")
        selected["selector"] = alias_selector
        selected["logical_id"] = "legacy-session"
        resolved = resolve_evidence_references(
            connection,
            _request(case),
            _contract(),
            required,
        )
        aliased = next(item for item in resolved if item.role == selected["role"])
        assert aliased.logical_id == session
        assert aliased.provenance["alias"]["canonical_selector"] == canonical_selector

        with pytest.raises(EvidenceSelectorError, match="does not match committed head"):
            resolve_evidence_references(
                connection,
                _request(case),
                _contract(),
                case["required_evidence"],
                publication_id="publication:stale",
            )
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@pytest.mark.parametrize(
    "prefix",
    ["oracle:q-alw-02:", "oracle:q-ops-01:"],
)
def test_four_no_window_variants_do_not_fabricate_window_evidence(prefix: str) -> None:
    cases = [
        case
        for case in build_question_scenarios()["cases"]
        if str(case["oracle_id"]).startswith(prefix)
    ]
    assert len(cases) == 2
    assert all(
        not any(item["selector_kind"] == "window" for item in case["required_evidence"])
        for case in cases
    )
