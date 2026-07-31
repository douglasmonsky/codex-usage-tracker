from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.agent_kernel.fixtures.oracles.seam_evidence import (
    validate_seam_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "docs"
    / "decisions"
    / "evidence"
    / "ck07a"
    / "fact-backed-oracle-and-seam-qualification-evidence.json"
)


def _passing_payload() -> dict:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for variant in payload["variants"]:
        variant["variant_predicates"] = [
            {"predicate": "source_record_native_turn_key", "passed": True},
            {"predicate": "published_call_canonical_identity", "passed": True},
        ]
    payload["measurements"]["lifecycle_transitions"] = [
        {"name": name, "passed": True}
        for name in (
            "initial",
            "same_lineage_rebuild",
            "replacement",
            "late_event",
            "recovery",
        )
    ]
    payload["measurements"]["byte_ratchets"]["complete_tree"] = {
        "baseline": 598_776,
        "observed": 1_348_201,
        "authority": {
            "packet": "CK-07A",
            "basis": "canonical_packet_explicit_complete_tree_authority",
            "maximum_authorized_bytes": 2_500_000,
        },
        "passed": True,
    }
    payload["review"] = {
        "status": "request_changes_resolved",
        "unresolved_findings": [],
        "resolved_findings": [f"finding-{index}" for index in range(1, 7)],
        "token_status": "not_measured",
    }
    return payload


def test_ck07a_evidence_is_complete_and_passed() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    validate_seam_evidence(payload)
    assert payload["status"] == "passed"
    assert all(item["status"] == "passed" for item in payload["seams"])
    assert all(item["status"] == "requalified" for item in payload["requalifications"])
    assert all(
        variant["request_matches"]
        and variant["rows_match"]
        and variant["grades_match"]
        and variant["ordered_references_match"]
        for variant in payload["variants"]
    )
    assert payload["measurements"]["unique_comparison_digest_count"] == 80
    assert (
        payload["measurements"]["response_bytes"]["maximum"]
        <= payload["measurements"]["response_bytes"]["ratchet_maximum"]
    )
    assert not payload["privacy"]["forbidden_source_findings"]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update(status="blocked"),
        lambda payload: payload["seams"][0].update(status="blocked"),
        lambda payload: payload["variants"][0].update(grades_match=False),
        lambda payload: payload["variants"][0]["variant_predicates"][0].update(passed=False),
        lambda payload: payload["variants"][1].update(
            comparison_digest=payload["variants"][0]["comparison_digest"]
        ),
        lambda payload: payload["measurements"]["lifecycle_transitions"][2].update(passed=False),
        lambda payload: payload["validation"][0].update(result="failed"),
        lambda payload: payload["privacy"].update(passed=False),
        lambda payload: payload["measurements"]["byte_ratchets"]["candidate_response"].update(
            passed=False
        ),
        lambda payload: payload["measurements"]["byte_ratchets"]["complete_tree"][
            "authority"
        ].update(maximum_authorized_bytes=1),
        lambda payload: payload["review"].update(unresolved_findings=["finding"]),
    ),
)
def test_ck07a_evidence_validation_fails_closed(mutation) -> None:
    payload = copy.deepcopy(_passing_payload())
    mutation(payload)
    with pytest.raises(ValueError):
        validate_seam_evidence(payload)
