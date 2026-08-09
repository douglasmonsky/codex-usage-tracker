from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts import qualify_ck08r1_answer_truth as qualification
from tests.agent_kernel.requalification import closure as closure_verifier
from tests.agent_kernel.requalification import production as production_replay
from tests.agent_kernel.requalification.closure import (
    ClosureError,
    compute_closure,
    verify_closure,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/decisions/evidence/ck08r1/answer-truth-requalification-v2.json"
SCHEMA = ROOT / "docs/decisions/evidence/ck08r1a" / "answer-truth-requalification-v2.schema.json"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def collected(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output = tmp_path_factory.mktemp("ck08r1") / "answer-truth.json"
    payload = qualification.qualify(output=output)
    assert output.read_bytes() == qualification.canonical_json_bytes(payload)
    return payload


def test_ck08r1_artifact_is_schema_valid_deterministic_and_committed(
    collected: dict[str, object],
) -> None:
    schema = _json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(collected)

    assert collected["schema"] == "codex-usage-tracker.answer-truth-requalification.v2"
    assert len(collected["variant_results"]) == 80  # type: ignore[arg-type]
    assert EVIDENCE.read_bytes() == qualification.canonical_json_bytes(collected)
    assert qualification.canonical_json_bytes(
        qualification.qualify(output=None)
    ) == qualification.canonical_json_bytes(collected)


def test_all_80_variants_match_rows_grades_order_evidence_and_provenance(
    collected: dict[str, object],
) -> None:
    variants = collected["variant_results"]
    assert isinstance(variants, list)
    assert len({item["oracle_id"] for item in variants}) == 80
    for item in variants:
        assert item["matches"] is True
        assert item["independent_rows"] == item["production_rows"]
        assert item["independent_grades"] == item["production_grades"]
        assert item["total_order"]
        assert item["ordered_evidence"]
        assert item["provenance"]


def test_authority_identities_and_both_lane_closures_are_recomputed(
    collected: dict[str, object],
) -> None:
    identities = qualification.recompute_authority_identities()
    assert identities["dependency_shas"] == collected["dependency_shas"]
    assert identities["authority_digests"] == collected["authority_digests"]
    assert identities["r1b_selected_paths"] == 23

    lanes = collected["lanes"]
    assert isinstance(lanes, list)
    assert [lane["lane"] for lane in lanes] == ["production", "independent"]
    for lane in lanes:
        checks = lane["closure_checks"]
        assert checks == {
            "all_files_accessible": True,
            "digests_recomputed": True,
            "forbidden_dependencies_absent": True,
            "membership_recomputed": True,
            "passed_before_grading": True,
        }
        assert lane["grading_checks"] == {
            "inaccessible": "baseline_answers_unchanged",
            "sentinel_mutated": "baseline_answers_unchanged",
        }


def test_closure_verifier_rejects_drift_inaccessibility_and_membership(
    tmp_path: Path,
) -> None:
    package = tmp_path / "tests/synthetic_closure"
    package.mkdir(parents=True)
    harness = package / "harness.py"
    consumer = package / "consumer.py"
    helper = package / "helper.py"
    (package / "__init__.py").write_text("", encoding="utf-8")
    harness.write_text("", encoding="utf-8")
    consumer.write_text("from . import helper\n", encoding="utf-8")
    helper.write_text("", encoding="utf-8")

    manifest = compute_closure(
        roots=(
            (harness, "harness"),
            (consumer, "consumer"),
        ),
        root=tmp_path,
    )
    checks = verify_closure(
        manifest,
        root=tmp_path,
        required_roles=("harness", "consumer"),
    )
    assert checks["passed_before_grading"] is True

    drift = copy.deepcopy(manifest)
    drift["roots"][0]["sha256"] = "0" * 64
    with pytest.raises(ClosureError, match="drift"):
        verify_closure(
            drift,
            root=tmp_path,
            required_roles=("harness", "consumer"),
        )

    inaccessible = copy.deepcopy(manifest)
    inaccessible["imports"][0]["path"] = "tests/synthetic_closure/missing.py"
    with pytest.raises(ClosureError, match="inaccessible"):
        verify_closure(
            inaccessible,
            root=tmp_path,
            required_roles=("harness", "consumer"),
        )

    membership = copy.deepcopy(manifest)
    membership["imports"] = []
    with pytest.raises(ClosureError, match="membership"):
        verify_closure(
            membership,
            root=tmp_path,
            required_roles=("harness", "consumer"),
        )


def test_authority_contradiction_stops_before_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compared = False

    def comparison_sentinel(*_args: object, **_kwargs: object) -> object:
        nonlocal compared
        compared = True
        raise AssertionError("comparison ran after authority failure")

    monkeypatch.setattr(
        qualification,
        "sha256_file",
        lambda _path: "0" * 64,
    )
    monkeypatch.setattr(qualification, "_collect_variants", comparison_sentinel)
    with pytest.raises(qualification.QualificationError, match="authority"):
        qualification.qualify(output=None)
    assert compared is False


def test_production_closure_covers_the_executed_src_consumer_and_canonical_digest(
    collected: dict[str, object],
) -> None:
    lanes = collected["lanes"]
    assert isinstance(lanes, list)
    production = next(item for item in lanes if item["lane"] == "production")
    closed_paths = {
        item["path"] for item in (*production["roots"], *production["transitive_local_imports"])
    }
    assert {
        "tests/agent_kernel/fixtures/oracles/database_replay.py",
        "src/codex_usage_tracker/agent_kernel/domain/plan_operands.py",
        "src/codex_usage_tracker/agent_kernel/query/compiler.py",
    }.issubset(closed_paths)
    digest_input = {
        "consumer": production["consumer"],
        "harness": production["harness"],
        "imports": production["transitive_local_imports"],
        "roots": production["roots"],
    }
    assert production["closure_digest"] == closure_verifier._manifest_digest(digest_input)


def test_declared_production_consumer_is_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = production_replay.database_replay.evaluate_published_question_case

    def altered_consumer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        result["rows"] = [*result["rows"], {"consumer_sentinel": True}]
        return result

    monkeypatch.setattr(
        production_replay.database_replay,
        "evaluate_published_question_case",
        altered_consumer,
    )
    with pytest.raises(qualification.QualificationError, match="answer comparison"):
        qualification.qualify(output=None)


def test_grading_isolation_covers_every_variant_and_plan() -> None:
    assert qualification.last_grading_matrix() == {
        "independent": {"inaccessible": 80, "sentinel_mutated": 80},
        "production": {"inaccessible": 80, "sentinel_mutated": 80},
        "plan_count": 40,
        "variant_count": 80,
    }


def test_grading_mutation_inaccessibility_and_semantic_mutations_pass(
    collected: dict[str, object],
) -> None:
    lanes = collected["lanes"]
    assert isinstance(lanes, list)
    assert all(
        lane["grading_checks"]["sentinel_mutated"] == "baseline_answers_unchanged"
        and lane["grading_checks"]["inaccessible"] == "baseline_answers_unchanged"
        for lane in lanes
    )
    assert collected["mutation_results"] == {
        "canonical_fact": {
            "independent_changed": True,
            "production_changed": True,
        },
        "production_source": {
            "independent_unchanged": True,
            "production_changed": True,
        },
    }


def test_query_service_matrix_is_two_supported_and_nineteen_fail_closed(
    collected: dict[str, object],
) -> None:
    matrix = qualification.last_query_service_matrix()
    assert matrix["supported_plans"] == [
        "data_health",
        "latest_publication_delta",
    ]
    assert matrix["supported_variant_count"] == 4
    assert len(matrix["failed_closed_plans"]) == 19
    assert matrix["projection_added"] is False
    assert matrix["query_only"] is True
    assert all(item["matches"] is True for item in collected["variant_results"])  # type: ignore[index]


def test_artifact_contains_synthetic_structural_evidence_only(
    collected: dict[str, object],
) -> None:
    encoded = qualification.canonical_json_bytes(collected).decode("utf-8")
    forbidden = (
        '"prompt"',
        '"response"',
        '"reasoning_content"',
        '"command_body"',
        '"tool_output_body"',
        "sk-proj-",
        "/Users/",
    )
    assert not any(token in encoded for token in forbidden)
    assert all(
        link.startswith("docs/decisions/evidence/")
        for link in collected["superseded_evidence_links"]  # type: ignore[index]
    )
    assert _sha(SCHEMA) == collected["authority_digests"]["evidence_schema"]  # type: ignore[index]
