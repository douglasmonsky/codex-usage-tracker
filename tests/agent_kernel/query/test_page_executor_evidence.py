from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

_ROOT = Path(__file__).resolve().parents[3]
_EVIDENCE_ROOT = _ROOT / "docs" / "decisions" / "evidence"
_ARTIFACTS = (
    _EVIDENCE_ROOT / "ck08r2" / "data-health-page-executor-benchmark-v2.json",
    _EVIDENCE_ROOT
    / "ck08r2"
    / "latest-publication-delta-page-executor-benchmark-v2.json",
)
_AUTHORITY = _EVIDENCE_ROOT / "ckqg1a0" / "page-executor-source-supersession-authority.json"
_AUTHORITY_SCHEMA = _EVIDENCE_ROOT / "ckqg1a0" / "page-executor-source-supersession-authority.schema.json"
_SOURCE_PATH = "src/codex_usage_tracker/agent_kernel/query/page_executor.py"
_PREDECESSOR = "2a48a63e0fbb18173b8e0abe09d65309f76bf59b4796e35d6b2f97dea95df305"
_SUCCESSOR = "9e80c8677dd4ceadc4fbd66681aedef78528b1ad4f50edc7a04f4b1c7ac12f31"
_R2_MANIFEST = "docs/decisions/evidence/ck08r2/physical-page-executor-evidence.json"
_R2_MANIFEST_SHA = "0a1f9ee919e065ba707826fc7c308748a7b6810a358f957aa6608ee0ff4d3c08"
_BASELINE_SHA = "c490d954a5e9d09c61f884d51e3b9d3196af5615887f409c36f8469d1b2b6cf9"
_PACKAGE_BUDGET_PATH = "config/kernel-release-candidate-budget.json"
_PACKAGE_BUDGET_HISTORICAL_SHA = "be2754c9b198b9c6f80c9213a4a22c9086285fdf551077dcd7585e7bcea5623b"
_PACKAGE_POLICY = _EVIDENCE_ROOT / "kernel-release-candidate-package-budget-supersession.json"


def _assert_indexed_explain(payload: dict[str, object]) -> None:
    explain = payload["explain"]
    assert isinstance(explain, list)
    details = tuple(str(item["detail"]) for item in explain)
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
    plan_id = str(payload["plan_id"])
    assert all(item in details for item in required[plan_id])


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_supersession_bindings(authority: dict[str, object], current_source_sha: str) -> None:
    predecessor = authority["predecessor"]
    successor = authority["selected_successor"]
    baseline = authority["maintainability_baseline"]
    assert authority["authority_base_sha"] == "e26d7d5bfa32bf74c0855ed87266aca83a7ebce1"
    assert authority["source_path"] == _SOURCE_PATH
    assert predecessor["sha256"] == _PREDECESSOR
    assert predecessor["accepted_merge_sha"] == "53ab22cb54b9a6f30009caeb6bb22a3a57033261"
    assert predecessor["manifest"] == {"path": _R2_MANIFEST, "sha256": _R2_MANIFEST_SHA}
    assert successor["sha256"] == _SUCCESSOR
    assert successor["status"] == "permitted_not_accepted"
    assert successor["blocked_task"] == "019fbe2b-cce0-7ed2-87c5-71f5aff5594a"
    assert successor["retained_branch"] == "fix/ck-qg1a-page-executor-complexity"
    assert authority["consumer_test_seam"] == {
        "path": "tests/agent_kernel/query/test_page_executor_evidence.py",
        "test": "test_ck08r2_manifest_binds_superseded_and_current_artifacts",
    }
    assert baseline == {
        "pr": 392,
        "head_sha": "29f18ae178a4d048e9d4bd1ae49a4307dd8472dd",
        "path": "config/agent-kernel/maintainability-baseline-v1.json",
        "sha256": _BASELINE_SHA,
        "schema": "codex-usage-tracker.agent-kernel-maintainability-baseline.v1",
        "tool_identity": "xenon==0.9.3;radon==6.0.1",
        "normalization_version": "xenon-threshold-findings-v1",
        "thresholds": {"block": "C", "module": "B", "average": "B"},
    }
    baseline_path = _ROOT / baseline["path"]
    if baseline_path.exists():
        assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == _BASELINE_SHA
    assert set(authority["preserved_semantics"]) == {
        "request_validation", "optional_entity_kind_and_limit", "typed_request_digest_binding",
        "keyset_cursor_and_total_order", "query_only_sqlite", "limit_page_size_plus_one",
        "exact_count_default_false_opt_in", "indexed_explain_gates", "two_supported_direct_plans",
        "nineteen_other_plans_fail_closed", "no_projection",
    }
    assert set(authority["constraints"]) == {
        "predecessor_remains_historically_verifiable", "selected_successor_only", "third_digest_fails",
        "missing_predecessor_fails", "mismatched_manifest_or_baseline_fails", "generic_source_drift_forbidden",
    }
    assert current_source_sha in {_PREDECESSOR, _SUCCESSOR}


