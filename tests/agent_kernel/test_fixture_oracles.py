from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.agent_kernel.fixtures.generator.generate import generate_fixture
from tests.agent_kernel.fixtures.generator.profile import load_profile
from tests.agent_kernel.fixtures.oracles.bundle import (
    build_oracle_bundle,
    oracle_bundle_failures,
)
from tests.agent_kernel.fixtures.oracles.evidence import paginate_total_order
from tests.agent_kernel.fixtures.oracles.source_ledger import read_source_ledger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
)
_COMMITTED_ROOT = Path(__file__).with_name("fixtures") / "tiny-v1"


def _bundle(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = tmp_path / "fixture"
    profile = load_profile("tiny")
    generate_fixture(profile, root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    ledger = read_source_ledger(root, manifest)
    return build_oracle_bundle(profile, catalog, ledger=ledger), catalog


def test_tiny_oracle_is_hand_auditable_and_covers_all_five_slices(
    tmp_path: Path,
) -> None:
    bundle, catalog = _bundle(tmp_path)
    assert oracle_bundle_failures(bundle, catalog) == []
    assert bundle["vertical_slices"] == {
        "V1": "context_deterioration",
        "V2": "workflow_sequence_first_mutation",
        "V3": "allowance_interval_accounting",
        "V4": "parent_subagent_aggregation",
        "V5": "evidence_source_lifecycle",
    }
    accounting = bundle["accounting"]
    assert accounting["canonical_counts"]["model_calls"] == 100
    assert accounting["canonical_counts"]["sessions"] == 10
    assert accounting["canonical_counts"]["turns"] == 50
    assert accounting["source_reconciliation"] == {
        "canonical_model_calls": 100,
        "model_call_occurrences": 102,
        "source_manifestations": 12,
    }
    assert accounting["measurement_coverage"]["cached_input_tokens"] == {
        "complete": False,
        "missing_count": 5,
        "observed_count": 95,
    }


def test_lifecycle_oracle_is_arrival_order_independent_and_noncausal(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path)
    lifecycle = bundle["lifecycle"]
    assert lifecycle["late_terminal"]["same_fold_as_in_order"] is True
    assert lifecycle["crash_restart"]["same_fold_as_uninterrupted"] is True
    assert lifecycle["turn_completion"]["open_tail"] == "open"
    assert lifecycle["tool_separation"] == {
        "causal_attribution": False,
        "observed_mutation": True,
        "preceding_tool_count": 2,
        "tool_state": "succeeded",
        "write_intent": True,
    }


def test_evidence_pages_have_no_gaps_and_use_real_coordinates(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path)
    evidence = bundle["evidence"]
    rows = evidence["equal_time_rows"]
    pages = paginate_total_order(rows, page_size=3)
    flattened = [row["logical_id"] for page in pages for row in page["rows"]]
    assert flattened == [row["logical_id"] for row in rows]
    assert len(flattened) == len(set(flattened))
    assert all(page["cursor"] is not None for page in pages[:-1])
    assert pages[-1]["cursor"] is None
    assert evidence["selector_rebuild"]["before"] == evidence["selector_rebuild"][
        "after"
    ]
    assert all(row["occurrence_coordinate"]["byte_end"] > 0 for row in rows)


def test_source_lifecycle_and_crash_matrix_preserve_prior_publication(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(tmp_path)
    source = bundle["source_lifecycle"]
    crash = bundle["crash_states"]
    assert source["manifestation_counts"] == {
        "active": 7,
        "archived": 1,
        "deferred": 1,
        "malformed": 1,
        "replaced": 1,
        "truncated": 1,
    }
    assert source["canonical_model_calls"] == 100
    assert source["duplicate_occurrences_excluded"] == 2
    assert len(crash) == 9
    assert all(case["prior_publication_queryable"] for case in crash)
    assert all(
        case["candidate_publication_committed"] is False
        for case in crash[:-2]
    )


def test_question_oracles_are_closed_exact_and_claim_safe(
    tmp_path: Path,
) -> None:
    bundle, catalog = _bundle(tmp_path)
    records = bundle["questions"]
    by_question = {
        question["question_id"]: question
        for question in catalog["questions"]
    }
    assert len(records) == 80
    for oracle_id, record in records.items():
        question = by_question[record["question_id"]]
        assert record["oracle_id"] == oracle_id
        assert record["request"]["plan_id"] == question["plan_id"]
        assert record["expected"]["field_grades"] == question["answers"]["fields"]
        assert set(record["expected"]["row"]) == set(question["answers"]["fields"])
        assert record["expected"]["order"] == question["order"]
        assert record["required_selectors"] == question["evidence"]["selector_kinds"]
        assert record["prohibited_claims"] == question["prohibited_claims"]
        assert record["limits"] == question["limits"]
        assert record["source_case"]["coordinate"]["revision"]


def test_committed_oracle_matches_current_source_projection() -> None:
    profile = load_profile("tiny")
    manifest = json.loads(
        (_COMMITTED_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    ledger = read_source_ledger(_COMMITTED_ROOT, manifest)
    expected = build_oracle_bundle(profile, catalog, ledger=ledger)
    committed = json.loads(
        (_COMMITTED_ROOT / "oracle-bundle.json").read_text(encoding="utf-8")
    )
    assert committed == expected
