from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.agent_kernel.contracts.reference.selector_provenance import (
    EvidenceReferenceV1,
    SelectorProvenanceError,
    validate_evidence_references_v1,
    validate_reference_stability_v1,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = _ROOT / "config/agent-kernel/selector-provenance-v1.json"
_SCHEMA = _ROOT / "config/agent-kernel/selector-provenance-v1.schema.json"
_CATALOG = _ROOT / "config/agent-kernel/question-catalog-v1.json"
_LOGICAL = _ROOT / "config/agent-kernel/logical-contract-v1.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_selector_provenance_schema_reconciles_all_logical_and_catalog_kinds() -> None:
    contract, schema = _load(_CONTRACT), _load(_SCHEMA)
    catalog, logical = _load(_CATALOG), _load(_LOGICAL)
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(contract)) == []
    assert contract["selector_kinds"] == catalog["selector_kinds"]
    assert set(contract["selector_kinds"]) == set(logical["selector_kinds"])
    assert {item["kind"] for item in contract["ownership"]} == set(contract["selector_kinds"])
    assert {item["kind"] for item in contract["provenance_contracts"]} == set(
        contract["provenance_kinds"]
    )


def test_ordered_role_tagged_references_allow_repeated_kinds_and_fail_closed() -> None:
    fields = {
        "request_derivation": (
            "request_digest",
            "parameter_role",
            "start_us",
            "end_us",
            "timezone",
        )
    }
    references = [
        EvidenceReferenceV1(
            role=role,
            selector_kind="window",
            selector=f"window:window:v1:{role}",
            logical_id=f"window:v1:{role}",
            provenance_kind="request_derivation",
            provenance={
                "request_digest": "a" * 64,
                "parameter_role": role,
                "start_us": start,
                "end_us": end,
                "timezone": "UTC",
            },
        )
        for role, start, end in (
            ("previous_window", 0, 10),
            ("current_window", 10, 20),
        )
    ]
    assert validate_evidence_references_v1(
        [
            ("previous_window", "window"),
            ("current_window", "window"),
        ],
        references,
        {"window": {"provenance_kind": "request_derivation", "required_provenance_fields": fields["request_derivation"]}},
        lambda _kind, _logical_id: True,
    ) == tuple(references)
    with pytest.raises(SelectorProvenanceError, match="sequences differ"):
        validate_evidence_references_v1(
            [("current_window", "window")],
            references,
            {"window": {"provenance_kind": "request_derivation", "required_provenance_fields": fields["request_derivation"]}},
            lambda _kind, _logical_id: True,
        )
    broken = [
        EvidenceReferenceV1(
            **{
                **references[0].__dict__,
                "provenance": {
                    **references[0].provenance,
                    "request_digest": "",
                },
            }
        )
    ]
    with pytest.raises(SelectorProvenanceError, match="incomplete"):
        validate_evidence_references_v1(
            [("previous_window", "window")],
            broken,
            {"window": {"provenance_kind": "request_derivation", "required_provenance_fields": fields["request_derivation"]}},
            lambda _kind, _logical_id: True,
        )


def test_four_no_window_variants_have_plan_specific_scope() -> None:
    by_question = {
        item["question_id"]: item
        for item in _load(_CONTRACT)["plan_scope_sources"]
    }
    assert by_question["Q-ALW-02"]["scope_source"] == (
        "allowance_observation_pair"
    )
    assert by_question["Q-OPS-01"]["scope_source"] == (
        "latest_accepted_publication_delta"
    )
    assert {
        variant
        for item in by_question.values()
        for variant in item["variants"]
    } == {
        "empty_interval",
        "same_time_boundary",
        "no_change",
        "recanonicalized_owner",
    }


@pytest.mark.parametrize(
    "lifecycle",
    ["clean_rebuild", "source_replacement", "late_event_replay"],
)
def test_semantic_selector_is_stable_when_occurrences_relocate(
    lifecycle: str,
) -> None:
    baseline = [
        EvidenceReferenceV1(
            role="selected_call",
            selector_kind="call",
            selector="call:call:v1:stable",
            logical_id="call:v1:stable",
            provenance_kind="source_occurrence",
            provenance={"occurrences": [{"revision": "a", "ordinal": 1}]},
        )
    ]
    replayed = [
        EvidenceReferenceV1(
            **{
                **baseline[0].__dict__,
                "provenance": {
                    "occurrences": [
                        {"revision": lifecycle, "ordinal": 2},
                        {"revision": lifecycle, "ordinal": 3},
                    ]
                },
            }
        )
    ]
    assert validate_reference_stability_v1(
        baseline,
        replayed,
        {"source_occurrence": ()},
    ) == tuple(replayed)
    changed = [
        EvidenceReferenceV1(
            **{
                **replayed[0].__dict__,
                "selector": "call:call:v1:changed",
            }
        )
    ]
    with pytest.raises(SelectorProvenanceError, match="semantic selector changed"):
        validate_reference_stability_v1(
            baseline,
            changed,
            {"source_occurrence": ()},
        )
