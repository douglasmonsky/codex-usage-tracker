from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "config/agent-kernel/answer-semantics-v1.json"
SCHEMA_PATH = ROOT / "config/agent-kernel/answer-semantics-v1.schema.json"
VECTORS_PATH = ROOT / "tests/agent_kernel/fixtures/contracts/answer-semantics-v1-vectors.json"
EVIDENCE_SCHEMA_PATH = (
    ROOT
    / "docs/decisions/evidence/ck08r1a/answer-truth-requalification-v2.schema.json"
)

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
BOUNDARY_ORDER = (
    "event_at_us_is_null",
    "event_at_us",
    "source_rank",
    "source_order",
    "event_kind_order",
    "logical_id",
    "transition_rank",
)
TOKEN_CLASSES = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_answer_semantics_contract_and_vectors_are_schema_valid_and_digest_bound() -> None:
    schema = _json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    contract = _json(CONTRACT_PATH)
    vectors = _json(VECTORS_PATH)

    validator.validate(contract)
    validator.validate(vectors)
    assert vectors["contract_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert contract["packet"] == "CK-08R1A"
    assert contract["status"] == "frozen"
    assert contract["sdist_ceiling_bytes"] == 2000000


def test_q_rev_03_freezes_all_fields_sources_joins_missingness_and_sensitivity() -> None:
    contract = _json(CONTRACT_PATH)
    vectors = _json(VECTORS_PATH)
    question = contract["questions"]["Q-REV-03"]  # type: ignore[index]
    fields = question["fields"]  # type: ignore[index]

    assert tuple(fields) == Q_REV_FIELDS
    assert all(
        set(fields[field])  # type: ignore[index]
        == {"shape", "sources", "joins", "missing_empty", "sensitivity"}
        for field in Q_REV_FIELDS
    )
    assert all(
        fields[field]["shape"]  # type: ignore[index]
        and fields[field]["sources"]  # type: ignore[index]
        and fields[field]["joins"]  # type: ignore[index]
        and fields[field]["missing_empty"]  # type: ignore[index]
        and fields[field]["sensitivity"]  # type: ignore[index]
        for field in Q_REV_FIELDS
    )
    assert all(
        source["relation"] and source["fields"]  # type: ignore[index]
        for field in Q_REV_FIELDS
        for source in fields[field]["sources"]  # type: ignore[index]
    )
    assert question["side_scope"] == {  # type: ignore[index]
        "identity": "requested_stable_session_id",
        "window": "[start_us,end_us)",
    }
    assert question["available_empty"] == "typed_zero_or_empty"  # type: ignore[index]
    assert question["missing_required"] == "fail_closed"  # type: ignore[index]

    isolation = vectors["q_rev_03"]["field_isolation"]  # type: ignore[index]
    assert tuple(item["field"] for item in isolation) == Q_REV_FIELDS
    assert all(item["expected_changed_fields"] == [item["field"]] for item in isolation)
    assert all(
        item["expected_unchanged_fields"]
        == [field for field in Q_REV_FIELDS if field != item["field"]]
        for item in isolation
    )
    assert {
        item["id"] for item in vectors["q_rev_03"]["missing_empty"]  # type: ignore[index]
    } == {
        "available_empty",
        "context_capability_unavailable",
        "mixed_context_missing",
        "missing_hierarchy",
        "missing_token_class",
        "absent_session",
        "duplicate_session",
        "malformed_session",
        "dangling_resource",
        "conflicting_resource",
        "unknown_tool_lifecycle",
    }


def test_q_wf_02_freezes_complete_boundaries_and_required_vectors() -> None:
    contract = _json(CONTRACT_PATH)
    vectors = _json(VECTORS_PATH)
    question = contract["questions"]["Q-WF-02"]  # type: ignore[index]

    assert tuple(question["boundary_order"]) == BOUNDARY_ORDER  # type: ignore[index]
    assert question["boundaries"] == {  # type: ignore[index]
        "action": "earliest_tool_start",
        "success": "earliest_terminal_succeeded_transition",
        "mutation": "earliest_state_change",
    }
    assert tuple(question["token_sum"]["classes"]) == TOKEN_CLASSES  # type: ignore[index]
    assert question["token_sum"]["comparison"] == "strictly_before_boundary"  # type: ignore[index]
    assert question["tool_coordinates"] == {  # type: ignore[index]
        "start": "complete_seven_part_coordinate",
        "terminal": "complete_seven_part_coordinate",
    }
    assert question["coordinate_sources"] == {  # type: ignore[index]
        "tool_start": {
            "relation": "tool_invocation",
            "logical_id": "tool_id",
            "fields": [
                "start_at_us",
                "start_source_rank",
                "start_source_order",
                "start_event_kind_order",
                "start_transition_rank",
            ],
        },
        "tool_terminal": {
            "relation": "tool_invocation",
            "logical_id": "tool_id",
            "fields": [
                "terminal_at_us",
                "terminal_source_rank",
                "terminal_source_order",
                "terminal_event_kind_order",
                "terminal_transition_rank",
                "lifecycle",
            ],
        },
        "state_change": {
            "relation": "state_change",
            "logical_id": "state_change_id",
            "fields": [
                "event_at_us",
                "source_rank",
                "source_order",
                "event_kind_order",
                "transition_rank",
            ],
        },
    }
    assert question["token_sum"]["present_boundary_without_prior_call"] == 0  # type: ignore[index]
    assert question["token_sum"]["absent_boundary"] is None  # type: ignore[index]
    assert question["token_sum"]["missing_prior_token_class"] is None  # type: ignore[index]
    assert {
        item["id"] for item in vectors["q_wf_02"]  # type: ignore[index]
    } == {
        "between_start_success",
        "failed_then_success",
        "absent_boundaries",
        "present_without_prior_call",
        "missing_prior_token",
        "seven_part_tie",
        "delayed_mutation",
    }
    between = next(
        item
        for item in vectors["q_wf_02"]  # type: ignore[index]
        if item["id"] == "between_start_success"
    )
    assert between["expected"]["first_action_tokens"] == 4
    assert between["expected"]["first_success_tokens"] == 12
    assert between["expected"]["first_mutation_tokens"] == 12


def test_recursive_closure_and_grading_gates_are_enforceable_and_ordered() -> None:
    contract = _json(CONTRACT_PATH)
    vectors = _json(VECTORS_PATH)
    closure = contract["closure"]  # type: ignore[index]
    example = vectors["closure"]["canonical"]  # type: ignore[index]
    digest_input = {
        "consumer": example["consumer"],
        "harness": example["harness"],
        "imports": example["imports"],
        "roots": example["roots"],
    }

    assert closure["path_order"] == "unicode_codepoint_ascending"  # type: ignore[index]
    assert closure["file_digest"] == "sha256_exact_bytes"  # type: ignore[index]
    assert closure["closure_digest"] == "sha256_canonical_json_utf8"  # type: ignore[index]
    assert [item["path"] for item in example["roots"]] == sorted(  # type: ignore[index]
        item["path"] for item in example["roots"]  # type: ignore[index]
    )
    assert [item["path"] for item in example["imports"]] == sorted(  # type: ignore[index]
        item["path"] for item in example["imports"]  # type: ignore[index]
    )
    assert example["closure_digest"] == _canonical_digest(digest_input)
    assert contract["gate_order"] == [  # type: ignore[index]
        "closure_membership",
        "closure_digest",
        "closure_accessibility",
        "grading_independence",
        "answer_comparison",
    ]
    assert vectors["closure"]["negative"] == [  # type: ignore[index]
        {"id": "drift", "outcome": "reject_before_grading"},
        {"id": "inaccessible", "outcome": "reject_before_grading"},
    ]
    assert vectors["grading"] == {  # type: ignore[index]
        "sentinel_mutated": [
            {
                "id": "production_grading_sentinel",
                "lane": "production",
                "outcome": "baseline_answers_unchanged",
            },
            {
                "id": "independent_grading_sentinel",
                "lane": "independent",
                "outcome": "baseline_answers_unchanged",
            },
        ],
        "inaccessible": [
            {
                "id": "production_grading_inaccessible",
                "lane": "production",
                "outcome": "baseline_answers_unchanged",
            },
            {
                "id": "independent_grading_inaccessible",
                "lane": "independent",
                "outcome": "baseline_answers_unchanged",
            },
        ],
        "mutations": [
            {"id": "canonical_fact", "production": "changed", "independent": "changed"},
            {"id": "production_source", "production": "changed", "independent": "unchanged"},
        ],
    }

    evidence_schema = _json(EVIDENCE_SCHEMA_PATH)
    Draft202012Validator.check_schema(evidence_schema)
    evidence = evidence_schema["$defs"]["answerTruth"]  # type: ignore[index]
    assert evidence["properties"]["schema"]["const"] == (  # type: ignore[index]
        "codex-usage-tracker.answer-truth-requalification.v2"
    )
    assert evidence["properties"]["variant_results"]["minItems"] == 80  # type: ignore[index]
    assert evidence["properties"]["variant_results"]["maxItems"] == 80  # type: ignore[index]
    assert evidence["properties"]["gate_order"]["const"] == contract["gate_order"]  # type: ignore[index]


def test_independent_lane_excludes_production_database_replay_and_grading_truth() -> None:
    contract = _json(CONTRACT_PATH)
    lane = contract["lanes"]["independent"]  # type: ignore[index]

    assert lane["forbidden_module_prefixes"] == [
        "codex_usage_tracker.agent_kernel.domain.formulas",
        "codex_usage_tracker.agent_kernel.domain.plan_derivations",
        "codex_usage_tracker.agent_kernel.domain.plan_operands",
        "codex_usage_tracker.agent_kernel.query",
        "codex_usage_tracker.agent_kernel.storage",
        "sqlite3",
        "tests.agent_kernel.fact_adapters.database",
        "tests.agent_kernel.fixtures.oracles.database",
        "tests.agent_kernel.fixtures.oracles.reference",
    ]
    assert lane["forbidden_data_keys"] == [
        "answer_rows",
        "comparison_rows",
        "expected_rows",
        "grades",
        "grading",
        "oracle_case",
    ]
    assert lane["forbidden_overlap_roles"] == [
        "r1b_root",
        "r1b_transitive_import",
        "r1b_data_source",
    ]
    assert contract["grading_checks"] == {  # type: ignore[index]
        "lanes": ["production", "independent"],
        "sentinel_mutated": "baseline_answers_unchanged",
        "inaccessible": "baseline_answers_unchanged",
    }
    assert contract["mutation_checks"] == {  # type: ignore[index]
        "canonical_fact": "both_lanes_change",
        "production_source": "independent_truth_unchanged",
    }
