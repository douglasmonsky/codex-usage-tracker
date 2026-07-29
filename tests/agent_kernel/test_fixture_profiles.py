from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.agent_kernel.fixtures.generator.cases import question_case_records
from tests.agent_kernel.fixtures.generator.profile import (
    load_all_profiles,
    load_profile,
    planned_distribution,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_SCHEMA = (
    _REPO_ROOT
    / "config"
    / "agent-kernel"
    / "production-shape-profile-v1.schema.json"
)
_PRODUCTION_PROFILE = (
    Path(__file__).with_name("fixtures")
    / "profiles"
    / "production-shape-v1.json"
)
_CATALOG = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
)


def test_scale_profiles_are_exact_and_share_one_semantic_case_library() -> None:
    profiles = load_all_profiles()

    assert {profile.name: profile.model_calls for profile in profiles} == {
        "tiny": 100,
        "small": 10_000,
        "standard": 100_000,
        "production": 1_316_864,
        "growth": 2_500_000,
    }
    assert load_profile("production").source_manifestations == 643
    assert len({profile.semantic_cases for profile in profiles}) == 1
    assert len(profiles[0].semantic_cases) == 5


def test_standard_and_production_distributions_are_exact() -> None:
    standard = planned_distribution(load_profile("standard"))
    production = planned_distribution(load_profile("production"))

    assert standard == {
        "activities": 5_000,
        "allowance_observations": 100,
        "compaction_boundaries": 1_000,
        "duplicate_call_occurrences": 1_000,
        "late_events": 1_000,
        "missing_cached_input_calls": 5_000,
        "model_calls": 100_000,
        "sessions": 10_000,
        "state_changes": 5_000,
        "tool_invocations": 25_000,
        "turns": 50_000,
        "unpriced_calls": 10_000,
    }
    assert production == {
        "activities": 65_843,
        "allowance_observations": 1_316,
        "compaction_boundaries": 13_168,
        "duplicate_call_occurrences": 13_168,
        "late_events": 13_168,
        "missing_cached_input_calls": 65_843,
        "model_calls": 1_316_864,
        "sessions": 131_687,
        "state_changes": 65_843,
        "tool_invocations": 329_216,
        "turns": 658_432,
        "unpriced_calls": 131_686,
    }


def test_production_shape_profile_is_aggregate_only_and_schema_valid() -> None:
    schema = json.loads(_PROFILE_SCHEMA.read_text(encoding="utf-8"))
    profile = json.loads(_PRODUCTION_PROFILE.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(profile)) == []
    assert profile["source_shape"]["total_files"] == 643
    serialized = json.dumps(profile, sort_keys=True)
    for forbidden in (
        "absolute_path",
        "command_body",
        "event_id",
        "prompt",
        "reasoning_content",
        "response",
        "session_id",
        "tool_output_body",
    ):
        assert forbidden not in serialized


def test_every_question_oracle_reference_is_resolved() -> None:
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    records = question_case_records(load_profile("tiny"), catalog)
    expected = {
        oracle_id
        for question in catalog["questions"]
        for oracle_id in question["oracle_ids"]
    }

    assert {record["payload"]["oracle_id"] for record in records} == expected
    assert len(records) == 80
    named_ids = {
        question["question_id"]
        for question in catalog["questions"]
        if question["stage"] in {"Foundation", "Cutover"}
    }
    assert {record["payload"]["question_id"] for record in records} >= named_ids


def test_no_large_generated_fixture_is_committed() -> None:
    fixture_root = Path(__file__).with_name("fixtures")
    committed_files = [
        path for path in fixture_root.rglob("*") if path.is_file()
    ]

    assert committed_files
    assert max(path.stat().st_size for path in committed_files) < 1_000_000
    assert not any(
        scale in path.parts
        for path in committed_files
        for scale in ("small-v1", "standard-v1", "production-v1", "growth-v1")
    )
