from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
publication_module = importlib.import_module("candidate_a.publication")

CandidateACrashDriver = publication_module.CandidateACrashDriver
database = importlib.import_module("candidate_a.schema").database

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_FAULT_MECHANISMS = {
    "disk_full": "enospc_projection_write",
    "disk_full_before_transaction": "enospc_before_transaction",
    "disk_full_during_transaction": "enospc_fact_transaction",
    "malformed_source": "json_decode_failure",
    "disappearing_source": "source_unlinked_before_read",
    "busy_reader": "reader_shared_lock_blocks_promotion_lease",
    "stale_writer_lease": "dead_pid_writer_lease",
    "stale_lease_pid_reuse": "live_pid_start_token_mismatch",
    "corrupt_staging_artifact": "sqlite_header_corruption",
    "sidecar_corruption": "invalid_sidecar_json",
    "analytical_candidate_corruption": "analytical_metadata_corruption",
    "pointer_mismatch": "active_pointer_identity_digest_mismatch",
    "schema_projection_incompatibility": "projection_table_removed",
    "invalid_rate_card": "rate_card_validation_failure",
    "read_process_open_during_promotion": ("separate_reader_snapshot_spans_atomic_promotion"),
    "simultaneous_startup_recovery": "two_process_startup_recovery_barrier",
}


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


def _record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return {str(key): item for key, item in value.items()}


def _case_root(root: Path, case: Any) -> Path:
    return root / case.case_id.replace(".", "-")


def _assert_subsequent_publication(case_root: Path) -> None:
    subsequent = _record(case_root / "subsequent-publication.json")
    pointer = _record(case_root / "active-publication.json")
    sidecar = _record(case_root / "publication-state.json")
    assert subsequent["succeeded"] is True
    assert sidecar["state"] == "succeeded"
    assert pointer["publication_id"] == subsequent["active"]["publication_id"]
    assert pointer["artifact_sha256"] == subsequent["active"]["artifact_sha256"]
    with database(case_root / "publication.sqlite", read_only=True) as connection:
        active_id = str(
            connection.execute(
                "SELECT publication_id FROM publications WHERE status='committed'"
            ).fetchone()[0]
        )
    assert active_id == pointer["publication_id"]


@pytest.mark.parametrize("boundary", shared.CRASH_BOUNDARIES)
def test_crash_boundaries_are_recovered_from_observed_state(
    fixture: Any,
    tmp_path: Path,
    boundary: str,
) -> None:
    case = shared.CrashCase.termination(boundary)
    observation = CandidateACrashDriver(
        fixture,
        tmp_path,
        timeout_seconds=20,
    ).run_crash_case(case)
    shared.validate_crash_observation(
        case,
        fixture.crash_expectation(boundary),
        observation,
    )

    case_root = _case_root(tmp_path, case)
    terminal = _record(case_root / "recovery-terminal-state.json")
    assert observation.prior_publication_queryable is terminal["prior_publication_queryable"]
    assert observation.rollback_available is terminal["rollback_available"]
    assert (
        observation.candidate_publication_committed is terminal["candidate_publication_committed"]
    )
    assert observation.sidecar_terminal_state == terminal["sidecar_terminal_state"]
    assert observation.abandoned_artifact_disposition == terminal["disposition"]
    assert not (case_root / "candidate.sqlite").exists()
    assert (case_root / "rollback.sqlite").is_file()
    if boundary == "after_validation_before_promotion":
        assert (case_root / "retained-candidate.sqlite").is_file()
    _assert_subsequent_publication(case_root)


@pytest.mark.parametrize("fault", shared.CRASH_FAULTS)
def test_every_fault_has_a_specific_mechanism_and_real_republication(
    fixture: Any,
    tmp_path: Path,
    fault: str,
) -> None:
    case = shared.CrashCase.injected_fault(fault)
    observation = CandidateACrashDriver(
        fixture,
        tmp_path,
        timeout_seconds=20,
    ).run_crash_case(case)
    shared.validate_crash_observation(case, {}, observation)

    case_root = _case_root(tmp_path, case)
    fault_record = _record(case_root / "fault-observation.json")
    terminal = _record(case_root / "recovery-terminal-state.json")
    assert fault_record["fault"] == fault
    assert fault_record["mechanism"] == _FAULT_MECHANISMS[fault]
    assert fault_record["stage"] == publication_module._fault_boundary(fault)
    assert terminal["prior_publication_queryable"] is True
    assert terminal["rollback_available"] is True
    assert (
        observation.candidate_publication_committed is terminal["candidate_publication_committed"]
    )
    assert observation.sidecar_terminal_state == terminal["sidecar_terminal_state"]
    assert observation.abandoned_artifact_disposition == terminal["disposition"]
    if fault == "read_process_open_during_promotion":
        reader = fault_record["observed"]["reader_result"]
        assert reader["same_snapshot"] is True
        assert reader["before_publication_id"] == reader["after_publication_id"]
    if fault == "busy_reader":
        assert fault_record["observed"]["reader_process_alive"] is True
        assert fault_record["reader_result"]["same_snapshot"] is True
    if fault == "pointer_mismatch":
        assert terminal["recovery_action"] == "rolled_back_to_valid_pair"
        assert terminal["disposition"] == "reconcile_pointer_or_rollback"
    if fault == "sidecar_corruption":
        assert terminal["sidecar_status_before"].startswith("invalid:")
    if fault == "stale_writer_lease":
        assert terminal["lease"]["pid_alive"] is False
    if fault == "stale_lease_pid_reuse":
        assert terminal["lease"]["pid_alive"] is True
        assert terminal["lease"]["token_matches"] is False
    if fault in {
        "analytical_candidate_corruption",
        "corrupt_staging_artifact",
        "schema_projection_incompatibility",
    }:
        assert terminal["staging_before"]["exists"] is True
        assert terminal["staging_before"]["valid"] is False
    if fault == "simultaneous_startup_recovery":
        assert (case_root / "simultaneous-recovery-0.json").is_file()
        assert (case_root / "simultaneous-recovery-1.json").is_file()
        assert (case_root / "recovery-observation-startup-0.json").is_file()
        assert (case_root / "recovery-observation-startup-1.json").is_file()
    _assert_subsequent_publication(case_root)


def test_publication_forwards_parser_workers_without_changing_default(
    fixture: Any,
    tmp_path: Path,
) -> None:
    artifact = publication_module.publish_artifact(
        fixture,
        tmp_path,
        parser_workers=2,
    )

    assert artifact.stats.parser_workers == 2
    pointer = _record(tmp_path / "active-publication.json")
    assert pointer["publication_id"] == artifact.publication_id
