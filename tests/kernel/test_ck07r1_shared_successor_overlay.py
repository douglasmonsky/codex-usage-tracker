from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import scripts.ck07r1_shared_successor_overlay as overlay_module
from scripts.ck07r1_prelaunch_recovery import (
    AUTHORITY_PATH as RECOVERY_AUTHORITY_PATH,
)
from scripts.ck07r1_prelaunch_recovery import (
    verify_combined_preflight,
)
from scripts.ck07r1_shared_successor_overlay import (
    CONSUMING_AUTHORITY_PATH,
    ROOT,
    SCHEMA_PATH,
    SharedSuccessorOverlayError,
    classify_observed_state,
    expected_worktree_delta,
    load_consuming_boundary,
    load_overlay,
    observed_candidate_artifacts,
    overlay_changed_path_allowance,
    sha256_path,
    verify_bound_authority_bytes,
    verify_consuming_boundary_activation,
    verify_current_exact_main,
    verify_exact_committed_delta,
    verify_exact_worktree_delta,
    verify_launcher_safety_contract,
    verify_shared_successor_overlay,
)
from scripts.ck07r1_terminal_failure_correction import (
    AUTHORITY_PATH as TERMINAL_AUTHORITY_PATH,
)
from scripts.ck07r1_terminal_failure_correction import (
    load_authority as load_terminal_authority,
)
from scripts.ck07r1_terminal_failure_correction import (
    verify_combined as verify_terminal_combined,
)
from scripts.ck07r1_terminal_failure_correction import (
    verify_exact_authority_delta as verify_terminal_authority_delta,
)
from scripts.ck07r1_terminal_failure_correction import (
    verify_immutable_authority_bytes as verify_terminal_authority_bytes,
)


def _state_observed(
    authority: dict,
    state_name: str,
) -> dict[str, str | None]:
    state = authority["states"][state_name]
    return {
        item["path"]: None if item["presence"] == "absent" else item["sha256"]
        for item in state["artifacts"]
    }


def test_overlay_is_exact_and_live_state_is_authorized() -> None:
    try:
        authority, state = verify_shared_successor_overlay()
    except SharedSuccessorOverlayError:
        if (ROOT / TERMINAL_AUTHORITY_PATH).is_file():
            terminal_authority = load_terminal_authority(ROOT)
            corrected_preparation = terminal_authority["corrected_candidate_cohort"][0]
            if sha256_path(ROOT, corrected_preparation["path"]) == corrected_preparation["sha256"]:
                terminal = verify_terminal_combined(terminal_authority, ROOT)
                assert terminal == {
                    "candidate_paths": 7,
                    "new_run_permitted": False,
                    "runtime_acceptance": "not_claimed",
                    "token_consumed": True,
                }
            else:
                verify_terminal_authority_bytes(terminal_authority, ROOT)
                verify_terminal_authority_delta(terminal_authority, ROOT)
                overlay = load_overlay(ROOT)
                assert (
                    sha256_path(ROOT, corrected_preparation["path"])
                    == (overlay["states"]["predecessor"]["artifacts"][0]["sha256"])
                )
            return
        if not (ROOT / RECOVERY_AUTHORITY_PATH).is_file():
            raise
        recovery_ledger = ROOT / "output/ck07r1/lifecycle-requalification-v1.launch-token.json"
        if recovery_ledger.is_file():
            recovery = verify_combined_preflight(ROOT, ROOT)
            assert recovery["recovery_transition"]["old_shared_overlay"] == (
                "immutable_historical_predecessor_evidence"
            )
            assert recovery["recovery_transition"]["live_corrected_cohort_authority"] == (
                "this_versioned_recovery_authority_only"
            )
            assert recovery["status"] == "permitted_not_accepted"
            assert recovery["decision"]["runtime_acceptance"] == "not_claimed"
            assert recovery["decision"]["launch_authorized_in_authority_task"] is False
            return
        authority = load_overlay()
        state = classify_observed_state(authority, observed_candidate_artifacts(authority))

    assert state in {"authority_main", "worker_prequalification"}
    assert authority["status"] == "permitted_not_accepted"
    assert authority["states"]["successor"]["status"] == "permitted_not_accepted"
    assert authority["states"]["successor"]["launch_authorized"] is False
    assert authority["non_consuming_invariants"] == {
        "maximum_new_end_to_end_runs": 1,
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "matching_processes": [],
        "successful_child": "absent",
        "pid": "absent",
        "handshake": "absent",
        "runtime_acceptance": "not_claimed",
        "receipt": "absent_non_qualifying",
        "output": "absent",
        "ledger": "absent",
        "stdout": "absent",
        "stderr": "absent",
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "pr394": "stale_read_only",
        "downstream": "CK-08R4_CK-08RG_CK-09_blocked",
        "data_policy": "synthetic_only",
    }
    state_key = "predecessor" if state == "authority_main" else "successor"
    assert observed_candidate_artifacts(authority) == _state_observed(authority, state_key)


