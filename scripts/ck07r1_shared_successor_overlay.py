"""Fail-closed verifier for the versioned CK-07R1 shared-successor overlay."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.ck07r1_terminal_failure_correction import (
    CLEAN_COMMIT_CI_AUTHORITY_PATH,
    TerminalCorrectionError,
    bound_authority_digest_matches,
    load_clean_commit_ci_authority,
    verify_clean_commit_ci_authority_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json"
SCHEMA_PATH = AUTHORITY_PATH.removesuffix(".json") + ".schema.json"
CONSUMING_AUTHORITY_PATH = (
    "docs/decisions/evidence/ck07r1a0/"
    "lifecycle-consuming-boundary-authority-v1.json"
)
CONSUMING_SCHEMA_PATH = CONSUMING_AUTHORITY_PATH.removesuffix(".json") + ".schema.json"
PREPARATION_PATH = "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
MINIMUM_CAPACITY_BYTES = 10 * 1024**3


class SharedSuccessorOverlayError(RuntimeError):
    """The workspace is not an exact state admitted by the shared overlay."""


def sha256_path(root: Path, relative: str) -> str | None:
    """Return an exact file digest, or ``None`` when the path is absent."""

    path = root / relative
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_overlay(root: Path = ROOT) -> dict[str, Any]:
    """Load and schema-validate the exact versioned overlay."""

    authority_path = root / AUTHORITY_PATH
    schema_path = root / SCHEMA_PATH
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    return authority


def load_consuming_boundary(root: Path = ROOT) -> dict[str, Any] | None:
    """Load the complete additive consuming authority, or reject a partial pair."""

    authority_path = root / CONSUMING_AUTHORITY_PATH
    schema_path = root / CONSUMING_SCHEMA_PATH
    if not authority_path.exists() and not schema_path.exists():
        return None
    if not authority_path.is_file() or not schema_path.is_file():
        raise SharedSuccessorOverlayError(
            "partial CK-07R1 consuming-boundary authority"
        )
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    immutable = authority.get("immutable_authorities")
    if not isinstance(immutable, list):
        raise SharedSuccessorOverlayError("consuming-boundary bindings missing")
    for record in immutable:
        if not isinstance(record, Mapping):
            raise SharedSuccessorOverlayError(
                "consuming-boundary binding malformed"
            )
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SharedSuccessorOverlayError(
                "consuming-boundary identity malformed"
            )
            try:
                matches = bound_authority_digest_matches(root, relative, expected)
            except TerminalCorrectionError as exc:
                raise SharedSuccessorOverlayError(str(exc)) from exc
            if not matches:
                raise SharedSuccessorOverlayError(
                    f"consuming-boundary bound bytes drifted: {relative}"
                )
    return authority


def _consuming_authority_scope(
    consuming: Mapping[str, Any] | None,
) -> set[str]:
    if consuming is None:
        return set()
    scope = consuming.get("scope")
    if not isinstance(scope, Mapping):
        raise SharedSuccessorOverlayError("consuming-boundary scope missing")
    paths = scope.get("authority_write_scope")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise SharedSuccessorOverlayError("consuming-boundary scope malformed")
    return set(paths)


def _git_text(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SharedSuccessorOverlayError(
            f"cannot verify git {' '.join(arguments)}"
        ) from exc
    return result.stdout.strip()


def verify_current_exact_main(
    root: Path,
    *,
    observed_head: str | None = None,
    observed_tracking_main: str | None = None,
    observed_remote_main: str | None = None,
) -> str:
    """Require HEAD to equal both fetched and live origin/main."""

    head = observed_head or _git_text(root, "rev-parse", "HEAD")
    tracking = observed_tracking_main or _git_text(
        root, "rev-parse", "refs/remotes/origin/main"
    )
    if observed_remote_main is None:
        remote = _git_text(root, "ls-remote", "origin", "refs/heads/main")
        fields = remote.split()
        if len(fields) != 2 or fields[1] != "refs/heads/main":
            raise SharedSuccessorOverlayError("live origin/main response malformed")
        observed_remote_main = fields[0]
    if head != tracking or head != observed_remote_main:
        raise SharedSuccessorOverlayError(
            "consuming-boundary requires fresh exact origin/main"
        )
    return head


def verify_consuming_boundary_activation(
    overlay: Mapping[str, Any],
    consuming: Mapping[str, Any],
    root: Path,
    *,
    observed_head: str | None = None,
    observed_tracking_main: str | None = None,
    observed_remote_main: str | None = None,
    observed_capacity_bytes: int | None = None,
    observed_base_is_ancestor: bool | None = None,
) -> None:
    """Enforce repository/runtime gates without claiming worker authentication."""

    transition = consuming.get("transition")
    governance = consuming.get("governance")
    worker = consuming.get("worker")
    if (
        not isinstance(transition, Mapping)
        or not isinstance(governance, Mapping)
        or not isinstance(worker, Mapping)
    ):
        raise SharedSuccessorOverlayError("consuming-boundary activation malformed")
    if (
        transition.get("from") != "worker_prequalification"
        or transition.get("to") != "launch_authorized_once"
        or transition.get("launch_authorized") is not True
        or transition.get("candidate_head_transition")
        != "after_merge_fetch_then_non_destructive_fast_forward_only_from_prequalification_base_to_exact_merged_main_while_preserving_and_recomputing_the_exact_three_dirty_candidate_bytes"
        or transition.get("runtime_acceptance") != "not_claimed"
    ):
        raise SharedSuccessorOverlayError("consuming-boundary transition drifted")
    if (
        governance.get("worker_identity")
        != "normative_coordinator_orchestration_binding_to_exact_existing_thread_and_repository_evidence"
        or governance.get("runtime_attestation")
        != "not_required_not_claimed_and_no_cryptographic_per_task_credential_available"
        or worker.get("identity_enforcement")
        != "normative_coordinator_orchestration_binding_not_runtime_authentication"
        or worker.get("runtime_identity_claim") != "none"
    ):
        raise SharedSuccessorOverlayError(
            "consuming-boundary worker orchestration policy drifted"
        )
    if str(root.absolute()) != worker.get("frozen_cwd"):
        raise SharedSuccessorOverlayError("consuming-boundary frozen cwd drifted")
    head = verify_current_exact_main(
        root,
        observed_head=observed_head,
        observed_tracking_main=observed_tracking_main,
        observed_remote_main=observed_remote_main,
    )
    base = worker.get("prequalification_base_sha")
    if not isinstance(base, str) or len(base) != 40 or head == base:
        raise SharedSuccessorOverlayError(
            "consuming-boundary merged-main transition missing"
        )
    if observed_base_is_ancestor is None:
        observed_base_is_ancestor = (
            subprocess.run(
                ("git", "merge-base", "--is-ancestor", base, head),
                cwd=root,
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
    if not observed_base_is_ancestor:
        raise SharedSuccessorOverlayError(
            "consuming-boundary prequalification base is not an ancestor"
        )
    capacity = (
        shutil.disk_usage(root).free
        if observed_capacity_bytes is None
        else observed_capacity_bytes
    )
    if capacity < MINIMUM_CAPACITY_BYTES:
        raise SharedSuccessorOverlayError(
            "consuming-boundary capacity below 10 GiB"
        )
    states = overlay.get("states")
    candidate = consuming.get("candidate_cohort")
    if not isinstance(states, Mapping) or not isinstance(candidate, list):
        raise SharedSuccessorOverlayError("consuming-boundary candidate malformed")
    successor = states.get("successor")
    if not isinstance(successor, Mapping):
        raise SharedSuccessorOverlayError("overlay successor missing")
    overlay_identity = [
        {"path": record.get("path"), "sha256": record.get("sha256")}
        for record in successor.get("artifacts", [])
        if isinstance(record, Mapping)
    ]
    if candidate != overlay_identity:
        raise SharedSuccessorOverlayError(
            "consuming-boundary candidate does not match exact overlay successor"
        )


def verify_bound_authority_bytes(
    authority: Mapping[str, Any],
    root: Path = ROOT,
) -> None:
    """Verify every immutable and CK-07 authority byte bound by the overlay."""

    for section in ("immutable_authorities", "ck07_authorities"):
        records = authority.get(section)
        if not isinstance(records, list):
            raise SharedSuccessorOverlayError(f"{section} missing")
        for record in records:
            if not isinstance(record, Mapping):
                raise SharedSuccessorOverlayError(f"{section} record malformed")
            for path_key, digest_key in (
                ("path", "sha256"),
                ("schema_path", "schema_sha256"),
            ):
                relative = record.get(path_key)
                expected = record.get(digest_key)
                if not isinstance(relative, str) or not isinstance(expected, str):
                    raise SharedSuccessorOverlayError(f"{section} byte binding is malformed")
                if sha256_path(root, relative) != expected:
                    raise SharedSuccessorOverlayError(f"bound authority digest drift: {relative}")


def observed_candidate_artifacts(
    authority: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, str | None]:
    """Read exactly the three paths owned by the predecessor/successor fold."""

    states = authority.get("states")
    if not isinstance(states, Mapping):
        raise SharedSuccessorOverlayError("states missing")
    successor = states.get("successor")
    if not isinstance(successor, Mapping):
        raise SharedSuccessorOverlayError("successor state missing")
    artifacts = successor.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise SharedSuccessorOverlayError("successor state must contain exactly three artifacts")

    observed: dict[str, str | None] = {}
    for record in artifacts:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise SharedSuccessorOverlayError("successor artifact malformed")
        relative = str(record["path"])
        if relative in observed:
            raise SharedSuccessorOverlayError(f"duplicate successor path: {relative}")
        observed[relative] = sha256_path(root, relative)
    return observed


def _expected_state(state: Mapping[str, Any]) -> dict[str, str | None]:
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise SharedSuccessorOverlayError("authorized state must contain exactly three paths")

    expected: dict[str, str | None] = {}
    for record in artifacts:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise SharedSuccessorOverlayError("authorized artifact malformed")
        relative = str(record["path"])
        if relative in expected:
            raise SharedSuccessorOverlayError(f"duplicate authorized path: {relative}")
        presence = record.get("presence")
        if presence == "absent":
            expected[relative] = None
        elif presence == "required" and isinstance(record.get("sha256"), str):
            expected[relative] = str(record["sha256"])
        else:
            raise SharedSuccessorOverlayError(f"invalid presence contract for {relative}")
    return expected


def classify_observed_state(
    authority: Mapping[str, Any],
    observed: Mapping[str, str | None],
) -> str:
    """Fold exact path presence and digests into one authorized state."""

    states = authority.get("states")
    if not isinstance(states, Mapping):
        raise SharedSuccessorOverlayError("states missing")
    predecessor = states.get("predecessor")
    successor = states.get("successor")
    if not isinstance(predecessor, Mapping) or not isinstance(successor, Mapping):
        raise SharedSuccessorOverlayError("authorized states malformed")

    predecessor_expected = _expected_state(predecessor)
    successor_expected = _expected_state(successor)
    if set(observed) != set(successor_expected):
        raise SharedSuccessorOverlayError("candidate cohort paths missing or extra")
    if dict(observed) == predecessor_expected:
        return str(predecessor["name"])
    if dict(observed) == successor_expected:
        return str(successor["name"])
    raise SharedSuccessorOverlayError("mixed, partial, historical, or unbound CK-07R1 cohort")


def _git_paths(root: Path, *arguments: str) -> set[str]:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SharedSuccessorOverlayError(
            f"cannot verify exact Git delta: git {' '.join(arguments)}"
        ) from exc
    return {line for line in result.stdout.splitlines() if line}


def observed_worktree_delta(root: Path = ROOT) -> set[str]:
    """Return every tracked, staged, and untracked path relative to ``HEAD``."""

    unstaged = _git_paths(root, "diff", "--name-only", "--no-renames", "HEAD")
    staged = _git_paths(
        root,
        "diff",
        "--cached",
        "--name-only",
        "--no-renames",
        "HEAD",
    )
    untracked = _git_paths(root, "ls-files", "--others", "--exclude-standard")
    return unstaged | staged | untracked


def expected_worktree_delta(
    authority: Mapping[str, Any],
    state: str,
) -> set[str]:
    """Return the sole exact dirty set allowed for the classified state."""

    scope = authority.get("scope")
    if not isinstance(scope, Mapping):
        raise SharedSuccessorOverlayError("overlay scope missing")
    candidate_paths = scope.get("combined_preflight_candidate_scope")
    if not isinstance(candidate_paths, list) or not all(
        isinstance(path, str) for path in candidate_paths
    ):
        raise SharedSuccessorOverlayError("candidate scope malformed")
    if state == "authority_main":
        return set()
    if state == "worker_prequalification":
        return set(candidate_paths)
    raise SharedSuccessorOverlayError(f"unrecognized overlay state: {state}")


def verify_exact_worktree_delta(
    authority: Mapping[str, Any],
    state: str,
    root: Path = ROOT,
    *,
    observed: set[str] | None = None,
) -> None:
    """Reject any partial, extra, staged, or otherwise hidden Git delta."""

    actual = observed_worktree_delta(root) if observed is None else set(observed)
    expected = expected_worktree_delta(authority, state)
    consuming_scope = _consuming_authority_scope(load_consuming_boundary(root))
    additive_authority_preflight = (
        state == "authority_main" and bool(consuming_scope) and actual == consuming_scope
    )
    if actual != expected and not additive_authority_preflight:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SharedSuccessorOverlayError(
            f"exact Git delta mismatch; missing={missing!r}; extra={extra!r}"
        )


def verify_exact_committed_delta(
    authority: Mapping[str, Any],
    root: Path = ROOT,
    *,
    observed: set[str] | None = None,
    base_is_ancestor: bool | None = None,
) -> None:
    """Reject any committed path outside the exact versioned authority scope."""

    base = authority.get("authority_base_sha")
    scope = authority.get("scope")
    if not isinstance(base, str) or len(base) != 40:
        raise SharedSuccessorOverlayError("authority base SHA is malformed")
    if not isinstance(scope, Mapping):
        raise SharedSuccessorOverlayError("overlay scope missing")
    authority_paths = scope.get("authority_write_scope")
    if not isinstance(authority_paths, list) or not all(
        isinstance(path, str) for path in authority_paths
    ):
        raise SharedSuccessorOverlayError("authority write scope malformed")

    if base_is_ancestor is None:
        try:
            result = subprocess.run(
                ("git", "merge-base", "--is-ancestor", base, "HEAD"),
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise SharedSuccessorOverlayError(
                "cannot verify authority base ancestry"
            ) from exc
        base_is_ancestor = result.returncode == 0
    if not base_is_ancestor:
        raise SharedSuccessorOverlayError("authority base is not an ancestor of HEAD")

    actual = (
        _git_paths(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD")
        if observed is None
        else set(observed)
    )
    predecessor_expected = set(authority_paths)
    consuming_scope = _consuming_authority_scope(load_consuming_boundary(root))
    successor_expected = predecessor_expected | consuming_scope
    additive_authority_preflight = (
        actual == predecessor_expected
        and bool(consuming_scope)
        and observed_worktree_delta(root) == consuming_scope
    )
    if actual != successor_expected and not additive_authority_preflight:
        missing = sorted(successor_expected - actual)
        extra = sorted(actual - successor_expected)
        raise SharedSuccessorOverlayError(
            f"exact committed authority delta mismatch; missing={missing!r}; "
            f"extra={extra!r}"
        )


def verify_launcher_safety_contract(authority: Mapping[str, Any]) -> None:
    """Pin the corrected candidate's non-consuming launcher semantics."""

    expected = {
        "overlay_and_cohort_verification": (
            "must_complete_before_ledger_fork_child_release_or_token_consumption"
        ),
        "receipt_binding": (
            "must_equal_exact_overlay_verification_result_and_three_artifact_cohort"
        ),
        "receipt_completion_ordering": (
            "construct_exact_overlay_bound_receipt_then_validate_then_first_durable_"
            "completed_finalization"
        ),
        "receipt_failure_state": (
            "construction_validation_or_finalization_failure_is_failed_after_launch_"
            "never_completed"
        ),
        "child_pre_release_failure": (
            "every_pre_release_child_failure_routes_to_os._exit_71"
        ),
        "child_wait_signal_handling": (
            "SIGINT_SIGTERM_ignored_while_waiting_for_parent_release"
        ),
        "parent_cleanup_pid_guard": (
            "reject_pid_less_than_or_equal_to_zero_before_kill_wait_or_reap"
        ),
        "atomic_ledger_update": (
            "unique_same_directory_mkstemp_close_and_unlink_on_every_failed_or_"
            "interrupted_write_fsync_replace_or_post_replace_path"
        ),
        "atomic_failure_state": (
            "durable_failed_after_launch_token_consumed_no_retry_no_temp_residue"
        ),
        "parent_signal_handling": (
            "temporary_SIGINT_SIGTERM_handlers_installed_before_child_observation_"
            "held_through_bounded_reap_evidence_receipt_and_terminal_ledger_"
            "persistence_then_restored"
        ),
        "wait_interruption_cleanup": (
            "every_wait_exception_or_parent_signal_requires_bounded_SIGTERM_then_"
            "SIGKILL_then_reap_before_terminal_failure"
        ),
        "signal_cleanup_mask": (
            "SIGINT_SIGTERM_ignored_during_bounded_child_cleanup"
        ),
        "terminal_fallback_signal_mask": (
            "SIGINT_SIGTERM_ignored_during_every_terminal_fallback_persistence_"
            "then_prior_temporary_handlers_restored"
        ),
        "evidence_completion_ordering": (
            "required_non_null_stdout_stderr_output_read_hash_parse_validate_before_"
            "first_durable_completed_finalization"
        ),
        "evidence_failure_state": (
            "missing_read_hash_parse_validation_or_finalization_failure_is_failed_"
            "after_launch_never_completed"
        ),
        "interpreter_identity": {
            "executable": "lexical_repository_worktree_.venv/bin/python_required",
            "sys_prefix": "lexical_repository_worktree_.venv_required",
            "base_interpreter": "rejected",
            "symlink_or_resolved_equivalence": "rejected",
            "wrong_worktree_venv": "rejected",
            "prefix_mismatch": "rejected",
        },
        "post_token_or_release_failure_state": "failed_after_launch",
        "aggregate_timeout_seconds": 720,
        "termination_sequence": ["SIGTERM", "wait_up_to_5_seconds", "SIGKILL"],
        "final_reap_timeout_seconds": 5,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }
    if authority.get("launcher_safety") != expected:
        raise SharedSuccessorOverlayError("launcher safety contract drifted")


