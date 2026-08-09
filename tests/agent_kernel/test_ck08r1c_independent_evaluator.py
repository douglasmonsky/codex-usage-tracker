from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.agent_kernel.fixtures.independent import semantic as independent_semantic
from tests.agent_kernel.fixtures.independent.closure import (
    ClosureError,
    compute_closure,
    verify_closure,
)
from tests.agent_kernel.fixtures.independent.semantic import (
    CONTRACT_PATH,
    FORBIDDEN_DATA_KEYS,
    QUESTION_CATALOG_PATH,
    ROOT,
    SELECTOR_PROVENANCE_PATH,
    VECTORS_PATH,
    SemanticError,
    evaluate_all,
    evaluate_case,
    evaluate_wf02_events,
    load_cases,
)

INDEPENDENT_ROOT = ROOT / "tests/agent_kernel/fixtures/independent"
Q_REV_FIELDS = (
    "completion_state",
    "context_features",
    "delegation_metrics",
    "resource_metrics",
    "state_change_metrics",
    "token_deltas",
    "tool_metrics",
    "turn_call_counts",
)


def _case(oracle_id: str) -> dict[str, Any]:
    for case in load_cases():
        if case.get("oracle_id") == oracle_id:
            return copy.deepcopy(case)
    raise AssertionError(f"missing synthetic case {oracle_id}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add("." * node.level + (node.module or ""))
    return modules


def test_independent_evaluator_evaluates_all_80_declared_variants() -> None:
    cases = load_cases()
    results = evaluate_all(cases)

    assert len(cases) == len(results) == 80
    assert len({result["oracle_id"] for result in results}) == 80
    for case, result in zip(cases, results, strict=True):
        assert result["oracle_id"] == case["oracle_id"]
        assert set(result) == {
            "oracle_id",
            "request",
            "rows",
            "field_grades",
            "total_order",
            "ordered_evidence",
            "provenance",
        }
        assert not FORBIDDEN_DATA_KEYS.intersection(result)


def test_field_grades_are_the_declared_typed_contract_for_all_80_variants() -> None:
    catalog = json.loads(QUESTION_CATALOG_PATH.read_text(encoding="utf-8"))
    expected = {
        question["plan_id"]: question["answers"]["fields"] for question in catalog["questions"]
    }
    for case, result in zip(load_cases(), evaluate_all(), strict=True):
        assert result["field_grades"] == expected[case["request"]["plan_id"]]


def test_provenance_is_owner_typed_and_non_placeholder_across_all_variants() -> None:
    contract = json.loads(SELECTOR_PROVENANCE_PATH.read_text(encoding="utf-8"))
    rules = {item["kind"]: item for item in contract["ownership"]}
    provenance_kinds: set[str] = set()
    for result in evaluate_all():
        for reference in result["provenance"]:
            kind = reference["selector_kind"]
            rule = rules[kind]
            provenance_kinds.add(reference["provenance_kind"])
            assert reference["provenance_kind"] == rule["provenance_kind"]
            assert all(
                field in reference["provenance"]
                and reference["provenance"][field] not in (None, "", [], {})
                for field in rule["required_provenance_fields"]
            )
    assert provenance_kinds == set(contract["provenance_kinds"])


def test_r1a_contract_identity_and_q_wf_02_vectors_are_consumed_directly() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

    assert vectors["contract_sha256"] == _sha256(CONTRACT_PATH)
    assert contract["packet"] == "CK-08R1A"
    assert tuple(contract["questions"]["Q-REV-03"]["fields"]) == Q_REV_FIELDS

    evaluated = [evaluate_wf02_events(vector["events"]) for vector in vectors["q_wf_02"]]
    assert evaluated == [vector["expected"] for vector in vectors["q_wf_02"]]


def test_q_wf_02_rejects_duplicate_logical_ids_for_every_event_kind() -> None:
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    events = vectors["q_wf_02"][0]["events"]
    for kind in ("call", "tool_start", "tool_terminal", "state_change"):
        event = next(item for item in events if item["kind"] == kind)
        duplicate = copy.deepcopy(events)
        duplicate.append(copy.deepcopy(event))
        with pytest.raises(SemanticError):
            evaluate_wf02_events(duplicate)


def test_q_wf_02_session_selector_excludes_same_window_foreign_facts() -> None:
    case = _case("oracle:q-wf-02:failed_then_success")
    selected_session = next(
        fact["values"]["session_id"]
        for fact in case["declaration"]["facts"]
        if fact["relation"] == "tool_invocation"
    )
    case["request"]["parameters"]["session_selector"] = selected_session
    baseline = evaluate_case(case)

    foreign = copy.deepcopy(case)
    for fact in foreign["declaration"]["facts"]:
        if fact["relation"] in {"canonical_call", "tool_invocation", "state_change"}:
            fact["values"]["session_id"] = "session:foreign"
    row = evaluate_case(foreign)["rows"][0]
    assert row == {
        "first_action_tokens": None,
        "first_mutation_tokens": None,
        "first_success_tokens": None,
        "mutation_observed": False,
    }
    assert row != baseline["rows"][0]


def test_q_wf_02_selects_succeeded_terminal_when_start_precedes_window() -> None:
    case = _case("oracle:q-wf-02:failed_then_success")
    case["request"]["parameters"]["window"] = {
        "start_us": 201,
        "end_us": 210,
        "timezone": "UTC",
    }
    row = evaluate_case(case)["rows"][0]
    assert row["first_action_tokens"] is None
    assert row["first_success_tokens"] == 0


@pytest.mark.parametrize(
    ("relation", "stable_id_field"),
    [
        ("canonical_call", "call_id"),
        ("tool_invocation", "tool_id"),
        ("state_change", "state_change_id"),
    ],
)
def test_q_wf_02_case_evaluator_rejects_duplicate_stable_ids(
    relation: str, stable_id_field: str
) -> None:
    case = _case("oracle:q-wf-02:failed_then_success")
    fact = next(item for item in case["declaration"]["facts"] if item["relation"] == relation)
    duplicate = copy.deepcopy(fact)
    duplicate["logical_id"] = f"{fact['logical_id']}:distinct-declaration"
    duplicate["values"][stable_id_field] = fact["values"][stable_id_field]
    case["declaration"]["facts"].append(duplicate)
    with pytest.raises(SemanticError, match="duplicate"):
        evaluate_case(case)


@pytest.mark.parametrize("prefix", ["start", "terminal"])
def test_q_wf_02_case_evaluator_rejects_null_required_tool_timestamp(
    prefix: str,
) -> None:
    case = _case("oracle:q-wf-02:failed_then_success")
    tool = next(
        fact
        for fact in case["declaration"]["facts"]
        if fact["relation"] == "tool_invocation"
        and fact["values"]["lifecycle"] == "succeeded"
    )
    tool["values"][f"{prefix}_at_us"] = None
    with pytest.raises(SemanticError, match=rf"malformed tool {prefix} coordinate"):
        evaluate_case(case)


@pytest.mark.parametrize("kind", ["tool_start", "tool_terminal"])
def test_q_wf_02_vector_evaluator_rejects_null_required_tool_timestamp(
    kind: str,
) -> None:
    vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    events = copy.deepcopy(vectors["q_wf_02"][0]["events"])
    event = next(item for item in events if item["kind"] == kind)
    event["coordinate"][0] = True
    event["coordinate"][1] = 0
    with pytest.raises(SemanticError, match=rf"{kind} event_at_us must not be null"):
        evaluate_wf02_events(events)


def test_q_rev_03_emits_frozen_shape_and_exact_side_metrics() -> None:
    result = evaluate_case(_case("oracle:q-rev-03:differing_coverage"))
    row = result["rows"][0]

    assert tuple(row) == Q_REV_FIELDS
    assert row["completion_state"]["left"] == {
        "completion_basis": "terminal_event",
        "lifecycle_state": "succeeded",
    }
    assert row["context_features"]["left"]["distinct_context_window_tokens"] == [128000]
    assert row["delegation_metrics"]["left"] == {
        "descendant_tokens": 675,
        "exclusive_tokens": 135,
        "inclusive_tokens": 810,
    }
    assert row["token_deltas"] == {
        "cached_input_tokens": 80,
        "output_tokens": 40,
        "reasoning_tokens": 20,
        "total_tokens": 540,
        "uncached_input_tokens": 400,
    }


def test_q_rev_03_open_lifecycle_and_missingness_fail_closed() -> None:
    open_case = _case("oracle:q-rev-03:open_session")
    left_id = open_case["request"]["parameters"]["left_session"]
    session = next(
        fact
        for fact in open_case["declaration"]["facts"]
        if fact["relation"] == "session" and fact["values"]["session_id"] == left_id
    )
    session["values"]["lifecycle_state"] = "open"
    session["values"]["completion_basis"] = "open_tail"
    row = evaluate_case(open_case)["rows"][0]
    assert row["completion_state"]["left"] == {
        "completion_basis": "open_tail",
        "lifecycle_state": "open",
    }

    mixed_case = _case("oracle:q-rev-03:differing_coverage")
    left_id = mixed_case["request"]["parameters"]["left_session"]
    call = next(
        fact
        for fact in mixed_case["declaration"]["facts"]
        if fact["relation"] == "canonical_call" and fact["values"]["session_id"] == left_id
    )
    del call["values"]["context_window_tokens"]
    with pytest.raises(SemanticError):
        evaluate_case(mixed_case)


def test_canonical_fact_mutation_changes_truth_but_source_metadata_does_not() -> None:
    baseline_case = _case("oracle:q-rev-03:differing_coverage")
    baseline = evaluate_case(baseline_case)

    fact_mutation = copy.deepcopy(baseline_case)
    left_id = fact_mutation["request"]["parameters"]["left_session"]
    call = next(
        fact
        for fact in fact_mutation["declaration"]["facts"]
        if fact["relation"] == "canonical_call" and fact["values"]["session_id"] == left_id
    )
    call["values"]["output_tokens"] += 1
    changed = evaluate_case(fact_mutation)
    assert changed["rows"] != baseline["rows"]
    assert changed["rows"][0]["token_deltas"]["output_tokens"] == 39

    source_mutation = copy.deepcopy(baseline_case)
    source_mutation["source_profile"] = {"synthetic_production_source": "mutated"}
    source_mutation["production_source"] = {"sentinel": "mutated"}
    assert evaluate_case(source_mutation) == baseline


def test_grading_sentinels_are_ignored_only_outside_the_answer_free_input() -> None:
    case = _case("oracle:q-acc-01:boundaries")
    baseline = evaluate_case(case)

    sentinel_case = copy.deepcopy(case)
    sentinel_case["grading_sentinel"] = {"mutated": True}
    assert evaluate_case(sentinel_case) == baseline

    for forbidden_key in sorted(FORBIDDEN_DATA_KEYS):
        forbidden_case = copy.deepcopy(case)
        forbidden_case[forbidden_key] = {"sentinel": "must-not-be-read"}
        with pytest.raises(SemanticError):
            evaluate_case(forbidden_case)


def test_closure_recomputes_membership_digests_and_rejects_drift_or_inaccessible_files() -> None:
    manifest = compute_closure(
        harness=INDEPENDENT_ROOT / "closure.py",
        consumer=INDEPENDENT_ROOT / "semantic.py",
        root=ROOT,
    )
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    lane = contract["lanes"]["independent"]
    checks = verify_closure(
        manifest,
        root=ROOT,
        forbidden_modules=lane["forbidden_module_prefixes"],
        forbidden_roles=lane["forbidden_overlap_roles"],
    )
    assert checks["membership_recomputed"]
    assert checks["digests_recomputed"]
    assert checks["all_files_accessible"]
    assert checks["forbidden_dependencies_absent"]
    assert checks["passed_before_grading"]

    drift = copy.deepcopy(manifest)
    drift["roots"][0]["sha256"] = "0" * 64
    with pytest.raises(ClosureError):
        verify_closure(drift, root=ROOT)

    inaccessible = copy.deepcopy(manifest)
    inaccessible["roots"][0]["path"] = (
        "tests/agent_kernel/fixtures/independent/missing-closure-root.py"
    )
    with pytest.raises(ClosureError):
        verify_closure(inaccessible, root=ROOT)

    membership = copy.deepcopy(manifest)
    init_path = "tests/agent_kernel/fixtures/independent/__init__.py"
    membership["imports"].append({"path": init_path, "sha256": _sha256(ROOT / init_path)})
    with pytest.raises(ClosureError):
        verify_closure(membership, root=ROOT)


def test_evaluate_case_fails_before_grading_when_closure_qualification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case("oracle:q-acc-01:boundaries")
    grading_entered = False

    def fail_if_graded(_case: Any) -> dict[str, Any]:
        nonlocal grading_entered
        grading_entered = True
        raise AssertionError("grading entered after closure failure")

    monkeypatch.setattr(
        independent_semantic,
        "_verify_independent_closure",
        lambda: (_ for _ in ()).throw(ClosureError("synthetic closure sentinel")),
    )
    monkeypatch.setattr(independent_semantic, "_evaluate_case_unchecked", fail_if_graded)
    with pytest.raises(ClosureError):
        evaluate_case(case)
    assert not grading_entered


def test_relative_from_import_is_recursive_and_forbidden_dependencies_fail_closed(
    tmp_path: Path,
) -> None:
    package = tmp_path / "tests" / "synthetic_package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "harness.py").write_text("", encoding="utf-8")
    (package / "consumer.py").write_text("from . import helper\n", encoding="utf-8")
    (package / "helper.py").write_text("import sqlite3\n", encoding="utf-8")

    manifest = compute_closure(
        harness=package / "harness.py",
        consumer=package / "consumer.py",
        root=tmp_path,
    )
    imported_paths = {record["path"] for record in manifest["imports"]}
    assert "tests/synthetic_package/helper.py" in imported_paths
    with pytest.raises(ClosureError):
        verify_closure(manifest, root=tmp_path, forbidden_modules=("sqlite3",))


def test_independent_closure_has_no_forbidden_imports_or_overlap_roles() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    lane = contract["lanes"]["independent"]
    modules = set().union(*(_module_imports(path) for path in INDEPENDENT_ROOT.glob("*.py")))

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in modules
        for forbidden in lane["forbidden_module_prefixes"]
    )
    manifest = compute_closure(
        harness=INDEPENDENT_ROOT / "closure.py",
        consumer=INDEPENDENT_ROOT / "semantic.py",
        root=ROOT,
    )
    assert {root["role"] for root in manifest["roots"]} == {"harness", "consumer"}
    assert all(root["role"] not in lane["forbidden_overlap_roles"] for root in manifest["roots"])
    init_path = "tests/agent_kernel/fixtures/independent/__init__.py"
    assert all(record["path"] != init_path for record in manifest["imports"])