def test_complete_consuming_boundary_is_the_only_additive_authority_delta() -> None:
    overlay = load_overlay()
    consuming = load_consuming_boundary()
    assert consuming is not None
    scope = set(consuming["scope"]["authority_write_scope"])
    predecessor_scope = set(overlay["scope"]["authority_write_scope"])

    verify_exact_worktree_delta(overlay, "authority_main", observed=scope)
    verify_exact_committed_delta(
        overlay,
        observed=predecessor_scope | scope,
        base_is_ancestor=True,
    )
    for changed in (
        scope - {next(iter(scope))},
        scope | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
    ):
        with pytest.raises(SharedSuccessorOverlayError, match="Git delta mismatch"):
            verify_exact_worktree_delta(overlay, "authority_main", observed=changed)


def test_partial_consuming_boundary_pair_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / CONSUMING_AUTHORITY_PATH
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SharedSuccessorOverlayError, match="partial"):
        load_consuming_boundary(tmp_path)


def test_consuming_activation_requires_exact_main_cwd_capacity_and_cohort() -> None:
    overlay = load_overlay()
    consuming = load_consuming_boundary()
    assert consuming is not None
    frozen_root = Path(consuming["worker"]["frozen_cwd"])
    exact_main = "a" * 40

    verify_consuming_boundary_activation(
        overlay,
        consuming,
        frozen_root,
        observed_head=exact_main,
        observed_tracking_main=exact_main,
        observed_remote_main=exact_main,
        observed_capacity_bytes=10 * 1024**3,
        observed_base_is_ancestor=True,
    )
    with pytest.raises(SharedSuccessorOverlayError, match="fresh exact"):
        verify_current_exact_main(
            frozen_root,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main="b" * 40,
        )
    with pytest.raises(SharedSuccessorOverlayError, match="frozen cwd"):
        verify_consuming_boundary_activation(
            overlay,
            consuming,
            Path("/wrong/worktree"),
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main=exact_main,
            observed_capacity_bytes=10 * 1024**3,
            observed_base_is_ancestor=True,
        )
    with pytest.raises(SharedSuccessorOverlayError, match="capacity"):
        verify_consuming_boundary_activation(
            overlay,
            consuming,
            frozen_root,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main=exact_main,
            observed_capacity_bytes=10 * 1024**3 - 1,
            observed_base_is_ancestor=True,
        )
    with pytest.raises(SharedSuccessorOverlayError, match="not an ancestor"):
        verify_consuming_boundary_activation(
            overlay,
            consuming,
            frozen_root,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main=exact_main,
            observed_capacity_bytes=10 * 1024**3,
            observed_base_is_ancestor=False,
        )
    changed = deepcopy(consuming)
    changed["worker"]["runtime_identity_claim"] = "self_asserted"
    with pytest.raises(SharedSuccessorOverlayError, match="orchestration policy"):
        verify_consuming_boundary_activation(
            overlay,
            changed,
            frozen_root,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main=exact_main,
            observed_capacity_bytes=10 * 1024**3,
            observed_base_is_ancestor=True,
        )


def test_worker_state_reaches_consuming_activation_before_verifier_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = load_overlay()
    consuming = load_consuming_boundary()
    assert consuming is not None
    calls: list[str] = []
    monkeypatch.setattr(overlay_module, "load_overlay", lambda root: overlay)
    monkeypatch.setattr(overlay_module, "verify_bound_authority_bytes", lambda *_: None)
    monkeypatch.setattr(overlay_module, "verify_launcher_safety_contract", lambda *_: None)
    monkeypatch.setattr(overlay_module, "verify_exact_committed_delta", lambda *_: None)
    monkeypatch.setattr(overlay_module, "observed_candidate_artifacts", lambda *_: {})
    monkeypatch.setattr(
        overlay_module,
        "classify_observed_state",
        lambda *_: "worker_prequalification",
    )
    monkeypatch.setattr(overlay_module, "verify_exact_worktree_delta", lambda *_: None)
    monkeypatch.setattr(overlay_module, "load_consuming_boundary", lambda *_: consuming)
    monkeypatch.setattr(
        overlay_module,
        "verify_consuming_boundary_activation",
        lambda *_: calls.append("consuming_activation"),
    )

    _, state = overlay_module.verify_shared_successor_overlay(Path("/synthetic"))
    assert state == "worker_prequalification"
    assert calls == ["consuming_activation"]