def test_ck08r2_page_executor_artifacts_match_frozen_lane_schema() -> None:
    schema = _json(
        _EVIDENCE_ROOT
        / "ck08r0"
        / "corrective-lane-evidence-v1.schema.json"
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    payloads = [_json(path) for path in _ARTIFACTS]

    assert {payload["plan_id"] for payload in payloads} == {
        "data_health",
        "latest_publication_delta",
    }
    for payload in payloads:
        validator.validate(payload)
        assert payload["dependency_sha"] == (
            "306cef37eea2ae017aca824d898cc435f7e1bea0"
        )
        assert "ORDER BY" in payload["sql"]
        assert "LIMIT ?" in payload["sql"]
        assert payload["bound_parameters"][-1] == 2
        assert payload["rows_decoded"] <= 2
        assert payload["exact_count_checks"]["default_is_false"] is True
        assert payload["cursor_checks"]["deep_page_after_anchor_empty"] is True
        assert payload["cursor_checks"]["stale_anchor_rejected"] is True
        assert payload["first_failure"] is None
        _assert_indexed_explain(payload)
        assert all(
            len(samples) == 5
            for samples in payload["stage_timings_ms"].values()
        )


def test_ck08r2_manifest_binds_superseded_and_current_artifacts() -> None:
    manifest = _json(
        _EVIDENCE_ROOT / "ck08r2" / "physical-page-executor-evidence.json"
    )
    assert manifest["dependency_sha"] == (
        "306cef37eea2ae017aca824d898cc435f7e1bea0"
    )
    assert manifest["projection_added"] is False
    assert manifest["unsupported_plan_count"] == 19

    authority = _json(_AUTHORITY)
    package_policy = _json(_PACKAGE_POLICY)
    source_artifacts = {item["path"]: item for item in manifest["source_artifacts"]}
    assert source_artifacts[_SOURCE_PATH]["sha256"] == _PREDECESSOR
    assert source_artifacts[_PACKAGE_BUDGET_PATH]["sha256"] == _PACKAGE_BUDGET_HISTORICAL_SHA
    assert package_policy["historical_active_config"] == {
        "path": _PACKAGE_BUDGET_PATH,
        "sha256": _PACKAGE_BUDGET_HISTORICAL_SHA,
    }
    for artifact in [
        *manifest["page_executor_artifacts"],
        *[item for path, item in source_artifacts.items() if path != _SOURCE_PATH],
    ]:
        source = _ROOT / artifact["path"]
        if artifact["path"] == _PACKAGE_BUDGET_PATH:
            assert package_policy["package_ceilings"]["wheel_bytes"] == {
                "historical_ceiling_bytes": 383000,
                "active_ceiling_bytes": 1000000,
            }
            assert package_policy["package_ceilings"]["sdist_bytes"] == {
                "historical_ceiling_bytes": 828000,
                "active_ceiling_bytes": 2000000,
            }
        else:
            assert hashlib.sha256(source.read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256(
        (_ROOT / _R2_MANIFEST).read_bytes()
    ).hexdigest() == _R2_MANIFEST_SHA
    _assert_supersession_bindings(
        authority,
        hashlib.sha256((_ROOT / _SOURCE_PATH).read_bytes()).hexdigest(),
    )
    schema = _json(_AUTHORITY_SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    expected_r2 = {
        path.relative_to(_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _ARTIFACTS
    }
    assert {item["path"]: item["sha256"] for item in authority["r2_artifacts"]} == expected_r2
    changed = deepcopy(authority)
    changed["r2_artifacts"][0]["path"] = "changed.json"
    with pytest.raises(AssertionError):
        assert {item["path"]: item["sha256"] for item in changed["r2_artifacts"]} == expected_r2
    missing_predecessor = deepcopy(authority)
    del missing_predecessor["predecessor"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(missing_predecessor)
    for target, field in (("predecessor", "sha256"), ("selected_successor", "sha256"), ("maintainability_baseline", "sha256")):
        changed = deepcopy(authority)
        changed[target][field] = "f" * 64
        with pytest.raises(AssertionError):
            _assert_supersession_bindings(changed, _PREDECESSOR)
    for field in ("blocked_task", "retained_branch"):
        changed = deepcopy(authority)
        changed["selected_successor"][field] = "changed"
        with pytest.raises(AssertionError):
            _assert_supersession_bindings(changed, _PREDECESSOR)
    changed = deepcopy(authority)
    changed["predecessor"]["manifest"]["sha256"] = "f" * 64
    with pytest.raises(AssertionError):
        _assert_supersession_bindings(changed, _PREDECESSOR)
