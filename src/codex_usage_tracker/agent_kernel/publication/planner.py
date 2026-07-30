"""Lock-free classification and bounds for CK-07 refresh operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from enum import Enum
from typing import TYPE_CHECKING, Generic, TypeVar

from ..adapters.contracts import SourceState
from ..domain.valuation import ValuationDirtyInterval

if TYPE_CHECKING:
    from ..adapters.codex_jsonl.canonicalize import ProposedChangeSet


class OperationClass(str, Enum):
    NO_CHANGE = "no_change"
    APPEND_SAFE_SMALL = "append_safe_small"
    APPEND_SAFE_LARGE = "append_safe_large"
    VALUATION_ONLY = "valuation_only"
    SOURCE_REPLACE = "source_replace"
    RECANONICALIZE = "recanonicalize"
    SCHEMA_UPGRADE = "schema_upgrade"
    PROJECTION_UPGRADE = "projection_upgrade"
    HISTORY_EXPAND = "history_expand"


@dataclass(frozen=True, slots=True)
class TailLimits:
    """Proven-small limits checked before opening the analytical writer."""

    selected_bytes: int = 8 * 1024 * 1024
    selected_records: int = 32
    observations: int = 12_000
    occurrences: int = 12_000
    affected_sessions: int = 2_000
    affected_turns: int = 4_000
    affected_resources: int = 4_000
    affected_allowance_cycles: int = 512
    dirty_keys: int = 16_000
    projection_rows: int = 16_000
    expected_wal_bytes: int = 16 * 1024 * 1024
    planning_staleness_us: int = 5_000_000
    model_call_tail_rows: int = 32_000

    def __post_init__(self) -> None:
        if any(getattr(self, item.name) <= 0 for item in fields(self)):
            raise ValueError("small-tail limits must be positive")


@dataclass(frozen=True, slots=True)
class ChangeEstimate:
    selected_bytes: int
    selected_records: int
    observations: int
    occurrences: int
    affected_sessions: int
    affected_turns: int
    affected_resources: int
    affected_allowance_cycles: int
    dirty_keys: int
    projection_rows: int
    expected_wal_bytes: int
    model_calls_inserted: int

    def __post_init__(self) -> None:
        if any(getattr(self, item.name) < 0 for item in fields(self)):
            raise ValueError("change estimates must be nonnegative")


@dataclass(frozen=True, slots=True)
class RefreshIntent:
    parent_publication_id: str | None
    parent_observed_at_us: int
    planned_at_us: int
    history_preset: str
    current_history_preset: str | None = None
    rate_card_changed: bool = False
    schema_changed: bool = False
    projection_registry_changed: bool = False
    adapter_changed: bool = False
    identity_changed: bool = False
    normalization_changed: bool = False
    canonical_owner_changed: bool = False
    watcher_dirty_hint_count: int = 0
    periodic_reconciliation_due: bool = False
    current_tail_rows: int = 0
    valuation_dirty_intervals: tuple[ValuationDirtyInterval, ...] = ()

    def __post_init__(self) -> None:
        if self.parent_observed_at_us > self.planned_at_us:
            raise ValueError("planning clock precedes parent observation")
        if self.watcher_dirty_hint_count < 0 or self.current_tail_rows < 0:
            raise ValueError("refresh counters must be nonnegative")
        if self.valuation_dirty_intervals and not self.rate_card_changed:
            raise ValueError("valuation dirty intervals require a rate-card change")


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    operation_class: OperationClass
    parent_publication_id: str | None
    estimate: ChangeEstimate
    reasons: tuple[str, ...]
    analytical_write_required: bool
    valuation_dirty_intervals: tuple[ValuationDirtyInterval, ...] = ()

    @property
    def is_small(self) -> bool:
        return self.operation_class in {
            OperationClass.APPEND_SAFE_SMALL,
            OperationClass.VALUATION_ONLY,
        }


BoundaryT = TypeVar("BoundaryT")


@dataclass(frozen=True, slots=True)
class CatchupResult(Generic[BoundaryT]):
    boundary: BoundaryT
    passes: int
    selected_bytes: int
    selected_records: int
    tail_pending: bool


def bounded_moving_tail_catchup(
    initial_boundary: BoundaryT,
    *,
    capture: Callable[[], BoundaryT],
    apply: Callable[[BoundaryT, BoundaryT, int, int], tuple[int, int]],
    maximum_passes: int = 2,
    maximum_bytes: int,
    maximum_records: int,
) -> CatchupResult[BoundaryT]:
    """Apply at most two host-owned catch-up passes to one captured boundary.

    ``apply`` receives the previous/current boundaries and remaining byte and
    record budgets. It must return the accepted bytes and records. A boundary
    that continues moving after the pass/budget limit is disclosed as pending.
    """

    if maximum_passes not in (1, 2):
        raise ValueError("moving-tail catch-up permits one or two passes")
    if maximum_bytes < 0 or maximum_records < 0:
        raise ValueError("moving-tail budgets must be nonnegative")
    previous = initial_boundary
    total_bytes = 0
    total_records = 0
    passes = 0
    tail_pending = False
    for _ in range(maximum_passes):
        current = capture()
        if current == previous:
            return CatchupResult(current, passes, total_bytes, total_records, tail_pending=False)
        remaining_bytes = maximum_bytes - total_bytes
        remaining_records = maximum_records - total_records
        if remaining_bytes <= 0 or remaining_records <= 0:
            tail_pending = True
            break
        accepted_bytes, accepted_records = apply(
            previous,
            current,
            remaining_bytes,
            remaining_records,
        )
        if (
            accepted_bytes < 0
            or accepted_records < 0
            or accepted_bytes > remaining_bytes
            or accepted_records > remaining_records
        ):
            raise ValueError("catch-up callback exceeded the remaining budget")
        total_bytes += accepted_bytes
        total_records += accepted_records
        passes += 1
        previous = current
    else:
        tail_pending = capture() != previous
    return CatchupResult(
        previous,
        passes,
        total_bytes,
        total_records,
        tail_pending=tail_pending,
    )


def reconciliation_required(
    *,
    dirty_hint_count: int,
    last_reconciled_at_us: int | None,
    observed_at_us: int,
    maximum_interval_us: int,
) -> bool:
    """Watcher hints accelerate refresh; this periodic bound owns correctness."""

    if dirty_hint_count < 0 or maximum_interval_us <= 0:
        raise ValueError("reconciliation bounds must be positive")
    if dirty_hint_count:
        return True
    if last_reconciled_at_us is None:
        return True
    if observed_at_us < last_reconciled_at_us:
        raise ValueError("reconciliation clock moved backwards")
    return observed_at_us - last_reconciled_at_us >= maximum_interval_us


_UNSAFE_SOURCE_STATES = frozenset({SourceState.REPLACED, SourceState.TRUNCATED})
DEFAULT_TAIL_LIMITS = TailLimits()


def estimate_change_set(
    changes: ProposedChangeSet,
    *,
    dirty_keys: int = 0,
    projection_rows: int = 0,
    expected_wal_bytes: int | None = None,
) -> ChangeEstimate:
    """Derive conservative proposal bounds without touching SQLite."""

    observations = changes.observations
    sessions = {
        str(item.payload["session_id"])
        for item in observations
        if isinstance(item.payload.get("session_id"), str)
    }
    turns = {
        str(item.payload["turn_id"])
        for item in observations
        if isinstance(item.payload.get("turn_id"), str)
    }
    resources = {
        str(item.payload["resource_id"])
        for item in observations
        if isinstance(item.payload.get("resource_id"), str)
    }
    cycles = {
        str(item.payload["cycle_id"])
        for item in observations
        if isinstance(item.payload.get("cycle_id"), str)
    }
    model_calls = {
        item.logical_id for item in observations if item.observation_type == "ModelCallObserved"
    }
    selected_ranges = {
        (
            item.source_range.manifestation_key,
            item.source_range.source_revision,
            item.source_range.byte_start,
            item.source_range.byte_end,
        )
        for item in observations
    }
    selected_bytes = sum(end - start for _, _, start, end in selected_ranges)
    selected_records = len(
        {
            (
                item.source_range.manifestation_key,
                item.source_range.source_revision,
                item.source_range.record_ordinal,
            )
            for item in observations
        }
    )
    # SQLite row/index amplification is intentionally conservative. The writer
    # later measures actual WAL bytes and can fail closed.
    wal_bytes = (
        expected_wal_bytes
        if expected_wal_bytes is not None
        else 4_096 * max(1, len(observations) + len(changes.occurrences))
    )
    return ChangeEstimate(
        selected_bytes=selected_bytes,
        selected_records=selected_records,
        observations=len(observations),
        occurrences=len(changes.occurrences),
        affected_sessions=len(sessions),
        affected_turns=len(turns),
        affected_resources=len(resources),
        affected_allowance_cycles=len(cycles),
        dirty_keys=dirty_keys,
        projection_rows=projection_rows,
        expected_wal_bytes=wal_bytes,
        model_calls_inserted=len(model_calls),
    )


def _limit_breaches(
    estimate: ChangeEstimate,
    intent: RefreshIntent,
    limits: TailLimits,
) -> tuple[str, ...]:
    pairs = (
        ("selected_bytes", estimate.selected_bytes, limits.selected_bytes),
        ("selected_records", estimate.selected_records, limits.selected_records),
        ("observations", estimate.observations, limits.observations),
        ("occurrences", estimate.occurrences, limits.occurrences),
        ("affected_sessions", estimate.affected_sessions, limits.affected_sessions),
        ("affected_turns", estimate.affected_turns, limits.affected_turns),
        ("affected_resources", estimate.affected_resources, limits.affected_resources),
        (
            "affected_allowance_cycles",
            estimate.affected_allowance_cycles,
            limits.affected_allowance_cycles,
        ),
        ("dirty_keys", estimate.dirty_keys, limits.dirty_keys),
        ("projection_rows", estimate.projection_rows, limits.projection_rows),
        ("expected_wal_bytes", estimate.expected_wal_bytes, limits.expected_wal_bytes),
        (
            "model_call_tail_rows",
            intent.current_tail_rows + estimate.model_calls_inserted,
            limits.model_call_tail_rows,
        ),
        (
            "planning_staleness_us",
            intent.planned_at_us - intent.parent_observed_at_us,
            limits.planning_staleness_us,
        ),
    )
    return tuple(name for name, actual, ceiling in pairs if actual > ceiling)


_RefreshClassification = tuple[OperationClass, tuple[str, ...]]


def _compatibility_classification(intent: RefreshIntent) -> _RefreshClassification | None:
    if intent.schema_changed:
        return OperationClass.SCHEMA_UPGRADE, ("schema_contract_changed",)
    if intent.adapter_changed or intent.identity_changed or intent.normalization_changed:
        return OperationClass.RECANONICALIZE, ("adapter_identity_or_normalization_changed",)
    if intent.projection_registry_changed:
        return OperationClass.PROJECTION_UPGRADE, ("projection_registry_changed",)
    return None


def _is_no_change(changes: ProposedChangeSet, intent: RefreshIntent) -> bool:
    return all(
        (
            intent.parent_publication_id is not None,
            not changes.observations,
            not changes.occurrences,
            not changes.cursor_updates,
            not changes.diagnostics,
            intent.watcher_dirty_hint_count == 0,
            not intent.periodic_reconciliation_due,
            not intent.rate_card_changed,
        )
    )


def _source_replace_reason(changes: ProposedChangeSet, intent: RefreshIntent) -> str | None:
    if intent.canonical_owner_changed:
        return "canonical_owner_changed"
    if any(item.state in _UNSAFE_SOURCE_STATES for item in changes.selected_sources):
        return "source_replaced_or_truncated"
    return None


def _non_append_classification(
    changes: ProposedChangeSet, intent: RefreshIntent
) -> _RefreshClassification | None:
    compatibility = _compatibility_classification(intent)
    if compatibility is not None:
        return compatibility
    if _is_no_change(changes, intent):
        return OperationClass.NO_CHANGE, ("source_revisions_and_compatibility_unchanged",)
    if intent.parent_publication_id is None:
        return OperationClass.HISTORY_EXPAND, ("initial_isolated_publication",)
    source_replace_reason = _source_replace_reason(changes, intent)
    if source_replace_reason is not None:
        return OperationClass.SOURCE_REPLACE, (source_replace_reason,)
    if (
        intent.current_history_preset is not None
        and intent.history_preset != intent.current_history_preset
    ):
        return OperationClass.HISTORY_EXPAND, ("history_preset_changed",)
    if intent.rate_card_changed and not changes.observations:
        return OperationClass.VALUATION_ONLY, ("rate_card_changed",)
    return None


def _append_classification(
    estimate: ChangeEstimate,
    intent: RefreshIntent,
    limits: TailLimits,
) -> _RefreshClassification:
    breaches = _limit_breaches(estimate, intent, limits)
    if breaches:
        return (
            OperationClass.APPEND_SAFE_LARGE,
            tuple(f"limit_exceeded:{name}" for name in breaches),
        )
    return OperationClass.APPEND_SAFE_SMALL, ("all_small_tail_bounds_proven",)


def plan_refresh(
    changes: ProposedChangeSet,
    intent: RefreshIntent,
    *,
    limits: TailLimits = DEFAULT_TAIL_LIMITS,
    dirty_keys: int = 0,
    projection_rows: int = 0,
    expected_wal_bytes: int | None = None,
) -> PublicationPlan:
    """Choose the operation class before any analytical write lock exists."""

    if (
        intent.valuation_dirty_intervals
        and dirty_keys != len(intent.valuation_dirty_intervals)
    ):
        raise ValueError("dirty-key estimate must equal valuation dirty interval count")
    estimate = estimate_change_set(
        changes,
        dirty_keys=dirty_keys,
        projection_rows=projection_rows,
        expected_wal_bytes=expected_wal_bytes,
    )
    classification = _non_append_classification(changes, intent)
    if classification is None:
        classification = _append_classification(estimate, intent, limits)
    operation_class, reasons = classification
    return PublicationPlan(
        operation_class=operation_class,
        parent_publication_id=intent.parent_publication_id,
        estimate=estimate,
        reasons=reasons,
        analytical_write_required=operation_class not in {OperationClass.NO_CHANGE},
        valuation_dirty_intervals=intent.valuation_dirty_intervals,
    )
