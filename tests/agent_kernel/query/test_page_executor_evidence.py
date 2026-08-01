from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[3]
_EVIDENCE_ROOT = _ROOT / "docs" / "decisions" / "evidence"
_ARTIFACTS = (
    _EVIDENCE_ROOT / "ck08r2" / "data-health-page-executor-benchmark-v2.json",
    _EVIDENCE_ROOT
    / "ck08r2"
    / "latest-publication-delta-page-executor-benchmark-v2.json",
)


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

    artifacts = [
        *manifest["source_artifacts"],
        *manifest["page_executor_artifacts"],
    ]
    for artifact in artifacts:
        source = _ROOT / artifact["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == artifact["sha256"]
