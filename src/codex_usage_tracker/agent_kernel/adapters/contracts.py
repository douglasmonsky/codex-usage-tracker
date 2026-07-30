"""Typed, storage-independent contracts emitted by an agent adapter.

The adapter boundary deliberately contains no SQLite or Codex-host runtime
imports.  It carries structural facts and occurrence coordinates only; the
publication writer owns canonical entity selection and persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, IntFlag
from types import MappingProxyType
from typing import Any

from ..domain.identity import semantic_id
from ..domain.measurements import validate_nonnegative_int64
from ..domain.time import validate_utc_microseconds

ADAPTER_CONTRACT = "codex-usage-tracker.adapter.v1"
ADAPTER_ID = "codex-jsonl"
ADAPTER_VERSION = "codex-jsonl.v1"
IDENTITY_VERSION = "v1"
SOURCE_KIND = "codex-jsonl"


class Capability(IntFlag):
    """Observable adapter capabilities, persisted as a stable bit mask."""

    ALLOWANCE_OBSERVATION = 1 << 0
    MODEL_CALL_USAGE = 1 << 1
    SESSION_HIERARCHY = 1 << 2
    SOURCE_OCCURRENCE = 1 << 3
    STATE_CHANGE_OBSERVATION = 1 << 4
    TOOL_LIFECYCLE = 1 << 5
    VALUATION = 1 << 6
    CONTEXT_COMPONENT = 1 << 7


CAPABILITY_MASK = int(
    Capability.ALLOWANCE_OBSERVATION
    | Capability.MODEL_CALL_USAGE
    | Capability.SESSION_HIERARCHY
    | Capability.SOURCE_OCCURRENCE
    | Capability.STATE_CHANGE_OBSERVATION
    | Capability.TOOL_LIFECYCLE
    | Capability.VALUATION
    | Capability.CONTEXT_COMPONENT
)


class SourceState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    REPLACED = "replaced"
    TRUNCATED = "truncated"
    MISSING = "missing"
    MALFORMED = "malformed"
    DEFERRED = "deferred"


class TimeRangeConfidence(str, Enum):
    TRUSTED = "trusted"
    UNCERTAIN = "uncertain"
    UNAVAILABLE = "unavailable"


class CursorOutcome(str, Enum):
    APPEND_SAFE = "append_safe"
    NO_CHANGE = "no_change"
    TRUNCATED = "truncated"
    REPLACED = "replaced"
    RECANONICALIZE = "recanonicalize"
    MISSING = "missing"
    MALFORMED_RANGE = "malformed_range"
    LATE_EVENT = "late_event"


@dataclass(frozen=True, slots=True)
class AdapterIdentity:
    adapter_id: str = ADAPTER_ID
    adapter_version: str = ADAPTER_VERSION
    source_kind: str = SOURCE_KIND
    capability_mask: int = CAPABILITY_MASK
    identity_version: str = IDENTITY_VERSION


@dataclass(frozen=True, slots=True)
class SourceRange:
    """A complete source record coordinate, never the record body."""

    manifestation_id: str
    manifestation_key: int
    source_revision: str
    record_ordinal: int
    byte_start: int
    byte_end: int
    adapter_version: str = ADAPTER_VERSION

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        if self.manifestation_key == 0:
            raise ValueError("manifestation key must be positive")
        validate_nonnegative_int64(self.record_ordinal, allow_none=False)
        validate_nonnegative_int64(self.byte_start, allow_none=False)
        validate_nonnegative_int64(self.byte_end, allow_none=False)
        if self.byte_start >= self.byte_end:
            raise ValueError("source range must contain at least one byte")

    @property
    def coordinate_tuple(self) -> tuple[object, ...]:
        """Return the physical coordinate shared by typed observations."""

        return (
            self.manifestation_id,
            self.source_revision,
            (self.byte_start, self.byte_end),
            self.record_ordinal,
            self.adapter_version,
        )


@dataclass(frozen=True, slots=True)
class TimeRangeHint:
    start_us: int
    end_us: int

    def __post_init__(self) -> None:
        validate_utc_microseconds(self.start_us, allow_none=False)
        validate_utc_microseconds(self.end_us, allow_none=False)
        if self.start_us > self.end_us:
            raise ValueError("time range start must not exceed end")

    def overlaps_closed_window(self, start_us: int, end_us: int) -> bool:
        """Apply the frozen half-open-source/closed-window overlap rule."""

        validate_utc_microseconds(start_us, allow_none=False)
        validate_utc_microseconds(end_us, allow_none=False)
        if start_us > end_us:
            raise ValueError("history window start must not exceed end")
        return self.end_us > start_us and self.start_us <= end_us


@dataclass(frozen=True, slots=True)
class SourceInventory:
    """Bounded source metadata returned before a source is hydrated."""

    source_key: str
    manifestation_key: int
    manifestation_id: str
    source_kind: str
    technical_path_key: str
    display_label: str
    size_bytes: int
    modified_at_us: int | None
    prefix_fingerprint: str | None
    suffix_fingerprint: str | None
    content_revision: str
    source_rank: int
    state: SourceState
    time_range_hint: TimeRangeHint | None
    time_range_confidence: TimeRangeConfidence
    selected: bool = False
    deferred_reason: str | None = None
    filesystem_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.source_key or not self.technical_path_key:
            raise ValueError("source keys must be non-empty")
        if self.technical_path_key.startswith(("/", "./", "../")):
            raise ValueError("technical path key must be root-relative")
        if "\\" in self.technical_path_key or ":" in self.technical_path_key:
            raise ValueError("technical path key must use portable separators")
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        if self.manifestation_key == 0:
            raise ValueError("manifestation key must be positive")
        validate_nonnegative_int64(self.size_bytes, allow_none=False)
        validate_nonnegative_int64(self.source_rank, allow_none=False)
        validate_utc_microseconds(self.modified_at_us)
        if self.time_range_confidence is TimeRangeConfidence.UNAVAILABLE:
            if self.time_range_hint is not None:
                raise ValueError("unavailable time range cannot carry a hint")
        elif self.time_range_hint is None:
            raise ValueError("available time-range confidence requires a hint")


@dataclass(frozen=True, slots=True)
class SourceCursor:
    """Resume state whose offset is always after a complete JSONL record."""

    manifestation_id: str
    manifestation_key: int
    source_revision: str
    byte_offset: int
    record_ordinal: int
    source_size_bytes: int
    prefix_through_cursor_sha256: str
    suffix_sha256: str
    latest_source_order: int
    parser_version: str
    adapter_version: str = ADAPTER_VERSION

    def __post_init__(self) -> None:
        validate_nonnegative_int64(self.manifestation_key, allow_none=False)
        if self.manifestation_key == 0:
            raise ValueError("manifestation key must be positive")
        for value in (
            self.byte_offset,
            self.record_ordinal,
            self.source_size_bytes,
            self.latest_source_order,
        ):
            validate_nonnegative_int64(value, allow_none=False)
        if self.byte_offset > self.source_size_bytes:
            raise ValueError("cursor offset cannot exceed source size")
        for name, digest in (
            ("prefix_through_cursor_sha256", self.prefix_through_cursor_sha256),
            ("suffix_sha256", self.suffix_sha256),
        ):
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ParseDiagnostic:
    code: str
    source_range: SourceRange | None
    detail: str


@dataclass(frozen=True, slots=True)
class AdapterObservation:
    """A normalized, body-free structural observation."""

    observation_type: str
    logical_id: str
    identity_tuple: tuple[Any, ...]
    source_range: SourceRange
    source_rank: int
    event_at_us: int | None
    source_order: int
    event_kind_order: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    capability_mask: int = 0
    measurement_mask: int = 0
    basis: str = "adapter_exact"
    confidence: str = "exact"
    transition_rank: int = 0

    def __post_init__(self) -> None:
        validate_utc_microseconds(self.event_at_us)
        validate_nonnegative_int64(self.source_rank, allow_none=False)
        validate_nonnegative_int64(self.source_order, allow_none=False)
        validate_nonnegative_int64(self.event_kind_order, allow_none=False)
        validate_nonnegative_int64(self.capability_mask, allow_none=False)
        validate_nonnegative_int64(self.measurement_mask, allow_none=False)
        validate_nonnegative_int64(self.transition_rank, allow_none=False)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.event_at_us is None,
            0 if self.event_at_us is None else self.event_at_us,
            self.source_rank,
            self.source_order,
            self.event_kind_order,
            self.logical_id,
            self.transition_rank,
        )

    @property
    def occurrence_id(self) -> str:
        return semantic_id(
            "source-occurrence",
            [
                self.logical_id,
                self.source_range.manifestation_id,
                self.source_range.source_revision,
                [self.source_range.byte_start, self.source_range.byte_end],
                self.source_range.record_ordinal,
                self.source_range.adapter_version,
            ],
        )


@dataclass(frozen=True, slots=True)
class IngestMetrics:
    sources_considered: int
    sources_selected: int
    sources_deferred: int
    source_bytes_selected: int
    records_seen: int
    observations_emitted: int
    diagnostics_emitted: int
    batches_emitted: int
    max_queue_depth: int
    workers: int
    batch_size: int
    peak_rss_bytes: int
    elapsed_ns: int


def frozen_payload(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a shallow immutable payload for callers building observations."""

    return MappingProxyType(dict(values))