def verify_shared_successor_overlay(
    root: Path = ROOT,
) -> tuple[dict[str, Any], str]:
    """Validate authority bytes, atomic cohort, exact Git delta, and launcher gate."""

    authority = load_overlay(root)
    verify_bound_authority_bytes(authority, root)
    verify_launcher_safety_contract(authority)
    verify_exact_committed_delta(authority, root)
    state = classify_observed_state(
        authority,
        observed_candidate_artifacts(authority, root),
    )
    verify_exact_worktree_delta(authority, state, root)
    consuming = load_consuming_boundary(root)
    if state == "worker_prequalification":
        if consuming is None:
            raise SharedSuccessorOverlayError(
                "consuming-boundary authority unavailable"
            )
        verify_consuming_boundary_activation(authority, consuming, root)
    return authority, state


def overlay_changed_path_allowance(
    authority: Mapping[str, Any],
    state: str,
    root: Path = ROOT,
) -> set[str]:
    """Return exact base-to-HEAD paths admitted for an authority/preflight lane."""

    scope = authority.get("scope")
    if not isinstance(scope, Mapping):
        raise SharedSuccessorOverlayError("overlay scope missing")
    authority_paths = scope.get("authority_write_scope")
    if not isinstance(authority_paths, list) or not all(
        isinstance(path, str) for path in authority_paths
    ):
        raise SharedSuccessorOverlayError("authority write scope malformed")

    allowed = set(authority_paths)
    allowed.update(_consuming_authority_scope(load_consuming_boundary(root)))
    clean_commit_ci_path = root / CLEAN_COMMIT_CI_AUTHORITY_PATH
    if clean_commit_ci_path.is_file():
        try:
            clean_commit_ci = load_clean_commit_ci_authority(root)
            verify_clean_commit_ci_authority_bytes(clean_commit_ci, root)
        except TerminalCorrectionError as exc:
            raise SharedSuccessorOverlayError(str(exc)) from exc
        allowed.update(clean_commit_ci["scope"]["authority_write_scope"])
    if state == "worker_prequalification":
        allowed.update(expected_worktree_delta(authority, state))
    elif state != "authority_main":
        raise SharedSuccessorOverlayError(f"unrecognized overlay state: {state}")
    return allowed
