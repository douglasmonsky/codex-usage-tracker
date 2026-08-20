#!/usr/bin/env python3
"""Verify the non-consuming CK-07R1 post-terminal roadmap transition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

AUTHORITY_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-post-terminal-completion-authority-v1.json"
)
SCHEMA_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-post-terminal-completion-authority-v1.schema.json"
)
REMAINING_PLAN_PATH = Path("docs/roadmap/REMAINING_EXECUTION_PLAN.md")
TASK_PACKETS_PATH = Path("docs/roadmap/TASK_PACKETS.md")
CK07R1_PACKET_PATH = Path("docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md")
CK08R4_PACKET_PATH = Path("docs/roadmap/tasks/ck-08r4-reclassify-physical-plans.md")


class PostTerminalCompletionError(RuntimeError):
    """The exact post-terminal roadmap completion contract is not satisfied."""


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
        raise PostTerminalCompletionError(f"cannot load exact JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PostTerminalCompletionError(f"exact JSON is not an object: {path}")
    return value


def load_authority(root: Path) -> dict[str, Any]:
    authority = _load_json(root / AUTHORITY_PATH)
    schema = _load_json(root / SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(authority)
    except Exception as exc:
        raise PostTerminalCompletionError(
            f"post-terminal authority/schema validation failed: {exc}"
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
        raise PostTerminalCompletionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    result = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _status_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise PostTerminalCompletionError("cannot inspect exact Git worktree delta")
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
            raise PostTerminalCompletionError("Git status entry is malformed")
        status = decoded[:2]
        relative = decoded[3:]
        if "R" in status or "C" in status:
            if index >= len(entries) or not entries[index]:
                raise PostTerminalCompletionError("Git rename status is malformed")
            relative = entries[index].decode("utf-8", errors="strict")
            index += 1
        paths.add(relative)
    return paths


def _diff_paths(root: Path, base: str, head: str = "HEAD") -> set[str]:
    output = _git(root, "diff", "--name-only", "--no-renames", base, head)
    return {line for line in output.splitlines() if line}


def _git_blob_sha256(root: Path, revision: str, relative: str) -> str:
    result = subprocess.run(
        ("git", "show", f"{revision}:{relative}"),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise PostTerminalCompletionError(
            f"cannot read exact Git blob {revision}:{relative}"
        )
    return hashlib.sha256(result.stdout).hexdigest()


def verify_source_authorities(authority: Mapping[str, Any], root: Path) -> None:
    for record in authority["source_authorities"]:
        path = root / str(record["path"])
        if not path.is_file() or _sha256(path) != record["sha256"]:
            raise PostTerminalCompletionError(
                f"source authority byte identity mismatch: {record['path']}"
            )


def verify_historical_successor_bindings(
    authority: Mapping[str, Any], root: Path
) -> None:
    base = str(authority["authority_base_sha"])
    scope = set(authority["scope"]["authority_write_scope"])
    for record in authority["historical_successor_bindings"]:
        relative = str(record["path"])
        path = root / relative
        if relative not in scope:
            raise PostTerminalCompletionError(
                f"historical successor binding escapes authority scope: {relative}"
            )
        if _git_blob_sha256(root, base, relative) != record["predecessor_sha256"]:
            raise PostTerminalCompletionError(
                f"historical predecessor byte identity mismatch: {relative}"
            )
        if not path.is_file() or _sha256(path) != record["successor_sha256"]:
            raise PostTerminalCompletionError(
                f"historical successor byte identity mismatch: {relative}"
            )


def verify_integrated_cohort(authority: Mapping[str, Any], root: Path) -> None:
    cohort = authority["integrated_cohort"]
    for record in cohort["paths"]:
        path = root / str(record["path"])
        if not path.is_file() or _sha256(path) != record["sha256"]:
            raise PostTerminalCompletionError(
                f"integrated cohort byte identity mismatch: {record['path']}"
            )
    expected_paths = {str(record["path"]) for record in cohort["paths"]}
    if expected_paths != set(authority["scope"]["immutable_integrated_scope"]):
        raise PostTerminalCompletionError(
            "integrated cohort and immutable scope are not the same exact set"
        )


def verify_terminal_history(authority: Mapping[str, Any], root: Path) -> None:
    records = {str(record["role"]): record for record in authority["integrated_cohort"]["paths"]}
    v1 = _load_json(root / records["immutable_v1_prelaunch_failed_ledger"]["path"])
    v2 = _load_json(root / records["immutable_v2_failed_after_launch_ledger"]["path"])
    expected_v1 = authority["terminal_history"]["v1"]
    expected_v2 = authority["terminal_history"]["v2"]
    if (
        v1.get("state") != expected_v1["state"]
        or v1.get("token_consumed") is not expected_v1["token_consumed"]
        or v1.get("token_status") != expected_v1["token_status"]
        or v1.get("retry_allowed") is not False
        or v1.get("restart_allowed") is not False
        or v1.get("replacement_allowed") is not False
    ):
        raise PostTerminalCompletionError("immutable v1 terminal state drifted")
    process = v2.get("process")
    failure = v2.get("failure")
    if not isinstance(process, dict) or not isinstance(failure, dict):
        raise PostTerminalCompletionError("immutable v2 process/failure evidence is absent")
    if (
        v2.get("state") != expected_v2["state"]
        or v2.get("token_consumed") is not expected_v2["token_consumed"]
        or v2.get("token_status") != expected_v2["token_status"]
        or v2.get("token_consumed_at_utc") != expected_v2["token_consumed_at_utc"]
        or process.get("pid") != expected_v2["child_pid"]
        or failure.get("stage") != expected_v2["failure_stage"]
        or v2.get("retry_allowed") is not False
        or v2.get("restart_allowed") is not False
        or v2.get("replacement_allowed") is not False
    ):
        raise PostTerminalCompletionError("immutable v2 terminal state drifted")
    for relative in authority["terminal_history"]["required_absent_paths"]:
        if (root / str(relative)).exists():
            raise PostTerminalCompletionError(f"forbidden runtime artifact exists: {relative}")


def verify_publication_evidence(authority: Mapping[str, Any], root: Path) -> None:
    for label, record in authority["publication_evidence"].items():
        head_tree = _git(root, "rev-parse", f"{record['head_sha']}^{{tree}}")
        merge_tree = _git(root, "rev-parse", f"{record['merge_sha']}^{{tree}}")
        if head_tree != record["head_tree_sha"] or merge_tree != record["merge_tree_sha"]:
            raise PostTerminalCompletionError(f"bound publication tree identity drifted: {label}")
        parents = _git(root, "rev-list", "--parents", "-n", "1", record["merge_sha"])
        parent_values = parents.split()[1:]
        if parent_values != [record["base_sha"]]:
            raise PostTerminalCompletionError(f"bound squash lineage drifted: {label}")


def _delegation_manifest(root: Path) -> dict[str, Any]:
    text = (root / REMAINING_PLAN_PATH).read_text(encoding="utf-8")
    match = re.search(
        r"<!-- delegated-task-dag:start -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- delegated-task-dag:end -->",
        text,
        re.DOTALL,
    )
    if match is None:
        raise PostTerminalCompletionError("machine delegation DAG is absent")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise PostTerminalCompletionError("machine delegation DAG is not an object")
    return value


def verify_roadmap_transition(authority: Mapping[str, Any], root: Path) -> None:
    manifest = _delegation_manifest(root)
    transition = authority["roadmap_transition"]
    completed = set(manifest.get("completed", []))
    ready = manifest.get("ready")
    if not set(transition["completed"]).issubset(completed):
        raise PostTerminalCompletionError("CK-07R1 is not machine-completed")
    if ready != transition["new_ready"]:
        raise PostTerminalCompletionError(
            "machine Ready set is not the exact post-terminal successor set"
        )
    if manifest.get("conditional_ready") != [] or manifest.get("blocked") != []:
        raise PostTerminalCompletionError("machine policy retains an unexpected explicit hold")
    accounting = (root / TASK_PACKETS_PATH).read_text(encoding="utf-8")
    ck07r1 = (root / CK07R1_PACKET_PATH).read_text(encoding="utf-8")
    ck08r4 = (root / CK08R4_PACKET_PATH).read_text(encoding="utf-8")
    required_accounting = (
        "Completed corrective child tasks: **14",
        "Remaining delegable child tasks: **36**",
        "Ready child tasks: **1 — CK-08R4**",
        "Blocked child tasks: **35",
        "[x] **CK-07R1",
        "[ ] **CK-08R4",
    )
    if any(claim not in accounting for claim in required_accounting):
        raise PostTerminalCompletionError("task accounting did not transition atomically")
    if (
        "**Status:** `completed_post_terminal_deterministic_evidence`" not in ck07r1
        or "**Status:** Ready" not in ck08r4
        or "runtime_acceptance=not_claimed" not in ck07r1
        or "CK-08RG and CK-09 remain blocked" not in ck08r4
    ):
        raise PostTerminalCompletionError("packet readiness wording drifted")


def verify_decision(authority: Mapping[str, Any]) -> None:
    decision = authority["decision"]
    if decision != {
        "completion_basis": "deterministic_post_terminal_merged_evidence",
        "corrective_implementation_state": ("accepted_for_CK-07R1_roadmap_dependency"),
        "roadmap_dependency_completion": (
            "authorized_on_authority_PR_merge_and_fresh_exact_main_verification"
        ),
        "runtime_acceptance": "not_claimed",
        "planner_valid_receipt": "absent",
        "receipt_fabrication": "forbidden",
        "post_single_run": "unavailable",
        "final_accepted": "unavailable",
        "failed_after_launch_reclassified": False,
        "new_command_invocations_permitted": 0,
        "launch_authorized": False,
        "token_consumed": True,
        "token_refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "production_semantics_changed_by_authority": False,
    }:
        raise PostTerminalCompletionError("post-terminal decision weakened or drifted")


def verify_authority_delta(
    authority: Mapping[str, Any],
    root: Path,
    *,
    observed_head: str | None = None,
    observed_worktree: set[str] | None = None,
    observed_committed: set[str] | None = None,
    base_is_ancestor: bool | None = None,
) -> str:
    base = str(authority["authority_base_sha"])
    expected = set(authority["scope"]["authority_write_scope"])
    if _git(root, "rev-parse", f"{base}^{{tree}}") != authority["authority_base_tree_sha"]:
        raise PostTerminalCompletionError("authority base tree identity drifted")
    head = observed_head if observed_head is not None else _git(root, "rev-parse", "HEAD")
    worktree = observed_worktree if observed_worktree is not None else _status_paths(root)
    if head == base:
        if worktree != expected:
            raise PostTerminalCompletionError("prepublication authority Git delta is not exact")
        return "dirty_prepublication"
    ancestor = base_is_ancestor if base_is_ancestor is not None else _is_ancestor(root, base, head)
    if not ancestor:
        raise PostTerminalCompletionError("authority base is not an ancestor")
    committed = (
        observed_committed if observed_committed is not None else _diff_paths(root, base, head)
    )
    if worktree or committed != expected:
        raise PostTerminalCompletionError("committed authority Git delta is not exact")
    return "clean_committed"


def verify_all(authority: Mapping[str, Any], root: Path) -> dict[str, Any]:
    verify_source_authorities(authority, root)
    verify_historical_successor_bindings(authority, root)
    verify_integrated_cohort(authority, root)
    verify_terminal_history(authority, root)
    verify_publication_evidence(authority, root)
    verify_decision(authority)
    verify_roadmap_transition(authority, root)
    representation = verify_authority_delta(authority, root)
    return {
        "authority_schema": authority["schema"],
        "representation": representation,
        "runtime_acceptance": "not_claimed",
        "planner_valid_receipt": "absent",
        "token_consumed": True,
        "new_command_invocations_permitted": 0,
        "completed": ["CK-07R1"],
        "ready": ["CK-08R4"],
        "verification": "passed",
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("authority",))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.absolute()
    authority = load_authority(root)
    print(json.dumps(verify_all(authority, root), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
