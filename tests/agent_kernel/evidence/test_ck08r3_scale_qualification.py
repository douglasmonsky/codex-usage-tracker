from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import scripts.qualify_ck08r3_evidence_scale as qualification
from scripts.qualify_ck08r3_evidence_scale import (
    DEPENDENCY_SHA,
    FROZEN_RUNTIME_DEPENDENCIES,
    MAX_EVIDENCE_BYTES,
    MAX_EVIDENCE_LIMIT,
    SELECTOR_SCOPE_KINDS,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs" / "decisions" / "evidence" / "ck08r3" / "evidence-scale-qualification.json"
SCHEMA = ROOT / "docs" / "decisions" / "evidence" / "ck08r0" / "corrective-lane-evidence-v1.schema.json"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validate(payload: dict[str, Any]) -> None:
    schema = _json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": "#/$defs/evidenceScale",
        }
    ).validate(payload)


def test_ck08r3_scale_artifact_binds_both_frozen_profiles() -> None:
    payload = _json(EVIDENCE)
    _validate(payload)

    assert payload["dependency_sha"] == DEPENDENCY_SHA
    assert payload["first_failure"] is None
    assert payload["direction"] == "next"
    assert "LIMIT ?" in payload["sql"]
    assert "COUNT(" not in payload["sql"].upper()
    assert payload["rows"] <= MAX_EVIDENCE_LIMIT
    assert payload["response_bytes"] <= MAX_EVIDENCE_BYTES
    assert len(payload["timing_samples_ms"]) == 5
    assert payload["rss_bytes"] > 0

    explain_details = [
        str(item["detail"])
        for page in payload["explain"]
        for item in page["plan"]
    ]
    assert not any("SCAN stream" in detail for detail in explain_details)
    assert not any("MATERIALIZE model_calls_visible" in detail for detail in explain_details)
    assert not any("AUTOMATIC COVERING INDEX" in detail for detail in explain_details)

    checks = payload["gap_duplicate_checks"]
    assert checks["synthetic_only"] is True
    assert checks["publication_base_committed"] is True
    assert checks["query_only_one_snapshot"] is True
    assert checks["typed_selector_seven_part_oracle"] is True
    assert checks["first_deep_no_gaps_or_duplicates"] is True
    assert checks["all_views_scopes_directions"] is True
    assert checks["late_event_fixture"] is True
    assert checks["exact_count_requested"] is False
    assert checks["byte_truncation_bounded"] is True
    assert checks["cursor_tamper_and_replacement_rejected"] is True
    assert checks["scale_execution"] == "standard_and_production_passed"

    profile_measurements = next(
        item["profiles"]
        for item in payload["noise"]
        if item.get("kind") == "profile_measurements"
    )
    by_name = {str(item["name"]): item for item in profile_measurements}
    assert set(by_name) == {"standard", "production"}
    assert {name: item["model_calls"] for name, item in by_name.items()} == {
        "standard": 100_000,
        "production": 1_316_864,
    }
    for item in by_name.values():
        assert item["base_publication_receipt"]["status"] == "committed"
        assert item["materialization"]["visible_after"] == item["model_calls"]
        assert item["materialization"]["typed_provenance"] is True
        assert item["late_event_count"] == 1
        assert item["matrix"]["selectors"] == len(SELECTOR_SCOPE_KINDS)
        assert tuple(item["matrix"]["selector_kinds"]) == SELECTOR_SCOPE_KINDS
        assert item["matrix"]["views"] == 7
        assert item["matrix"]["directions"] == 2
        assert item["matrix"]["outcomes"] == len(SELECTOR_SCOPE_KINDS) * 7 * 2
        assert item["matrix"]["deep_pages"] > 0
        assert item["matrix"]["passed"] is True
        assert item["budget"]["passed"] is True
        assert item["timing_p95_ms"] <= item["budget"]["service_p95_ms"]
        assert item["sql_p95_ms"] <= item["budget"]["sql_p95_ms"]
        assert item["maximum_rows"] <= MAX_EVIDENCE_LIMIT
        assert item["maximum_response_bytes"] <= MAX_EVIDENCE_BYTES
        assert len(item["timing_samples_ms"]) == 5
        assert len(item["sql_timing_samples_ms"]) == 5
        assert all(check["first_matches_oracle"] for check in item["call_oracle"].values())
        assert all(check["deep_matches_oracle"] for check in item["call_oracle"].values())
        assert all(check["typed_provenance"] for check in item["call_oracle"].values())

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "prompt" not in serialized
    assert "response_body" not in serialized
    assert "tool_body" not in serialized
    assert "secret" not in serialized


def test_ck08r3_collector_rejects_frozen_consumer_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_path = "src/codex_usage_tracker/agent_kernel/evidence/service.py"
    original_sha = qualification._sha

    def drifted_sha(path: Path) -> str:
        if path == ROOT / service_path:
            return "0" * 64
        return original_sha(path)

    monkeypatch.setattr(qualification, "_sha", drifted_sha)
    with pytest.raises(ValueError, match=r"frozen CK-08R3 runtime dependency stale"):
        qualification._load_authority()

    assert service_path in FROZEN_RUNTIME_DEPENDENCIES
    assert hashlib.sha256((ROOT / service_path).read_bytes()).hexdigest() == FROZEN_RUNTIME_DEPENDENCIES[service_path]
