"""Frozen row and value models shared by canonical storage repositories."""

from __future__ import annotations

from dataclasses import dataclass

from .measurements import validate_nonnegative_int64
from .time import validate_utc_microseconds


@dataclass(frozen=True, slots=True)
class ConfiguredProducer:
    producer_id: str
    configured_producer_key: str
    display_label: str | None
    first_seen_publication_id: str
    last_seen_publication_id: str


@dataclass(frozen=True, slots=True)
class ConfiguredSource:
    source_id: str
    adapter_id: str
    producer_id: str
    source_kind: str
    adapter_native_source_key: str
    selected_history_preset: str
    selected_from_us: int | None
    selected_through_us: int | None
    first_seen_publication_id: str
    last_seen_publication_id: str

    def __post_init__(self) -> None:
        validate_utc_microseconds(self.selected_from_us)
        validate_utc_microseconds(self.selected_through_us)
        if (
            self.selected_from_us is not None
            and self.selected_through_us is not None
            and self.selected_from_us > self.selected_through_us
        ):
            raise ValueError("selected_from_us must not exceed selected_through_us")


@dataclass(frozen=True, slots=True)
class SourceManifestation:
    manifestation_id: str
    manifestation_key: int
    source_id: str
    adapter_native_file_key: str
    technical_path_key: str
    display_label: str
    filesystem_identity_json: str | None
    size_bytes: int
    modified_at_us: int | None
    prefix_sha256: str | None
    suffix_sha256: str | None
    content_revision: str
    source_rank: int
    state: str
    time_range_start_us: int | None
    time_range_end_us: int | None
    time_range_confidence: str
    selected: int
    first_seen_publication_id: str
    last_seen_publication_id: str
    ended_publication_id: str | None

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        if self.manifestation_key == 0:
            raise ValueError("manifestation_key must be greater than zero")
        validate_nonnegative_int64(self.size_bytes, allow_none=False)
        validate_utc_microseconds(self.modified_at_us)
        validate_nonnegative_int64(self.source_rank, allow_none=False)
        validate_utc_microseconds(self.time_range_start_us)
        validate_utc_microseconds(self.time_range_end_us)
        validate_nonnegative_int64(self.selected, allow_none=False)
        if self.selected not in (0, 1):
            raise ValueError("selected must be 0 or 1")
        if (
            self.time_range_start_us is not None
            and self.time_range_end_us is not None
            and self.time_range_start_us > self.time_range_end_us
        ):
            raise ValueError("time_range_start_us must not exceed time_range_end_us")


@dataclass(frozen=True, slots=True)
class SourceOccurrence:
    occurrence_id: str
    semantic_logical_id: str
    manifestation_key: int
    source_revision: str
    record_ordinal: int
    byte_start: int
    byte_end: int
    adapter_version: str
    first_seen_publication_id: str

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        if self.manifestation_key == 0:
            raise ValueError("manifestation_key must be greater than zero")
        validate_nonnegative_int64(self.record_ordinal, allow_none=False)
        validate_nonnegative_int64(self.byte_start, allow_none=False)
        validate_nonnegative_int64(self.byte_end, allow_none=False)
        if self.byte_start >= self.byte_end:
            raise ValueError("byte_end must be greater than byte_start")


@dataclass(frozen=True, slots=True)
class LifecycleTransition:
    transition_id: str
    entity_logical_id: str
    entity_kind: str
    lifecycle_state: str
    state_basis: str
    transition_version: int
    transition_at_us: int | None
    source_rank: int
    source_order: int
    event_kind_order: int
    transition_rank: int
    occurrence_id: str
    terminal_error_category: str | None
    measurement_mask: int
    first_seen_publication_id: str

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.transition_version, allow_none=False)
        if self.transition_version == 0:
            raise ValueError("transition_version must be positive")
        validate_utc_microseconds(self.transition_at_us)
        validate_nonnegative_int64(self.source_rank, allow_none=False)
        validate_nonnegative_int64(self.source_order, allow_none=False)
        validate_nonnegative_int64(self.event_kind_order, allow_none=False)
        validate_nonnegative_int64(self.transition_rank, allow_none=False)
        validate_nonnegative_int64(self.measurement_mask, allow_none=False)


@dataclass(frozen=True, slots=True)
class LifecycleFold:
    entity_logical_id: str
    lifecycle_state: str
    state_basis: str
    transition_version: int
    start_at_us: int | None
    start_occurrence_id: str | None
    terminal_at_us: int | None
    terminal_occurrence_id: str | None
    observed_duration_us: int | None
    duration_diagnostic: str | None
    terminal_error_category: str | None
    transition_count: int

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.transition_version, allow_none=False)
        validate_utc_microseconds(self.start_at_us)
        validate_utc_microseconds(self.terminal_at_us)
        validate_nonnegative_int64(self.observed_duration_us)
        validate_nonnegative_int64(self.transition_count, allow_none=False)


@dataclass(frozen=True, slots=True)
class ModelCallTokens:
    call_id: str
    uncached_input_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    output_tokens: int | None

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.uncached_input_tokens)
        validate_nonnegative_int64(self.cached_input_tokens)
        validate_nonnegative_int64(self.reasoning_tokens)
        validate_nonnegative_int64(self.output_tokens)


@dataclass(frozen=True, slots=True)
class MeasurementAggregate:
    value: int | None
    observed_count: int
    missing_count: int

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.value)
        validate_nonnegative_int64(self.observed_count, allow_none=False)
        validate_nonnegative_int64(self.missing_count, allow_none=False)

    @property
    def complete(self) -> bool:
        return self.missing_count == 0


@dataclass(frozen=True, slots=True)
class AccountingSummary:
    canonical_model_calls: int
    source_occurrences: int
    uncached_input_tokens: MeasurementAggregate
    cached_input_tokens: MeasurementAggregate
    reasoning_tokens: MeasurementAggregate
    output_tokens: MeasurementAggregate

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.canonical_model_calls, allow_none=False)
        validate_nonnegative_int64(self.source_occurrences, allow_none=False)
