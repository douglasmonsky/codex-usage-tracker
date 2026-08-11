"""Fail-closed verifier for the versioned CK-07R1 shared-successor overlay."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json"
SCHEMA_PATH = AUTHORITY_PATH.removesuffix(".json") + ".schema.json"
PREPARATION_PATH = "src/codex_usage_tracker/agent_kernel/publication/preparation.py"


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
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SharedSuccessorOverlayError(
            f"exact Git delta mismatch; missing={missing!r}; extra={extra!r}"
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
    state = classify_observed_state(
        authority,
        observed_candidate_artifacts(authority, root),
    )
    verify_exact_worktree_delta(authority, state, root)
    return authority, state


def overlay_changed_path_allowance(
    authority: Mapping[str, Any],
    state: str,
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
    if state == "worker_prequalification":
        allowed.update(expected_worktree_delta(authority, state))
    elif state != "authority_main":
        raise SharedSuccessorOverlayError(f"unrecognized overlay state: {state}")
    return allowed
