from __future__ import annotations

from typing import Any

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.contracts.reference.lifecycle import fold_lifecycle


def _transition(
    logical_id: str,
    state: str,
    event_at_us: int,
    source_order: int,
) -> dict[str, Any]:
    return {
        "basis": "observed_transition",
        "coordinate": {
            "source_order": source_order,
            "event_at_us": event_at_us,
        },
        "event_at_us": event_at_us,
        "event_kind_order": 1,
        "logical_id": logical_id,
        "source_order": ["synthetic-lifecycle", source_order],
        "state": state,
    }


def build_lifecycle_oracle() -> dict[str, Any]:
    """Return closed lifecycle cases independent of arrival or SQL order."""

    tool = semantic_id("tool", ["lifecycle-oracle"])
    in_order = [
        _transition(tool, "running", 1_000_000, 1),
        _transition(tool, "succeeded", 2_000_000, 2),
    ]
    late_arrival = [in_order[1], in_order[0]]
    uninterrupted = fold_lifecycle(in_order)
    restarted = fold_lifecycle([in_order[0], in_order[1]])
    return {
        "states_covered": [
            "pending",
            "running",
            "succeeded",
            "failed",
            "cancelled",
            "rolled_back",
            "open",
            "unknown",
        ],
        "late_terminal": {
            "in_order": uninterrupted,
            "late_arrival": fold_lifecycle(late_arrival),
            "same_fold_as_in_order": fold_lifecycle(late_arrival) == uninterrupted,
        },
        "crash_restart": {
            "uninterrupted": uninterrupted,
            "restarted": restarted,
            "same_fold_as_uninterrupted": restarted == uninterrupted,
        },
        "turn_completion": {
            "observed_terminal": "succeeded",
            "failed": "failed",
            "cancelled": "cancelled",
            "open_tail": "open",
            "end_of_file_is_completion": False,
        },
        "tool_separation": {
            "write_intent": True,
            "tool_state": "succeeded",
            "observed_mutation": True,
            "preceding_tool_count": 2,
            "causal_attribution": False,
        },
    }
