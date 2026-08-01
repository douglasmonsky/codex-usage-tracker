from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import scripts.collect_ck08_evidence as collector
from scripts.collect_ck08_evidence import collect, validate_evidence

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck08"
    / "fact-backed-query-and-evidence-qualification.json"
)
R2_EVIDENCE = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck08r2"
    / "physical-page-executor-evidence.json"
)


def _payload() -> dict[str, object]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_ck08_historical_evidence_is_preserved_and_r2_supersedes_runtime() -> None:
    payload = _payload()
    validate_evidence(payload)
    with pytest.raises(
        ValueError,
        match="raw scale benchmark does not match reviewed source",
    ):
        collect()

    assert payload["status"] == "passed"
    assert payload["completion_claimed"] is True
    assert payload["counts"]["admitted_plans"] == 21
    assert payload["counts"]["admitted_variants"] == 42
    assert payload["counts"]["unique_comparison_digests"] == 42
    assert all(
        all(variant["parity"].values())
        for variant in payload["variants"]
    )
    assert all(
        variant["explain"]["sources"]
        and variant["explain"]["explain_structure"]
        for variant in payload["variants"]
    )
    assert payload["measurements"]["cursor_and_exact_count"]["passed"] is True
    assert payload["security"]["passed"] is True
    assert payload["scale"]["passed"] is True
    assert payload["scale"]["fact_table_sufficient_count"] == 3
    assert payload["scale"]["projection_required_count"] == 18
    assert {item["classification"] for item in payload["plans"]} == {
        "fact_table_sufficient",
        "projection_required",
    }
    r2 = json.loads(R2_EVIDENCE.read_text(encoding="utf-8"))
    assert r2["dependency_sha"] == "306cef37eea2ae017aca824d898cc435f7e1bea0"
    assert r2["supported_direct_plans"] == [
        "data_health",
        "latest_publication_delta",
    ]
    assert r2["unsupported_plan_count"] == 19
    assert r2["projection_added"] is False


def test_ck08_durable_evidence_matches_bounded_contract() -> None:
    payload = _payload()

    validate_evidence(payload)
    assert payload["schema"].endswith("qualification.v1")
    assert payload["task_name"] == "worker CK08 query-evidence"
    assert payload["authority"]["admitted_variant_count"] == 42
    assert payload["measurements"]["repetitions"]["first_samples_preserved"] is True
    assert payload["measurements"]["repetitions"]["waived_repetitions"] == [3, 4]
    assert payload["measurements"]["repetitions"]["strict_five_run_aggregate_claimed"] is False
    assert payload["scale"]["unresolved_gates"] == []
    assert payload["unresolved_gates"] == []
    assert payload["review"]["status"] == "passed"
    assert payload["review"]["accepted_findings"] == 3


@pytest.mark.parametrize("field", ("reviewed_source_digest", "measurements_sha256"))
def test_ck08_raw_scale_benchmark_fails_closed_when_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    raw = json.loads(collector.RAW_SCALE_PATH.read_text(encoding="utf-8"))
    raw[field] = "0" * 64
    stale = tmp_path / "stale-scale.json"
    stale.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(collector, "RAW_SCALE_PATH", stale)

    with pytest.raises(ValueError, match="raw scale"):
        collect()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.update(status="blocked"),
        lambda value: value.update(completion_claimed=False),
        lambda value: value["variants"][0]["parity"].update(rows=False),
        lambda value: value["variants"][0].update(
            comparison_digest=value["variants"][1]["comparison_digest"]
        ),
        lambda value: value["variants"][0]["explain"].update(sources=[]),
        lambda value: value["measurements"]["cursor_and_exact_count"].update(passed=False),
        lambda value: value["security"].update(forbidden_source_findings=["question_cases"]),
        lambda value: value["scale"].update(passed=False),
        lambda value: value["plans"][0].update(classification="fact_table_sufficient"),
        lambda value: value["measurements"]["repetitions"].update(
            strict_five_run_aggregate_claimed=True
        ),
    ),
)
def test_ck08_evidence_validation_fails_closed(mutation) -> None:
    payload = copy.deepcopy(_payload())

    mutation(payload)
    with pytest.raises(ValueError):
        validate_evidence(payload)