def test_frozen_launcher_imports_verifier_before_any_side_effect() -> None:
    consuming = load_consuming_boundary()
    assert consuming is not None
    launcher_path = (
        Path(consuming["worker"]["frozen_cwd"]) / "scripts/benchmark_ck07r1_lifecycle_scale.py"
    )
    if not launcher_path.is_file():
        pytest.skip("retained frozen candidate witness is unavailable")
    launcher = launcher_path.read_text(encoding="utf-8")
    launch = launcher[launcher.index("def _launch_exact()") : launcher.index("\ndef main()")]
    assert "verifier.verify_prelaunch_recovery(root)" in launcher
    assert "_verify_historical_shared_overlay_binding" in launcher
    assert "_verify_overlay_cohort()" not in launch
    assert launch.index("_verify_prelaunch_recovery()") < launch.index("os.pipe()")
    assert launch.index("_verify_prelaunch_recovery()") < launch.index("os.fork()")


def test_overlay_admits_only_the_complete_exact_successor() -> None:
    authority = load_overlay()
    predecessor = _state_observed(authority, "predecessor")
    successor = _state_observed(authority, "successor")

    assert classify_observed_state(authority, predecessor) == "authority_main"
    assert classify_observed_state(authority, successor) == "worker_prequalification"

    for path in successor:
        partial = dict(successor)
        partial[path] = predecessor[path]
        with pytest.raises(SharedSuccessorOverlayError, match="mixed, partial"):
            classify_observed_state(authority, partial)

    other = dict(successor)
    other[next(iter(other))] = "0" * 64
    with pytest.raises(SharedSuccessorOverlayError, match="unbound"):
        classify_observed_state(authority, other)

    missing = dict(successor)
    missing.pop(next(iter(missing)))
    with pytest.raises(SharedSuccessorOverlayError, match="missing or extra"):
        classify_observed_state(authority, missing)

    extra = dict(successor)
    extra["unexpected.py"] = "0" * 64
    with pytest.raises(SharedSuccessorOverlayError, match="missing or extra"):
        classify_observed_state(authority, extra)


def test_overlay_schema_rejects_status_token_launch_scope_and_safety_weakening() -> None:
    authority = load_overlay()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    mutations = [
        lambda value: value.__setitem__("status", "final_accepted"),
        lambda value: value["states"]["successor"].__setitem__("launch_authorized", True),
        lambda value: value["non_consuming_invariants"].__setitem__("token_consumed", True),
        lambda value: value["non_consuming_invariants"].__setitem__("receipt", "fabricated"),
        lambda value: value["states"]["successor"]["artifacts"].pop(),
        lambda value: value["states"]["successor"]["artifacts"].append(
            {"path": "extra.py", "sha256": "0" * 64, "presence": "required"}
        ),
        lambda value: value["scope"]["authority_write_scope"].append(
            "src/codex_usage_tracker/agent_kernel/publication/writer.py"
        ),
        lambda value: value["scope"]["combined_preflight_candidate_scope"].pop(),
        lambda value: value["launcher_safety"].__setitem__(
            "overlay_and_cohort_verification", "after_ledger"
        ),
        lambda value: value["launcher_safety"].__setitem__("receipt_binding", "optional"),
        lambda value: value["launcher_safety"].__setitem__(
            "receipt_completion_ordering", "durable_completed_before_validation"
        ),
        lambda value: value["launcher_safety"].__setitem__("receipt_failure_state", "completed"),
        lambda value: value["launcher_safety"].__setitem__(
            "child_pre_release_failure", "exception_returns_to_parent_path"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "child_wait_signal_handling", "signals_actionable_while_waiting"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "parent_cleanup_pid_guard", "pid_zero_allowed"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "atomic_ledger_update", "fixed_temp_without_cleanup"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "atomic_failure_state", "retry_or_temp_residue_allowed"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "parent_signal_handling", "not_installed"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "parent_signal_handling", "restored_after_wait"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "wait_interruption_cleanup", "persist_without_reap"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "signal_cleanup_mask", "signals_remain_actionable"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "terminal_fallback_signal_mask", "signals_remain_actionable"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "evidence_completion_ordering", "nullable_hashes_allowed"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "evidence_failure_state", "launched_consumed"
        ),
        lambda value: value["launcher_safety"]["interpreter_identity"].__setitem__(
            "executable", "resolved_equivalent_python_allowed"
        ),
        lambda value: value["launcher_safety"]["interpreter_identity"].__setitem__(
            "sys_prefix", "optional"
        ),
        lambda value: value["launcher_safety"].__setitem__(
            "post_token_or_release_failure_state", "prelaunch_failed"
        ),
        lambda value: value["launcher_safety"].__setitem__("final_reap_timeout_seconds", 0),
    ]
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(validator.iter_errors(changed))


