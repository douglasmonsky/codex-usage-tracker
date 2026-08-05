"""Append-only lifecycle observations and their deterministic current fold."""

from __future__ import annotations

import sqlite3

from ..domain.models import LifecycleFold, LifecycleTransition

TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "rolled_back"})
_ACTIVE_STATES = frozenset({"pending", "open", "running"})
_ALLOWED_STATES = frozenset({"unknown", *_ACTIVE_STATES, *TERMINAL_STATES})
_ALLOWED_AFTER = {
    "unknown": _ALLOWED_STATES,
    "pending": frozenset({"pending", "open", "running", *TERMINAL_STATES}),
    "open": frozenset({"open", "running", *TERMINAL_STATES}),
    "running": frozenset({"running", *TERMINAL_STATES}),
    **{state: frozenset({state}) for state in TERMINAL_STATES},
}


class LifecycleFoldError(ValueError):
    """Lifecycle observations cannot produce one valid current state."""


def lifecycle_order_key(transition: LifecycleTransition) -> tuple[object, ...]:
    """Return the semantic lifecycle order; timestamps are evidence, not state order.

    An adapter may observe a terminal record whose clock precedes the start
    record.  ``transition_version`` remains the semantic sequence in that
    case, while the observed timestamps are retained for duration validation.
    """

    return (
        transition.transition_version,
        transition.transition_at_us is None,
        0 if transition.transition_at_us is None else transition.transition_at_us,
        transition.source_rank,
        transition.source_order,
        transition.event_kind_order,
        transition.entity_logical_id,
        transition.transition_rank,
    )


def fold_lifecycle(transitions: tuple[LifecycleTransition, ...]) -> LifecycleFold:
    """Fold by evidence order so a late-arriving earlier observation is stable."""

    if not transitions:
        raise LifecycleFoldError("lifecycle requires at least one transition")
    identities = {transition.entity_logical_id for transition in transitions}
    if len(identities) != 1:
        raise LifecycleFoldError("lifecycle transitions mix logical identities")
    kinds = {transition.entity_kind for transition in transitions}
    if len(kinds) != 1:
        raise LifecycleFoldError("lifecycle transitions mix entity kinds")
    ordered = sorted(transitions, key=lifecycle_order_key)
    state = "unknown"
    basis = "unknown"
    start: LifecycleTransition | None = None
    terminal: LifecycleTransition | None = None
    for transition in ordered:
        next_state = transition.lifecycle_state
        if next_state not in _ALLOWED_STATES:
            raise LifecycleFoldError(f"unknown lifecycle state {next_state}")
        if next_state not in _ALLOWED_AFTER[state]:
            raise LifecycleFoldError(f"invalid lifecycle transition {state} -> {next_state}")
        state = next_state
        basis = transition.state_basis
        if start is None and next_state in _ACTIVE_STATES:
            start = transition
        if next_state in TERMINAL_STATES:
            terminal = transition

    duration_us: int | None = None
    diagnostic: str | None = None
    if (
        start is not None
        and terminal is not None
        and start.transition_at_us is not None
        and terminal.transition_at_us is not None
    ):
        if terminal.transition_at_us >= start.transition_at_us:
            duration_us = terminal.transition_at_us - start.transition_at_us
        else:
            diagnostic = "negative_duration"
    return LifecycleFold(
        entity_logical_id=next(iter(identities)),
        lifecycle_state=state,
        state_basis=basis,
        transition_version=max(item.transition_version for item in transitions),
        start_at_us=None if start is None else start.transition_at_us,
        start_occurrence_id=None if start is None else start.occurrence_id,
        terminal_at_us=None if terminal is None else terminal.transition_at_us,
        terminal_occurrence_id=None if terminal is None else terminal.occurrence_id,
        observed_duration_us=duration_us,
        duration_diagnostic=diagnostic,
        terminal_error_category=(None if terminal is None else terminal.terminal_error_category),
        transition_count=len(ordered),
    )


class LifecycleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def append(self, transition: LifecycleTransition) -> LifecycleFold:
        """Append one observation, rejecting conflicting terminal histories."""

        self._connection.execute("SAVEPOINT append_lifecycle_transition")
        try:
            self._connection.execute(
                """
                INSERT INTO lifecycle_transitions (
                  transition_id, entity_logical_id, entity_kind, lifecycle_state,
                  state_basis, transition_version, transition_at_us, source_rank,
                  source_order, event_kind_order, transition_rank, occurrence_id,
                  terminal_error_category, measurement_mask,
                  first_seen_publication_id, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.transition_id,
                    transition.entity_logical_id,
                    transition.entity_kind,
                    transition.lifecycle_state,
                    transition.state_basis,
                    transition.transition_version,
                    transition.transition_at_us,
                    transition.source_rank,
                    transition.source_order,
                    transition.event_kind_order,
                    transition.transition_rank,
                    transition.occurrence_id,
                    transition.terminal_error_category,
                    transition.measurement_mask,
                    transition.first_seen_publication_id,
                    transition.session_id,
                ),
            )
            folded = self.fold(transition.entity_logical_id)
            self._connection.execute("RELEASE append_lifecycle_transition")
            return folded
        except Exception:
            self._connection.execute("ROLLBACK TO append_lifecycle_transition")
            self._connection.execute("RELEASE append_lifecycle_transition")
            raise

    add = append

    def transitions_for(self, entity_logical_id: str) -> tuple[LifecycleTransition, ...]:
        rows = self._connection.execute(
            """
            SELECT transition_id, entity_logical_id, entity_kind, lifecycle_state,
                   state_basis, transition_version, transition_at_us, source_rank,
                   source_order, event_kind_order, transition_rank, occurrence_id,
                   terminal_error_category, measurement_mask,
                   first_seen_publication_id, session_id
            FROM lifecycle_transitions
            WHERE entity_logical_id = ?
            ORDER BY transition_version, (transition_at_us IS NULL),
                     transition_at_us, source_rank, source_order,
                     event_kind_order, entity_logical_id, transition_rank
            """,
            (entity_logical_id,),
        )
        return tuple(LifecycleTransition(*row) for row in rows)

    def fold(self, entity_logical_id: str) -> LifecycleFold:
        return fold_lifecycle(self.transitions_for(entity_logical_id))
