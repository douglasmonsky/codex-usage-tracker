"""Deterministic occurrence reconciliation and CK-07-ready change proposals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ...domain.identity import semantic_id
from ...domain.models import MeasurementAggregate
from ...domain.time import validate_utc_microseconds
from ..contracts import (
    AdapterObservation,
    ParseDiagnostic,
    SourceCursor,
    SourceInventory,
    SourceRange,
)
from .parser import ParseBatch


@dataclass(frozen=True, slots=True)
class ProposedOccurrence:
    semantic_logical_id: str
    source_range: SourceRange

    @property
    def occurrence_id(self) -> str:
        return semantic_id(
            "source-occurrence",
            [
                self.semantic_logical_id,
                self.source_range.manifestation_id,
                self.source_range.source_revision,
                [self.source_range.byte_start, self.source_range.byte_end],
                self.source_range.record_ordinal,
                self.source_range.adapter_version,
            ],
        )


@dataclass(frozen=True, slots=True)
class AdapterAccounting:
    canonical_counts: Mapping[str, int]
    occurrence_counts: Mapping[str, int]
    token_sums: Mapping[str, MeasurementAggregate]


@dataclass(frozen=True, slots=True)
class ProposedChangeSet:
    """Body-free changes for the later publication writer."""

    observations: tuple[AdapterObservation, ...]
    occurrences: tuple[ProposedOccurrence, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
    cursor_updates: tuple[SourceCursor, ...]
    accounting: AdapterAccounting
    selected_sources: tuple[SourceInventory, ...]
    deferred_sources: tuple[SourceInventory, ...]

    def assert_body_free(self) -> None:
        forbidden = ("body", "command", "content", "diff", "patch", "prompt", "reasoning", "response", "stderr", "stdout", "tool_output")
        for observation in self.observations:
            for key in observation.payload:
                lowered = str(key).lower()
                if lowered in forbidden or lowered.endswith("_body") or lowered.startswith("raw_"):
                    raise ValueError(f"raw body field crossed the adapter boundary: {key}")


_COUNT_TYPES = {
    "ProjectObserved": "projects",
    "SessionObserved": "sessions",
    "TurnBoundaryObserved": "turns",
    "ModelCallObserved": "model_calls",
    "ToolLifecycleObserved": "tool_invocations",
    "ActivityLifecycleObserved": "activities",
    "CompactionObserved": "compaction_boundaries",
    "StateChangeObserved": "state_changes",
    "AllowanceObservationObserved": "allowance_observations",
    "AllowanceLimitObserved": "allowance_limits",
    "ResourceObserved": "resources",
}
_TOKEN_FIELDS = ("uncached_input_tokens", "cached_input_tokens", "reasoning_tokens", "output_tokens")


def _aggregate_tokens(observations: Iterable[AdapterObservation]) -> dict[str, MeasurementAggregate]:
    unique: dict[str, AdapterObservation] = {}
    for observation in observations:
        if observation.observation_type != "ModelCallObserved":
            continue
        existing = unique.get(observation.logical_id)
        if existing is None:
            unique[observation.logical_id] = observation
        elif existing.identity_tuple != observation.identity_tuple:
            raise ValueError(f"semantic identity conflict for {observation.logical_id}")
    result: dict[str, MeasurementAggregate] = {}
    for field in _TOKEN_FIELDS:
        values = [item.payload.get(field) for item in unique.values()]
        observed = [value for value in values if type(value) is int]
        result[field] = MeasurementAggregate(
            value=None if len(observed) != len(values) else sum(observed),
            observed_count=len(observed),
            missing_count=len(values) - len(observed),
        )
    return result


def build_change_set(
    batches: Iterable[ParseBatch],
    *,
    selected_sources: Iterable[SourceInventory],
    deferred_sources: Iterable[SourceInventory],
    window: tuple[int, int] | None = None,
) -> ProposedChangeSet:
    """Merge parser output in the contract order and preserve every occurrence."""

    if window is not None:
        start_us, end_us = window
        validate_utc_microseconds(start_us, allow_none=False)
        validate_utc_microseconds(end_us, allow_none=False)
        if start_us > end_us:
            raise ValueError("history window start must not exceed end")

    observations: list[AdapterObservation] = []
    diagnostics: list[ParseDiagnostic] = []
    cursor_updates: dict[int, SourceCursor] = {}
    for batch in batches:
        observations.extend(
            observation
            for observation in batch.observations
            if window is None
            or observation.event_at_us is None
            or window[0] <= observation.event_at_us <= window[1]
        )
        diagnostics.extend(batch.diagnostics)
        if batch.done and batch.cursor is not None:
            cursor_updates[batch.cursor.manifestation_key] = batch.cursor
    observations.sort(key=lambda item: item.sort_key)
    occurrence_by_id: dict[str, ProposedOccurrence] = {}
    for observation in observations:
        occurrence_by_id.setdefault(
            observation.occurrence_id,
            ProposedOccurrence(observation.logical_id, observation.source_range),
        )
    occurrences = tuple(
        occurrence_by_id[key]
        for key in sorted(occurrence_by_id)
    )
    canonical_by_type: dict[str, set[str]] = {}
    occurrence_by_type: dict[str, int] = {}
    for observation in observations:
        name = _COUNT_TYPES.get(observation.observation_type)
        if name is None:
            continue
        canonical_by_type.setdefault(name, set()).add(observation.logical_id)
        occurrence_by_type[name] = occurrence_by_type.get(name, 0) + 1
    accounting = AdapterAccounting(
        canonical_counts={key: len(value) for key, value in sorted(canonical_by_type.items())},
        occurrence_counts=dict(sorted(occurrence_by_type.items())),
        token_sums=_aggregate_tokens(observations),
    )
    result = ProposedChangeSet(
        observations=tuple(observations),
        occurrences=occurrences,
        diagnostics=tuple(diagnostics),
        cursor_updates=tuple(cursor_updates[key] for key in sorted(cursor_updates)),
        accounting=accounting,
        selected_sources=tuple(sorted(selected_sources, key=lambda item: item.source_rank)),
        deferred_sources=tuple(sorted(deferred_sources, key=lambda item: item.source_rank)),
    )
    result.assert_body_free()
    return result
