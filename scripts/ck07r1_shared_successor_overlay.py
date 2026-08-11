"""Fail-closed verifier for the versioned CK-07R1 shared-successor overlay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = (
    "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json"
)
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
            raise SharedSuccessorOverlayError(f"{section} is missing")
        for record in records:
            if not isinstance(record, Mapping):
                raise SharedSuccessorOverlayError(f"{section} record is malformed")
            for path_key, digest_key in (
                ("path", "sha256"),
                ("schema_path", "schema_sha256"),
            ):
                relative = record.get(path_key)
                expected = record.get(digest_key)
                if not isinstance(relative, str) or not isinstance(expected, str):
                    raise SharedSuccessorOverlayError(
                        f"{section} byte binding is malformed"
                    )
                actual = sha256_path(root, relative)
                if actual != expected:
                    raise SharedSuccessorOverlayError(
                        f"bound authority digest drift: {relative}"
                    )


def observed_candidate_artifacts(
    authority: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, str | None]:
    """Read exactly the three paths owned by the predecessor/successor fold."""

    states = authority.get("states")
    if not isinstance(states, Mapping):
        raise SharedSuccessorOverlayError("states are missing")
    successor = states.get("successor")
    if not isinstance(successor, Mapping):
        raise SharedSuccessorOverlayError("successor state is missing")
    artifacts = successor.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise SharedSuccessorOverlayError("successor cohort must contain exactly three paths")

    observed: dict[str, str | None] = {}
    for record in artifacts:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise SharedSuccessorOverlayError("successor artifact is malformed")
        relative = str(record["path"])
        if relative in observed:
            raise SharedSuccessorOverlayError(f"duplicate successor path: {relative}")
        observed[relative] = sha256_path(root, relative)
    return observed


def _expected_state(
    state: Mapping[str, Any],
) -> dict[str, str | None]:
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise SharedSuccessorOverlayError("authorized state must contain exactly three paths")
    expected: dict[str, str | None] = {}
    for record in artifacts:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise SharedSuccessorOverlayError("authorized artifact is malformed")
        relative = str(record["path"])
        if relative in expected:
            raise SharedSuccessorOverlayError(f"duplicate authorized path: {relative}")
        presence = record.get("presence")
        if presence == "absent":
            expected[relative] = None
        elif presence == "required" and isinstance(record.get("sha256"), str):
            expected[relative] = str(record["sha256"])
        else:
            raise SharedSuccessorOverlayError(
                f"invalid presence contract for {relative}"
            )
    return expected


def classify_observed_state(
    authority: Mapping[str, Any],
    observed: Mapping[str, str | None],
) -> str:
    """Fold exact path presence and digests into one authorized state."""

    states = authority.get("states")
    if not isinstance(states, Mapping):
        raise SharedSuccessorOverlayError("states are missing")
    predecessor = states.get("predecessor")
    successor = states.get("successor")
    if not isinstance(predecessor, Mapping) or not isinstance(successor, Mapping):
        raise SharedSuccessorOverlayError("authorized states are malformed")

    predecessor_expected = _expected_state(predecessor)
    successor_expected = _expected_state(successor)
    if set(observed) != set(successor_expected):
        raise SharedSuccessorOverlayError("candidate cohort paths are missing or extra")
    if dict(observed) == predecessor_expected:
        return str(predecessor["name"])
    if dict(observed) == successor_expected:
        return str(successor["name"])
    raise SharedSuccessorOverlayError(
        "mixed, partial, historical, or unbound CK-07R1 cohort"
    )


def verify_shared_successor_overlay(root: Path = ROOT) -> tuple[dict[str, Any], str]:
    """Validate authority bytes and classify the live workspace atomically."""

    authority = load_overlay(root)
    verify_bound_authority_bytes(authority, root)
    state = classify_observed_state(
        authority,
        observed_candidate_artifacts(authority, root),
    )
    return authority, state


def overlay_changed_path_allowance(
    authority: Mapping[str, Any],
    state: str,
) -> set[str]:
    """Return the exact overlay paths allowed for the classified state."""

    scope = authority.get("scope")
    if not isinstance(scope, Mapping):
        raise SharedSuccessorOverlayError("overlay scope is missing")
    authority_paths = scope.get("authority_write_scope")
    candidate_paths = scope.get("combined_preflight_candidate_scope")
    if not isinstance(authority_paths, list) or not all(
        isinstance(path, str) for path in authority_paths
    ):
        raise SharedSuccessorOverlayError("authority write scope is malformed")
    allowed = set(authority_paths)
    if state == "worker_prequalification":
        if not isinstance(candidate_paths, list) or not all(
            isinstance(path, str) for path in candidate_paths
        ):
            raise SharedSuccessorOverlayError("candidate scope is malformed")
        allowed.update(candidate_paths)
    elif state != "authority_main":
        raise SharedSuccessorOverlayError(f"unrecognized overlay state: {state}")
    return allowed
