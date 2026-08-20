#!/usr/bin/env python3
"""Verify the non-consuming CK-07R1 terminal-failure correction boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

AUTHORITY_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-terminal-failure-correction-authority-v1.json"
)
SCHEMA_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/"
    "lifecycle-terminal-failure-correction-authority-v1.schema.json"
)
CLEAN_COMMIT_AUTHORITY_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/"
    "lifecycle-terminal-failure-clean-commit-authority-v1.json"
)
CLEAN_COMMIT_SCHEMA_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/"
    "lifecycle-terminal-failure-clean-commit-authority-v1.schema.json"
)


class TerminalCorrectionError(RuntimeError):
    """The exact terminal correction contract is not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalCorrectionError(f"cannot load exact JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TerminalCorrectionError(f"exact JSON is not an object: {path}")
    return value


def load_authority(root: Path) -> dict[str, Any]:
    authority = _load_json(root / AUTHORITY_PATH)
    schema = _load_json(root / SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(authority)
    except Exception as exc:
        raise TerminalCorrectionError(
            f"terminal correction authority/schema validation failed: {exc}"
        ) from exc
    return authority


def load_clean_commit_authority(root: Path) -> dict[str, Any]:
    authority = _load_json(root / CLEAN_COMMIT_AUTHORITY_PATH)
    schema = _load_json(root / CLEAN_COMMIT_SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(authority)
    except Exception as exc:
        raise TerminalCorrectionError(
            f"terminal clean-commit authority/schema validation failed: {exc}"
        ) from exc
    return authority


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TerminalCorrectionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _status_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise TerminalCorrectionError("cannot inspect exact Git delta")
    paths: set[str] = set()
    entries = result.stdout.split(b"\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        decoded = entry.decode("utf-8", errors="strict")
        if len(decoded) < 4:
            raise TerminalCorrectionError("Git status entry is malformed")
        status = decoded[:2]
        path = decoded[3:]
        if "R" in status or "C" in status:
            if index >= len(entries) or not entries[index]:
                raise TerminalCorrectionError("Git rename status is malformed")
            path = entries[index].decode("utf-8", errors="strict")
            index += 1
        paths.add(path)
    return paths


def _is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    result = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def verify_clean_commit_authority_bytes(
    authority: Mapping[str, Any], root: Path
) -> None:
    for record in authority["source_authority"]:
        path = root / record["path"]
        if not path.is_file() or _sha256(path) != record["sha256"]:
            raise TerminalCorrectionError(
                f"clean-commit source authority byte identity mismatch: {record['path']}"
            )


def _clean_candidate_bytes_exact(
    authority: Mapping[str, Any], root: Path
) -> bool:
    return all(
        (root / record["path"]).is_file()
        and _sha256(root / record["path"]) == record["sha256"]
        for record in authority["implementation_transition"]["paths"]
    )


def verify_clean_candidate_bytes(
    authority: Mapping[str, Any], root: Path
) -> None:
    for record in authority["implementation_transition"]["paths"]:
        candidate = root / record["path"]
        if not candidate.is_file() or _sha256(candidate) != record["sha256"]:
            raise TerminalCorrectionError(
                f"clean committed candidate byte identity mismatch: {record['path']}"
            )


def verify_clean_commit_authority_delta(
    authority: Mapping[str, Any],
    root: Path,
    *,
    include_committed_candidate: bool = False,
    observed: set[str] | None = None,
    observed_worktree: set[str] | None = None,
    base_is_ancestor: bool | None = None,
) -> None:
    base = str(authority["authority_base_sha"])
    if base_is_ancestor is None:
        base_is_ancestor = _is_ancestor(root, base)
    if not base_is_ancestor:
        raise TerminalCorrectionError("clean-commit authority base is not an ancestor of HEAD")
    expected = set(authority["scope"]["authority_write_scope"])
    if include_committed_candidate:
        expected |= set(authority["scope"]["candidate_scope"])
    if observed is None:
        head = _git(root, "rev-parse", "HEAD")
        worktree = _status_paths(root)
        if head == base:
            actual = worktree
            permitted_worktree = expected
        else:
            actual = {
                line
                for line in _git(
                    root, "diff", "--name-only", f"{base}..{head}", "--"
                ).splitlines()
                if line
            }
            permitted_worktree = set()
    else:
        actual = observed
        permitted_worktree = set()
        worktree = observed_worktree or set()
    if worktree != permitted_worktree:
        raise TerminalCorrectionError(
            "clean-commit authority worktree delta must be exact: "
            f"expected={sorted(permitted_worktree)} actual={sorted(worktree)}"
        )
    if actual != expected:
        raise TerminalCorrectionError(
            "clean-commit authority Git delta must be exact: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def verify_clean_candidate_transition(
    authority: Mapping[str, Any],
    root: Path,
    *,
    observed_head: str | None = None,
    observed_head_tree: str | None = None,
    observed_worktree: set[str] | None = None,
    observed_committed_delta: set[str] | None = None,
    base_is_ancestor: bool | None = None,
) -> str:
    transition = authority["implementation_transition"]
    base = str(transition["base_sha"])
    bound_head = str(transition["head_sha"])
    base_tree = str(authority["authority_base_tree_sha"])
    candidate_scope = set(authority["scope"]["candidate_scope"])
    authority_scope = set(authority["scope"]["authority_write_scope"])
    head = observed_head or _git(root, "rev-parse", "HEAD")
    head_tree = observed_head_tree or _git(root, "rev-parse", "HEAD^{tree}")
    worktree = _status_paths(root) if observed_worktree is None else observed_worktree

    if worktree == candidate_scope:
        if head_tree != base_tree:
            raise TerminalCorrectionError(
                "dirty prepublication head tree does not match exact authority main"
            )
        return "dirty_prepublication"
    if worktree:
        raise TerminalCorrectionError(
            "candidate Git delta must be exact and all-or-none: "
            f"expected={sorted(candidate_scope)} actual={sorted(worktree)}"
        )

    if base_is_ancestor is None:
        base_is_ancestor = _is_ancestor(root, base, head)
    if not base_is_ancestor:
        raise TerminalCorrectionError(
            "clean committed candidate base is not an ancestor of HEAD"
        )
    if observed_committed_delta is None:
        committed_delta = {
            line
            for line in _git(
                root, "diff", "--name-only", f"{base}..{head}", "--"
            ).splitlines()
            if line
        }
    else:
        committed_delta = observed_committed_delta
    if head == bound_head and committed_delta == candidate_scope:
        return "clean_pr_head"
    if committed_delta == authority_scope | candidate_scope:
        return "clean_integrated"
    raise TerminalCorrectionError(
        "clean committed candidate lineage/delta must be exact: "
        f"head={head} expected_head={bound_head} "
        f"expected_candidate={sorted(candidate_scope)} "
        f"expected_integrated={sorted(authority_scope | candidate_scope)} "
        f"actual={sorted(committed_delta)}"
    )


def verify_exact_authority_delta(
    authority: Mapping[str, Any],
    root: Path,
    *,
    observed: set[str] | None = None,
    allowed_worktree_delta: set[str] | None = None,
    base_is_ancestor: bool | None = None,
) -> None:
    if (
        observed is None
        and allowed_worktree_delta is None
        and (root / CLEAN_COMMIT_AUTHORITY_PATH).is_file()
    ):
        clean_commit = load_clean_commit_authority(root)
        verify_clean_commit_authority_bytes(clean_commit, root)
        include_committed_candidate = False
        if _clean_candidate_bytes_exact(clean_commit, root):
            representation = verify_clean_candidate_transition(clean_commit, root)
            include_committed_candidate = representation == "clean_integrated"
        verify_clean_commit_authority_delta(
            clean_commit,
            root,
            include_committed_candidate=include_committed_candidate,
        )
        return
    expected = set(authority["scope"]["authority_write_scope"])
    base = str(authority["authority_base_sha"])
    if base_is_ancestor is None:
        ancestor = subprocess.run(
            ("git", "merge-base", "--is-ancestor", base, "HEAD"),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        base_is_ancestor = ancestor.returncode == 0
    if not base_is_ancestor:
        raise TerminalCorrectionError("authority base is not an ancestor of HEAD")
    if observed is None:
        head = _git(root, "rev-parse", "HEAD")
        worktree = _status_paths(root)
        if head == base:
            actual = worktree
        else:
            actual = {
                line
                for line in _git(root, "diff", "--name-only", f"{base}..{head}", "--").splitlines()
                if line
            }
            permitted = allowed_worktree_delta or set()
            if worktree != permitted:
                raise TerminalCorrectionError(
                    "authority worktree delta must be exact: "
                    f"expected={sorted(permitted)} actual={sorted(worktree)}"
                )
    else:
        actual = observed
    if actual != expected:
        raise TerminalCorrectionError(
            "authority Git delta must be exact: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def verify_exact_candidate_delta(
    authority: Mapping[str, Any],
    root: Path,
    *,
    observed: set[str] | None = None,
) -> None:
    expected = set(authority["scope"]["combined_candidate_scope"])
    actual = _status_paths(root) if observed is None else observed
    if actual != expected:
        raise TerminalCorrectionError(
            "candidate Git delta must be exact and all-or-none: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def verify_immutable_authority_bytes(authority: Mapping[str, Any], root: Path) -> None:
    for record in authority["immutable_authorities"]:
        path = root / record["path"]
        if not path.is_file() or _sha256(path) != record["sha256"]:
            raise TerminalCorrectionError(
                f"immutable authority byte identity mismatch: {record['path']}"
            )


def _verify_record(root: Path, record: Mapping[str, Any], label: str) -> Path:
    path = root / str(record["path"])
    if not path.is_file() or _sha256(path) != record["sha256"]:
        raise TerminalCorrectionError(f"{label} byte identity mismatch: {record['path']}")
    return path


def verify_corrected_cohort(authority: Mapping[str, Any], root: Path) -> None:
    cohort = authority["corrected_candidate_cohort"]
    if len(cohort) != 3:
        raise TerminalCorrectionError("corrected candidate cohort is incomplete")
    for record in cohort:
        _verify_record(root, record, "corrected candidate")


def verify_terminal_evidence(
    authority: Mapping[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = authority["terminal_evidence"]
    v1_path = _verify_record(root, evidence["v1_ledger"], "v1 ledger")
    v2_path = _verify_record(root, evidence["v2_ledger"], "v2 ledger")
    stderr_path = _verify_record(root, evidence["v2_stderr"], "v2 stderr")
    _verify_record(root, evidence["v2_stdout"], "v2 stdout")
    v1 = _load_json(v1_path)
    v2 = _load_json(v2_path)
    if {
        "state": v1.get("state"),
        "token_consumed": v1.get("token_consumed"),
        "token_status": v1.get("token_status"),
    } != {
        "state": "prelaunch_failed",
        "token_consumed": False,
        "token_status": "unspent_unavailable",
    }:
        raise TerminalCorrectionError("v1 terminal state was rewritten")
    launch_v1 = v1.get("launch")
    if not isinstance(launch_v1, Mapping) or launch_v1.get("matching_processes") != []:
        raise TerminalCorrectionError("v1 process evidence was rewritten")
    expected_v2 = {
        "state": "failed_after_launch",
        "token_consumed": True,
        "token_status": "consumed",
        "token_consumed_at_utc": "2026-08-19T19:44:55Z",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
    }
    for field, value in expected_v2.items():
        if v2.get(field) != value:
            raise TerminalCorrectionError(f"v2 terminal field changed: {field}")
    process = v2.get("process")
    if not isinstance(process, Mapping) or {
        "pid": process.get("pid"),
        "parent_pid": process.get("parent_pid"),
        "run_token_id": process.get("run_token_id"),
    } != {
        "pid": 20482,
        "parent_pid": 20450,
        "run_token_id": "ck07r1-all-profile-e2e-1",
    }:
        raise TerminalCorrectionError("v2 child identity changed")
    launch_v2 = v2.get("launch")
    if not isinstance(launch_v2, Mapping) or launch_v2.get("matching_processes") != []:
        raise TerminalCorrectionError("v2 process collision evidence changed")
    failed_cohort = launch_v2.get("prelaunch_recovery", {}).get("candidate_cohort")
    if failed_cohort != authority["failed_candidate_cohort"]:
        raise TerminalCorrectionError("v2 failed candidate cohort binding changed")
    failure = v2.get("failure")
    if not isinstance(failure, Mapping) or failure.get("stage") != "evidence_collection":
        raise TerminalCorrectionError("v2 terminal failure classification changed")
    stderr = _load_json(stderr_path)
    reproduction = authority["planner_reproduction"]["standard_30_day"]
    if {
        "exception_type": stderr.get("exception_type"),
        "failure": stderr.get("failure"),
        "selected_fragment": (
            f"selected_records={reproduction['selected_records']}" in str(stderr.get("message"))
        ),
        "reason_fragment": ("limit_exceeded:selected_records" in str(stderr.get("message"))),
    } != {
        "exception_type": "AssertionError",
        "failure": "child_exception",
        "selected_fragment": True,
        "reason_fragment": True,
    }:
        raise TerminalCorrectionError("v2 stderr planner failure identity changed")
    for relative in evidence["required_absent_paths"]:
        if (root / relative).exists():
            raise TerminalCorrectionError(f"forbidden terminal artifact exists: {relative}")
    return v1, v2


def verify_planner_reproduction(authority: Mapping[str, Any], root: Path) -> None:
    code = r"""
import json
from codex_usage_tracker.agent_kernel.publication.planner import RefreshIntent, plan_refresh
from scripts import benchmark_ck07r1_lifecycle_scale as b
rows = {}
for profile_name, days in (("standard", 30), ("production", None)):
    scale = b._scale_observations(profile_name, b._profile(profile_name), days)
    chunk = scale[: b.PUBLICATION_CHUNK_OBSERVATIONS]
    plan = plan_refresh(
        b._changes(chunk),
        RefreshIntent(
            parent_publication_id="publication:seed",
            parent_observed_at_us=1_800_000_000_000_000,
            planned_at_us=1_800_000_000_000_001,
            history_preset="all_time",
            current_history_preset="all_time",
        ),
        limits=b._tail_limits(),
        dirty_keys=0,
        projection_rows=0,
        expected_wal_bytes=None,
    )
    rows[profile_name] = {
        "operation_class": plan.operation_class.value,
        "reasons": list(plan.reasons),
        "selected_records": plan.estimate.selected_records,
        "expected_wal_bytes": plan.estimate.expected_wal_bytes,
        "observations": plan.estimate.observations,
    }
print(json.dumps(rows, sort_keys=True, separators=(",", ":")))
"""
    result = subprocess.run(
        (str(root / ".venv/bin/python"), "-c", code),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
        },
    )
    if result.returncode != 0:
        raise TerminalCorrectionError(
            f"non-consuming planner reproduction failed: {result.stderr.strip()}"
        )
    try:
        observed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TerminalCorrectionError("planner reproduction output is invalid") from exc
    expected = {
        "standard": authority["planner_reproduction"]["standard_30_day"],
        "production": authority["planner_reproduction"]["production_first_chunk"],
    }
    if observed != expected:
        raise TerminalCorrectionError(
            f"planner reproduction drifted: expected={expected} actual={observed}"
        )


def verify_combined(
    authority: Mapping[str, Any],
    root: Path,
    *,
    authority_root: Path | None = None,
) -> dict[str, Any]:
    clean_commit_root = authority_root or root
    clean_commit_path = clean_commit_root / CLEAN_COMMIT_AUTHORITY_PATH
    if clean_commit_path.is_file():
        clean_commit = load_clean_commit_authority(clean_commit_root)
        verify_clean_commit_authority_bytes(clean_commit, clean_commit_root)
        same_root = clean_commit_root == root
        if same_root:
            representation = verify_clean_candidate_transition(clean_commit, root)
            verify_clean_commit_authority_delta(
                clean_commit,
                clean_commit_root,
                include_committed_candidate=representation == "clean_integrated",
            )
        else:
            verify_clean_commit_authority_delta(clean_commit, clean_commit_root)
            representation = verify_clean_candidate_transition(clean_commit, root)
        verify_clean_candidate_bytes(clean_commit, root)
    else:
        candidate_delta = set(authority["scope"]["combined_candidate_scope"])
        verify_immutable_authority_bytes(authority, root)
        verify_exact_authority_delta(
            authority,
            root,
            allowed_worktree_delta=candidate_delta,
        )
        verify_exact_candidate_delta(authority, root)
        representation = "dirty_prepublication"
    verify_corrected_cohort(authority, root)
    verify_terminal_evidence(authority, root)
    verify_planner_reproduction(authority, root)
    return {
        "candidate_paths": len(authority["scope"]["combined_candidate_scope"]),
        "new_run_permitted": False,
        "runtime_acceptance": "not_claimed",
        "token_consumed": True,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("authority", "combined"))
    parser.add_argument("--authority-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-root", type=Path)
    args = parser.parse_args(argv)
    authority_root = args.authority_root.absolute()
    authority = load_authority(authority_root)
    verify_immutable_authority_bytes(authority, authority_root)
    verify_exact_authority_delta(authority, authority_root)
    clean_commit = (
        load_clean_commit_authority(authority_root)
        if (authority_root / CLEAN_COMMIT_AUTHORITY_PATH).is_file()
        else None
    )
    result: dict[str, Any] = {
        "authority_paths": len(
            clean_commit["scope"]["authority_write_scope"]
            if clean_commit is not None
            else authority["scope"]["authority_write_scope"]
        ),
        "authority_schema": (
            clean_commit["schema"] if clean_commit is not None else authority["schema"]
        ),
        "status": authority["status"],
        "verification": "passed",
    }
    if args.command == "combined":
        if args.candidate_root is None:
            parser.error("--candidate-root is required for combined")
        result.update(
            verify_combined(
                authority,
                args.candidate_root.absolute(),
                authority_root=authority_root,
            )
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
