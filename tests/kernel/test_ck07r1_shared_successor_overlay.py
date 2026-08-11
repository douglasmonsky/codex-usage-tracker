from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.ck07r1_shared_successor_overlay import (
    ROOT,
    SCHEMA_PATH,
    SharedSuccessorOverlayError,
    classify_observed_state,
    load_overlay,
    observed_candidate_artifacts,
    overlay_changed_path_allowance,
    sha256_path,
    verify_bound_authority_bytes,
    verify_shared_successor_overlay,
)


def _state_observed(authority: dict, state_name: str) -> dict[str, str | None]:
    state = authority["states"][state_name]
    return {
        item["path"]: None if item["presence"] == "absent" else item["sha256"]
        for item in state["artifacts"]
    }


def test_overlay_is_exact_and_live_state_is_authorized() -> None:
    authority, state = verify_shared_successor_overlay()

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


def test_overlay_schema_rejects_status_token_launch_and_scope_weakening() -> None:
    authority = load_overlay()
    schema = __import__("json").loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    mutations = (
        lambda value: value.__setitem__("status", "final_accepted"),
        lambda value: value["states"]["successor"].__setitem__(
            "launch_authorized", True
        ),
        lambda value: value["non_consuming_invariants"].__setitem__(
            "token_consumed", True
        ),
        lambda value: value["non_consuming_invariants"].__setitem__(
            "receipt", "fabricated"
        ),
        lambda value: value["states"]["successor"]["artifacts"].pop(),
        lambda value: value["states"]["successor"]["artifacts"].append(
            {"path": "extra.py", "sha256": "0" * 64, "presence": "required"}
        ),
        lambda value: value["scope"]["authority_write_scope"].append(
            "src/codex_usage_tracker/agent_kernel/publication/writer.py"
        ),
        lambda value: value["scope"]["combined_preflight_candidate_scope"].pop(),
    )
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(validator.iter_errors(changed))


def test_overlay_rejects_any_immutable_v1_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_overlay_scope_is_state_specific_and_cannot_hide_writer_changes() -> None:
    authority = load_overlay()
    predecessor = overlay_changed_path_allowance(authority, "authority_main")
    successor = overlay_changed_path_allowance(authority, "worker_prequalification")
    candidate = set(authority["scope"]["combined_preflight_candidate_scope"])

    assert successor == predecessor | candidate
    assert candidate.isdisjoint(predecessor)
    assert "src/codex_usage_tracker/agent_kernel/publication/writer.py" not in successor
