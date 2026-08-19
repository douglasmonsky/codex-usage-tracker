#!/usr/bin/env python3
"""Fail-closed CK-07R1 prelaunch-failure recovery verifier.

This module never launches the qualification child.  It binds the preserved
terminal v1 ledger, the exact corrected candidate cohort, the non-colliding v2
paths, and the still-unspent one-run token before a corrected launcher may
create any new durable state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

AUTHORITY_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.json"
)
SCHEMA_PATH = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.schema.json"
)
MINIMUM_CAPACITY_BYTES = 10 * 1024**3


class PrelaunchRecoveryError(RuntimeError):
    """The exact recovery contract is not satisfied."""


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
        raise PrelaunchRecoveryError(f"cannot load exact JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PrelaunchRecoveryError(f"exact JSON is not an object: {path}")
    return value


def load_authority(root: Path) -> dict[str, Any]:
    authority_path = root / AUTHORITY_PATH
    schema_path = root / SCHEMA_PATH
    authority = _load_json(authority_path)
    schema = _load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(authority)
    except Exception as exc:
        raise PrelaunchRecoveryError(
            f"prelaunch recovery authority/schema validation failed: {exc}"
        ) from exc
    return authority


def verify_bound_authority_bytes(authority: Mapping[str, Any], root: Path) -> None:
    records = authority.get("immutable_authorities")
    if not isinstance(records, list) or not records:
        raise PrelaunchRecoveryError("immutable authority set is missing")
    for record in records:
        if not isinstance(record, Mapping):
            raise PrelaunchRecoveryError("immutable authority record is malformed")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise PrelaunchRecoveryError("immutable authority identity is malformed")
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise PrelaunchRecoveryError(f"immutable authority byte identity mismatch: {relative}")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PrelaunchRecoveryError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _status_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise PrelaunchRecoveryError("cannot inspect candidate Git delta")
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
            raise PrelaunchRecoveryError("candidate Git status entry is malformed")
        status = decoded[:2]
        path = decoded[3:]
        if "R" in status or "C" in status:
            if index >= len(entries) or not entries[index]:
                raise PrelaunchRecoveryError("candidate rename status is malformed")
            path = entries[index].decode("utf-8", errors="strict")
            index += 1
        paths.add(path)
    return paths


def verify_exact_candidate_delta(
    authority: Mapping[str, Any],
    candidate_root: Path,
    *,
    observed: set[str] | None = None,
) -> None:
    expected = set(authority["scope"]["combined_preflight_candidate_scope"])
    actual = _status_paths(candidate_root) if observed is None else observed
    if actual != expected:
        raise PrelaunchRecoveryError(
            "candidate Git delta must be exact and all-or-none: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def verify_exact_authority_delta(
    authority: Mapping[str, Any],
    authority_root: Path,
    *,
    observed: set[str] | None = None,
) -> None:
    expected = set(authority["scope"]["authority_write_scope"])
    if observed is None:
        base = str(authority["authority_base_sha"])
        tracked = {
            line
            for line in _git(authority_root, "diff", "--name-only", base, "--").splitlines()
            if line
        }
        untracked = {
            line
            for line in _git(
                authority_root,
                "ls-files",
                "--others",
                "--exclude-standard",
            ).splitlines()
            if line
        }
        actual = tracked | untracked
    else:
        actual = observed
    if actual != expected:
        raise PrelaunchRecoveryError(
            "authority Git delta must be exact: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def verify_candidate_cohort(authority: Mapping[str, Any], candidate_root: Path) -> None:
    records = authority.get("candidate_cohort")
    if not isinstance(records, list) or len(records) != 3:
        raise PrelaunchRecoveryError("corrected candidate cohort is malformed")
    for record in records:
        if not isinstance(record, Mapping):
            raise PrelaunchRecoveryError("corrected candidate record is malformed")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise PrelaunchRecoveryError("corrected candidate identity is malformed")
        path = candidate_root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise PrelaunchRecoveryError(f"corrected candidate identity mismatch: {relative}")


def verify_preserved_failure_ledger(
    authority: Mapping[str, Any], candidate_root: Path
) -> dict[str, Any]:
    lineage = authority["preserved_failure_lineage"]
    preserved = authority["preserved_v1_ledger"]
    relative = str(preserved["path"])
    ledger_path = candidate_root / relative
    if not ledger_path.is_file():
        raise PrelaunchRecoveryError("preserved terminal v1 ledger is missing")
    if _sha256(ledger_path) != preserved["sha256"]:
        raise PrelaunchRecoveryError("preserved terminal v1 ledger bytes changed")
    ledger = _load_json(ledger_path)
    expected = {
        "schema": lineage["ledger_schema"],
        "state": "prelaunch_failed",
        "run_token_id": authority["run_token"]["id"],
        "maximum_new_end_to_end_runs": 1,
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "first_result_retained": True,
    }
    for field, value in expected.items():
        if ledger.get(field) != value:
            raise PrelaunchRecoveryError(f"preserved terminal v1 ledger field changed: {field}")
    failure = ledger.get("failure")
    if not isinstance(failure, Mapping) or {
        "stage": failure.get("stage"),
        "exception_type": failure.get("exception_type"),
        "message": failure.get("message"),
    } != {
        "stage": "child_start_handshake",
        "exception_type": "RuntimeError",
        "message": "child-start handshake did not prove exact PID/argv/cwd/owner",
    }:
        raise PrelaunchRecoveryError("preserved terminal v1 failure identity changed")
    forbidden = {
        "process",
        "receipt",
        "evidence",
        "completed_at_utc",
        "token_consumed_at_utc",
    }
    if forbidden.intersection(ledger):
        raise PrelaunchRecoveryError(
            "preserved terminal v1 ledger fabricates launched/runtime evidence"
        )
    launch = ledger.get("launch")
    if not isinstance(launch, Mapping) or launch.get("matching_processes") != []:
        raise PrelaunchRecoveryError("preserved terminal v1 process evidence changed")
    if {
        "path": relative,
        "sha256": _sha256(ledger_path),
        "state": ledger["state"],
        "token_consumed": ledger["token_consumed"],
        "token_status": ledger["token_status"],
        "matching_processes": launch["matching_processes"],
    } != preserved:
        raise PrelaunchRecoveryError("preserved terminal v1 authority binding drifted")
    old_paths = authority["preserved_failure_lineage"]["exclusive_paths"]
    for name in ("output", "stdout", "stderr"):
        if (candidate_root / old_paths[name]).exists():
            raise PrelaunchRecoveryError(
                f"unexpected v1 runtime artifact exists: {old_paths[name]}"
            )
    return ledger


def verify_new_paths_absent(authority: Mapping[str, Any], candidate_root: Path) -> None:
    paths = authority["launch_contract"]["exclusive_paths"]
    present = [relative for relative in paths.values() if (candidate_root / str(relative)).exists()]
    if present:
        raise PrelaunchRecoveryError(f"recovery launch path already exists: {sorted(present)}")


def verify_current_exact_main(root: Path) -> str:
    head = _git(root, "rev-parse", "HEAD")
    tracking = _git(root, "rev-parse", "refs/remotes/origin/main")
    remote_line = _git(root, "ls-remote", "origin", "refs/heads/main")
    remote = remote_line.split()[0] if remote_line else ""
    if not head or head != tracking or head != remote:
        raise PrelaunchRecoveryError(
            "recovery activation requires HEAD == fetched origin/main == live origin/main"
        )
    return head


def verify_minimum_capacity(root: Path, *, observed_bytes: int | None = None) -> int:
    available = shutil.disk_usage(root).free if observed_bytes is None else observed_bytes
    if available < MINIMUM_CAPACITY_BYTES:
        raise PrelaunchRecoveryError("recovery activation requires at least 10 GiB free")
    return available


def verify_frozen_candidate_root(
    authority: Mapping[str, Any], root: Path
) -> None:
    expected = Path(str(authority["launch_contract"]["cwd"])).absolute()
    actual = root.absolute()
    if actual != expected:
        raise PrelaunchRecoveryError(
            "recovery activation requires the exact frozen lexical cwd: "
            f"expected={expected} actual={actual}"
        )


def verify_pre_side_effect_recovery(root: Path) -> dict[str, Any]:
    """Verify every static recovery gate from the exact candidate root."""

    authority = load_authority(root)
    verify_frozen_candidate_root(authority, root)
    verify_bound_authority_bytes(authority, root)
    verify_current_exact_main(root)
    available = verify_minimum_capacity(root)
    verify_candidate_cohort(authority, root)
    verify_exact_candidate_delta(authority, root)
    verify_preserved_failure_ledger(authority, root)
    verify_new_paths_absent(authority, root)
    return {
        "schema": authority["schema"],
        "authority_version": authority["authority_version"],
        "authority_base_sha": authority["authority_base_sha"],
        "verification": "passed",
        "preserved_v1_ledger": authority["preserved_v1_ledger"],
        "candidate_cohort": authority["candidate_cohort"],
        "v2_paths": authority["v2_paths"],
        "run_token_id": authority["run_token"]["id"],
        "token_status": authority["run_token"]["status"],
        "token_consumed": authority["run_token"]["token_consumed"],
        "disk_available_bytes": available,
        "retry": authority["run_token"]["retry"],
        "restart": authority["run_token"]["restart"],
        "replacement": authority["run_token"]["replacement"],
    }


def verify_prelaunch_recovery(root: Path) -> tuple[dict[str, Any], str]:
    """Return the exact launcher-facing recovery authority and verified state."""

    verify_pre_side_effect_recovery(root)
    return load_authority(root), "prelaunch_recovery_verified"


def evaluate_recovery_prelaunch(
    authority: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, Any]:
    contract = authority["launch_contract"]
    worker = authority["worker"]
    token = authority["run_token"]
    required_environment = contract["environment"]["required"]
    exact = {
        "worker_thread_id": worker["thread_id"],
        "cwd": contract["cwd"],
        "argv": contract["argv"],
        "environment": required_environment,
        "interpreter": contract["cwd"] + "/.venv/bin/python",
        "venv_prefix": contract["cwd"] + "/.venv",
        "authority_integrity": "passed",
        "candidate_cohort": "passed",
        "candidate_delta": "passed",
        "preserved_ledger": "passed",
        "new_paths_present": [],
        "matching_processes": [],
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "prior_invocation_state": "prelaunch_failed",
        "prior_successful_child": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "synthetic_fixture": True,
        "live_or_real_data": False,
    }
    for field, expected in exact.items():
        if observation.get(field) != expected:
            raise PrelaunchRecoveryError(f"recovery prelaunch gate failed: {field}")
    present = observation.get("environment_present")
    if not isinstance(present, Mapping):
        raise PrelaunchRecoveryError("recovery prelaunch gate failed: environment_present")
    for name in contract["environment"]["forbidden"]:
        if name in present:
            raise PrelaunchRecoveryError(
                f"recovery prelaunch gate failed: forbidden environment {name}"
            )
    capacity = observation.get("disk_available_bytes")
    if not isinstance(capacity, int) or capacity < MINIMUM_CAPACITY_BYTES:
        raise PrelaunchRecoveryError("recovery prelaunch gate failed: disk_available_bytes")
    if token != {
        "id": "ck07r1-all-profile-e2e-1",
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "token_consumed": False,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "successful_launches_observed": 0,
        "new_recovery_invocations_permitted": 1,
        "consumption": "first_successfully_observed_exact_child_launch_and_handshake",
    }:
        raise PrelaunchRecoveryError("recovery run-token contract drifted")
    return {
        "decision": "recovery_launch_authorized_once",
        "run_token_id": token["id"],
        "new_command_invocations_permitted": 1,
        "consume_only_after_successful_child_handshake": True,
        "prior_prelaunch_failure_is_not_a_launched_process_retry": True,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("authority", "combined"))
    parser.add_argument("--authority-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-root", type=Path)
    args = parser.parse_args(argv)
    authority_root = args.authority_root.absolute()
    authority = load_authority(authority_root)
    verify_bound_authority_bytes(authority, authority_root)
    verify_exact_authority_delta(authority, authority_root)
    result: dict[str, Any] = {
        "authority_schema": authority["schema"],
        "authority_status": authority["status"],
        "authority_paths": len(authority["scope"]["authority_write_scope"]),
        "token_consumed": authority["run_token"]["token_consumed"],
        "verification": "passed",
    }
    if args.command == "combined":
        if args.candidate_root is None:
            parser.error("--candidate-root is required for combined")
        candidate_root = args.candidate_root.absolute()
        verify_candidate_cohort(authority, candidate_root)
        verify_exact_candidate_delta(authority, candidate_root)
        verify_preserved_failure_ledger(authority, candidate_root)
        verify_new_paths_absent(authority, candidate_root)
        result["candidate_paths"] = len(authority["scope"]["combined_preflight_candidate_scope"])
        result["preserved_ledger_sha256"] = authority["preserved_v1_ledger"]["sha256"]
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
