#!/usr/bin/env python3
"""Fail-closed CK-07R1 exactly-once consuming-boundary verifier."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.ck07r1_terminal_failure_correction import (
    TerminalCorrectionError,
    bound_authority_digest_matches,
)

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = (
    "docs/decisions/evidence/ck07r1a0/"
    "lifecycle-consuming-boundary-authority-v1.json"
)
SCHEMA_PATH = AUTHORITY_PATH.removesuffix(".json") + ".schema.json"
MINIMUM_CAPACITY_BYTES = 10 * 1024**3


class ConsumingBoundaryError(RuntimeError):
    """The observed state is not authorized to cross the consuming boundary."""


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConsumingBoundaryError(
            f"cannot verify git {' '.join(arguments)}"
        ) from exc
    return result.stdout.strip()


def _git_paths(root: Path, *arguments: str) -> set[str]:
    return set(filter(None, _git(root, *arguments).splitlines()))


def verify_current_exact_main(
    root: Path,
    *,
    observed_head: str | None = None,
    observed_tracking_main: str | None = None,
    observed_remote_main: str | None = None,
) -> str:
    """Require HEAD to equal both fetched and live origin/main."""

    head = observed_head or _git(root, "rev-parse", "HEAD")
    tracking = observed_tracking_main or _git(
        root, "rev-parse", "refs/remotes/origin/main"
    )
    if observed_remote_main is None:
        remote = _git(root, "ls-remote", "origin", "refs/heads/main")
        fields = remote.split()
        if len(fields) != 2 or fields[1] != "refs/heads/main":
            raise ConsumingBoundaryError("live origin/main response malformed")
        observed_remote_main = fields[0]
    if head != tracking or head != observed_remote_main:
        raise ConsumingBoundaryError(
            "consuming boundary requires fresh exact origin/main"
        )
    return head


def load_authority(root: Path = ROOT) -> dict[str, Any]:
    authority = json.loads((root / AUTHORITY_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    return authority


def verify_bound_authority_bytes(
    authority: Mapping[str, Any], root: Path = ROOT
) -> None:
    records = authority.get("immutable_authorities")
    if not isinstance(records, list):
        raise ConsumingBoundaryError("immutable authority records missing")
    for record in records:
        if not isinstance(record, Mapping):
            raise ConsumingBoundaryError("immutable authority record malformed")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ConsumingBoundaryError("immutable authority identity malformed")
        try:
            matches = bound_authority_digest_matches(root, relative, expected)
        except TerminalCorrectionError as exc:
            raise ConsumingBoundaryError(str(exc)) from exc
        if not matches:
            raise ConsumingBoundaryError(f"bound authority bytes drifted: {relative}")


def verify_candidate_cohort(
    authority: Mapping[str, Any], candidate_root: Path
) -> None:
    records = authority.get("candidate_cohort")
    if not isinstance(records, list) or len(records) != 3:
        raise ConsumingBoundaryError("candidate cohort must contain exactly three paths")
    observed: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ConsumingBoundaryError("candidate cohort record malformed")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ConsumingBoundaryError("candidate identity malformed")
        if relative in observed:
            raise ConsumingBoundaryError(f"duplicate candidate path: {relative}")
        observed.add(relative)
        if _sha256(candidate_root / relative) != expected:
            raise ConsumingBoundaryError(
                f"candidate cohort identity mismatch: {relative}"
            )


def observed_worktree_delta(root: Path) -> set[str]:
    return (
        _git_paths(root, "diff", "--name-only", "--no-renames", "HEAD")
        | _git_paths(root, "diff", "--cached", "--name-only", "--no-renames", "HEAD")
        | _git_paths(root, "ls-files", "--others", "--exclude-standard")
    )


def verify_exact_candidate_delta(
    authority: Mapping[str, Any],
    candidate_root: Path,
    *,
    observed: set[str] | None = None,
) -> None:
    scope = authority.get("scope")
    if not isinstance(scope, Mapping):
        raise ConsumingBoundaryError("authority scope missing")
    expected = scope.get("combined_preflight_candidate_scope")
    if not isinstance(expected, list) or not all(
        isinstance(path, str) for path in expected
    ):
        raise ConsumingBoundaryError("candidate scope malformed")
    actual = observed_worktree_delta(candidate_root) if observed is None else observed
    if actual != set(expected):
        raise ConsumingBoundaryError(
            "exact candidate Git delta mismatch; "
            f"missing={sorted(set(expected) - actual)!r}; "
            f"extra={sorted(actual - set(expected))!r}"
        )


def verify_exact_authority_delta(
    authority: Mapping[str, Any],
    authority_root: Path,
    *,
    committed: bool,
    observed: set[str] | None = None,
) -> None:
    scope = authority.get("scope")
    if not isinstance(scope, Mapping):
        raise ConsumingBoundaryError("authority scope missing")
    expected = scope.get("authority_write_scope")
    if not isinstance(expected, list) or not all(
        isinstance(path, str) for path in expected
    ):
        raise ConsumingBoundaryError("authority write scope malformed")
    if observed is None:
        if committed:
            base = authority.get("authority_base_sha")
            if not isinstance(base, str):
                raise ConsumingBoundaryError("authority base malformed")
            if subprocess.run(
                ("git", "merge-base", "--is-ancestor", base, "HEAD"),
                cwd=authority_root,
                check=False,
                capture_output=True,
            ).returncode:
                raise ConsumingBoundaryError("authority base is not an ancestor")
            actual = _git_paths(
                authority_root,
                "diff",
                "--name-only",
                "--no-renames",
                f"{base}...HEAD",
            )
            verify_current_exact_main(authority_root)
        else:
            actual = observed_worktree_delta(authority_root)
    else:
        actual = observed
    if actual != set(expected):
        raise ConsumingBoundaryError(
            "exact authority Git delta mismatch; "
            f"missing={sorted(set(expected) - actual)!r}; "
            f"extra={sorted(actual - set(expected))!r}"
        )


def verify_combined_preflight(
    authority_root: Path,
    candidate_root: Path,
    *,
    authority_committed: bool,
) -> dict[str, Any]:
    authority = load_authority(authority_root)
    verify_bound_authority_bytes(authority, authority_root)
    verify_exact_authority_delta(
        authority, authority_root, committed=authority_committed
    )
    verify_candidate_cohort(authority, candidate_root)
    verify_exact_candidate_delta(authority, candidate_root)
    worker = authority["worker"]
    if _git(candidate_root, "rev-parse", "HEAD") != worker[
        "prequalification_base_sha"
    ]:
        raise ConsumingBoundaryError("worker prequalification base drifted")
    return {
        "authority_schema": authority["schema"],
        "authority_status": authority["status"],
        "authority_base_sha": authority["authority_base_sha"],
        "candidate_paths": [record["path"] for record in authority["candidate_cohort"]],
        "candidate_sha256": {
            record["path"]: record["sha256"] for record in authority["candidate_cohort"]
        },
        "launch_authorized_in_authority_task": False,
        "token_consumed": False,
        "output_artifacts_created": False,
        "verification": "passed",
    }


def verify_post_merge_candidate_head(
    authority: Mapping[str, Any], candidate_root: Path
) -> str:
    """Require the frozen launch lane at exact merged main above its proof base."""

    worker = authority.get("worker")
    if not isinstance(worker, Mapping):
        raise ConsumingBoundaryError("worker binding missing")
    base = worker.get("prequalification_base_sha")
    if not isinstance(base, str) or len(base) != 40:
        raise ConsumingBoundaryError("prequalification base malformed")
    head = verify_current_exact_main(candidate_root)
    if head == base:
        raise ConsumingBoundaryError(
            "consuming authority is not present in candidate HEAD"
        )
    result = subprocess.run(
        ("git", "merge-base", "--is-ancestor", base, head),
        cwd=candidate_root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise ConsumingBoundaryError(
            "prequalification base is not an ancestor of exact merged main"
        )
    return head


def evaluate_prelaunch(
    authority: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {
        "cwd": authority["worker"]["frozen_cwd"],
        "argv": authority["launch_contract"]["argv"],
        "environment": authority["launch_contract"]["environment"]["required"],
        "interpreter": (
            authority["worker"]["frozen_cwd"] + "/.venv/bin/python"
        ),
        "venv_prefix": authority["worker"]["frozen_cwd"] + "/.venv",
        "prequalification_base_sha": authority["worker"][
            "prequalification_base_sha"
        ],
        "candidate_head_transition": (
            "non_destructive_fast_forward_to_exact_merged_main"
        ),
        "matching_processes": [],
        "output_paths_present": [],
        "receipt": "absent",
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "authority_integrity": "passed",
        "candidate_cohort": "passed",
        "candidate_delta": "passed",
        "synthetic_fixture": True,
    }
    for field, value in expected.items():
        if observation.get(field) != value:
            raise ConsumingBoundaryError(f"prelaunch gate failed: {field}")
    capacity = observation.get("disk_available_bytes")
    if not isinstance(capacity, int) or capacity < MINIMUM_CAPACITY_BYTES:
        raise ConsumingBoundaryError("prelaunch gate failed: disk_available_bytes")
    forbidden = authority["launch_contract"]["environment"]["forbidden"]
    if any(
        name in observation.get("environment_present", {})
        for name in forbidden
        if name != "real Codex log or database paths"
    ):
        raise ConsumingBoundaryError("prelaunch gate failed: forbidden environment")
    if observation.get("live_or_real_data") is not False:
        raise ConsumingBoundaryError("prelaunch gate failed: live_or_real_data")
    return {
        "decision": "launch_authorized_once",
        "run_token_id": authority["run_token"]["id"],
        "maximum_new_end_to_end_runs": 1,
        "consume_only_after_successful_child_handshake": True,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }


def _normalized_argv(argv: Sequence[str], cwd: Path) -> tuple[str, ...]:
    values = list(argv)
    indexes = {0, 1}
    if "--output" in values:
        indexes.add(values.index("--output") + 1)
    return tuple(
        str((cwd / value).absolute()) if index in indexes else value
        for index, value in enumerate(values)
    )


def _process_cwd(pid: int) -> Path | None:
    command = shutil.which("lsof") or "/usr/sbin/lsof"
    result = subprocess.run(
        (command, "-a", "-p", str(pid), "-d", "cwd", "-Fn"),
        check=False,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:]).resolve()
    return None


def _matching_processes(argv: Sequence[str], cwd: Path) -> list[dict[str, Any]]:
    expected = _normalized_argv(argv, cwd)
    owner = getpass.getuser()
    result = subprocess.run(
        ("ps", "-ww", "-axo", "pid=,user=,command="),
        check=True,
        capture_output=True,
        text=True,
    )
    matches: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid_text, user, command = parts
        if user != owner:
            continue
        try:
            pid = int(pid_text)
            process_argv = shlex.split(command)
        except ValueError:
            continue
        if pid == os.getpid() or _normalized_argv(process_argv, cwd) != expected:
            continue
        process_cwd = _process_cwd(pid)
        if process_cwd is None:
            raise ConsumingBoundaryError(
                f"cannot verify cwd of matching process {pid}"
            )
        if process_cwd == cwd:
            matches.append({"pid": pid, "owner": user, "cwd": str(process_cwd)})
    return matches


def observe_live_prelaunch(
    authority_root: Path, candidate_root: Path
) -> dict[str, Any]:
    authority = load_authority(authority_root)
    verify_bound_authority_bytes(authority, authority_root)
    verify_exact_authority_delta(authority, authority_root, committed=True)
    verify_candidate_cohort(authority, candidate_root)
    verify_exact_candidate_delta(authority, candidate_root)
    verify_post_merge_candidate_head(authority, candidate_root)

    cwd = candidate_root.absolute()
    required = authority["launch_contract"]["environment"]["required"]
    exclusive = authority["launch_contract"]["exclusive_paths"]
    output_paths_present = [
        relative for relative in exclusive.values() if (cwd / relative).exists()
    ]
    output_parent = (cwd / exclusive["output"]).parent
    if not output_parent.is_dir():
        raise ConsumingBoundaryError("prelaunch gate failed: output parent absent")
    observation = {
        "cwd": str(cwd),
        "argv": authority["launch_contract"]["argv"],
        "environment": {name: os.environ.get(name) for name in required},
        "environment_present": dict(os.environ),
        "interpreter": str(Path(sys.executable).absolute()),
        "venv_prefix": str(Path(sys.prefix).absolute()),
        "prequalification_base_sha": authority["worker"][
            "prequalification_base_sha"
        ],
        "candidate_head_transition": (
            "non_destructive_fast_forward_to_exact_merged_main"
        ),
        "matching_processes": _matching_processes(
            authority["launch_contract"]["argv"], cwd
        ),
        "output_paths_present": output_paths_present,
        "receipt": "absent",
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "authority_integrity": "passed",
        "candidate_cohort": "passed",
        "candidate_delta": "passed",
        "synthetic_fixture": True,
        "live_or_real_data": False,
        "disk_available_bytes": shutil.disk_usage(cwd).free,
    }
    return evaluate_prelaunch(authority, observation)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    combined = subparsers.add_parser("combined")
    combined.add_argument("--authority-root", type=Path, required=True)
    combined.add_argument("--candidate-root", type=Path, required=True)
    combined.add_argument("--authority-committed", action="store_true")
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--authority-root", type=Path, required=True)
    preflight.add_argument("--candidate-root", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "combined":
        result = verify_combined_preflight(
            arguments.authority_root,
            arguments.candidate_root,
            authority_committed=arguments.authority_committed,
        )
    else:
        result = observe_live_prelaunch(
            arguments.authority_root,
            arguments.candidate_root,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
