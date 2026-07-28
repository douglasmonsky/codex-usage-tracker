from __future__ import annotations

from collections import defaultdict
from typing import Any

from tests.agent_kernel.contracts.reference.time import event_order_key

_TERMINAL_STATES = frozenset(
    {"succeeded", "failed", "cancelled", "rolled_back"}
)
_ALLOWED = {
    "unknown": frozenset(
        {"unknown", "pending", "open", "running", *_TERMINAL_STATES}
    ),
    "pending": frozenset({"pending", "open", "running", *_TERMINAL_STATES}),
    "open": frozenset({"open", "running", *_TERMINAL_STATES}),
    "running": frozenset({"running", *_TERMINAL_STATES}),
    "succeeded": frozenset({"succeeded"}),
    "failed": frozenset({"failed"}),
    "cancelled": frozenset({"cancelled"}),
    "rolled_back": frozenset({"rolled_back"}),
}


class LifecycleContractError(ValueError):
    """Raised for an invalid lifecycle fold or session hierarchy."""


def fold_lifecycle(transitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold append-only observations by semantic event order, not arrival order."""

    if not transitions:
        raise LifecycleContractError("lifecycle requires at least one transition")
    logical_ids = {transition["logical_id"] for transition in transitions}
    if len(logical_ids) != 1:
        raise LifecycleContractError("lifecycle transitions mix logical identities")
    ordered = sorted(transitions, key=event_order_key)
    state = "unknown"
    start = None
    start_at_us: int | None = None
    terminal = None
    terminal_at_us: int | None = None
    basis = "unknown"
    for transition in ordered:
        next_state = transition["state"]
        if next_state not in _ALLOWED:
            raise LifecycleContractError(f"unknown lifecycle state {next_state}")
        if next_state not in _ALLOWED[state]:
            raise LifecycleContractError(
                f"invalid lifecycle transition {state} -> {next_state}"
            )
        state = next_state
        basis = transition["basis"]
        if start is None and next_state in {"pending", "open", "running"}:
            start = transition["coordinate"]
            start_at_us = transition.get("event_at_us")
        if next_state in _TERMINAL_STATES:
            terminal = transition["coordinate"]
            terminal_at_us = transition.get("event_at_us")
    duration_us = None
    diagnostic = None
    if (
        start is not None
        and terminal is not None
        and start_at_us is not None
        and terminal_at_us is not None
    ):
        if terminal_at_us >= start_at_us:
            duration_us = terminal_at_us - start_at_us
        else:
            diagnostic = "negative_duration"
    return {
        "logical_id": next(iter(logical_ids)),
        "state": state,
        "state_basis": basis,
        "start_coordinate": start,
        "terminal_coordinate": terminal,
        "observed_duration_us": duration_us,
        "duration_diagnostic": diagnostic,
        "transition_count": len(ordered),
    }


def _assert_acyclic(parent_by_session: dict[str, str | None]) -> None:
    for origin in parent_by_session:
        seen: set[str] = set()
        current: str | None = origin
        while current is not None:
            if current in seen:
                raise LifecycleContractError("session hierarchy contains a cycle")
            seen.add(current)
            current = parent_by_session.get(current)


def hierarchy_usage(
    session_id: str,
    parent_by_session: dict[str, str | None],
    exclusive_usage: dict[str, int],
) -> dict[str, int]:
    """Reconcile direct, descendant-exclusive, and family-inclusive scopes."""

    _assert_acyclic(parent_by_session)
    children: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_by_session.items():
        if parent is not None:
            children[parent].append(child)
    descendants: list[str] = []
    stack = list(children.get(session_id, []))
    while stack:
        child = stack.pop()
        descendants.append(child)
        stack.extend(children.get(child, []))
    parent_exclusive = exclusive_usage.get(session_id, 0)
    descendant_exclusive = sum(exclusive_usage.get(child, 0) for child in descendants)
    return {
        "parent_exclusive": parent_exclusive,
        "descendant_exclusive": descendant_exclusive,
        "family_inclusive": parent_exclusive + descendant_exclusive,
        "child_count": len(children.get(session_id, [])),
        "descendant_count": len(descendants),
    }