def test_overlay_rejects_any_immutable_v1_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = load_overlay()
    original = sha256_path
    first = authority["immutable_authorities"][0]["path"]

    def changed_digest(root: Path, relative: str) -> str | None:
        if relative == first:
            return "0" * 64
        return original(root, relative)

    monkeypatch.setattr(
        "scripts.ck07r1_shared_successor_overlay.sha256_path",
        changed_digest,
    )
    with pytest.raises(SharedSuccessorOverlayError, match="digest drift"):
        verify_bound_authority_bytes(authority)


def test_overlay_requires_exact_all_or_none_git_delta() -> None:
    authority = load_overlay()
    candidate = set(authority["scope"]["combined_preflight_candidate_scope"])

    assert expected_worktree_delta(authority, "authority_main") == set()
    assert expected_worktree_delta(authority, "worker_prequalification") == candidate
    verify_exact_worktree_delta(authority, "authority_main", observed=set())
    verify_exact_worktree_delta(
        authority,
        "worker_prequalification",
        observed=candidate,
    )

    with pytest.raises(SharedSuccessorOverlayError, match="missing="):
        verify_exact_worktree_delta(
            authority,
            "worker_prequalification",
            observed=candidate - {next(iter(candidate))},
        )
    with pytest.raises(SharedSuccessorOverlayError, match="extra="):
        verify_exact_worktree_delta(
            authority,
            "worker_prequalification",
            observed=candidate | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
        )
    with pytest.raises(SharedSuccessorOverlayError, match="extra="):
        verify_exact_worktree_delta(
            authority,
            "worker_prequalification",
            observed=candidate
            | {"docs/decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json"},
        )


def test_overlay_requires_exact_committed_authority_delta() -> None:
    authority = load_overlay()
    consuming = load_consuming_boundary()
    assert consuming is not None
    expected = set(authority["scope"]["authority_write_scope"]) | set(
        consuming["scope"]["authority_write_scope"]
    )

    verify_exact_committed_delta(
        authority,
        observed=expected,
        base_is_ancestor=True,
    )
    with pytest.raises(SharedSuccessorOverlayError, match="not an ancestor"):
        verify_exact_committed_delta(
            authority,
            observed=expected,
            base_is_ancestor=False,
        )
    with pytest.raises(SharedSuccessorOverlayError, match="missing="):
        verify_exact_committed_delta(
            authority,
            observed=expected - {next(iter(expected))},
            base_is_ancestor=True,
        )
    with pytest.raises(SharedSuccessorOverlayError, match="extra="):
        verify_exact_committed_delta(
            authority,
            observed=expected | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
            base_is_ancestor=True,
        )


def test_overlay_scope_and_launcher_contract_are_exact() -> None:
    authority = load_overlay()
    predecessor = overlay_changed_path_allowance(authority, "authority_main")
    successor = overlay_changed_path_allowance(authority, "worker_prequalification")
    candidate = set(authority["scope"]["combined_preflight_candidate_scope"])

    assert successor == predecessor | candidate
    assert candidate.isdisjoint(predecessor)
    assert "src/codex_usage_tracker/agent_kernel/publication/writer.py" not in successor
    verify_launcher_safety_contract(authority)

    weakened = deepcopy(authority)
    weakened["launcher_safety"]["termination_sequence"] = ["SIGTERM"]
    with pytest.raises(SharedSuccessorOverlayError, match="safety"):
        verify_launcher_safety_contract(weakened)

    weakened = deepcopy(authority)
    weakened["launcher_safety"]["interpreter_identity"]["symlink_or_resolved_equivalence"] = (
        "accepted"
    )
    with pytest.raises(SharedSuccessorOverlayError, match="safety"):
        verify_launcher_safety_contract(weakened)
