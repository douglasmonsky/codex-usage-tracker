"""Coverage-aware whole-source selection for explicit initial hydration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import partial
from pathlib import Path

from .discovery import SourceObservation, observe_source

_TAIL_SCAN_BYTES = 256 * 1024
_CATALOG_WORKERS = 4
_PARALLEL_CATALOG_MIN_SOURCES = 8


class HydrationPreset(str, Enum):
    RECENT_30D = "recent_30d"
    RECENT_90D = "recent_90d"
    COMPLETE = "complete"


@dataclass(frozen=True)
class CatalogSource:
    observation: SourceObservation
    latest_event_at: datetime | None

    @property
    def path(self) -> Path:
        return self.observation.path

    @property
    def timestamp_is_certain(self) -> bool:
        return self.latest_event_at is not None


@dataclass(frozen=True)
class CatalogCheckpoint:
    size_bytes: int
    modified_ns: int
    latest_event_at: datetime | None


@dataclass(frozen=True)
class HydrationSelection:
    preset: HydrationPreset
    captured_at: datetime
    cutoff_at: datetime | None
    hydrate: tuple[CatalogSource, ...]
    deferred: tuple[CatalogSource, ...]
    uncertain_source_count: int
    complete_history: bool

    @property
    def hydrated_bytes(self) -> int:
        return sum(item.observation.size_bytes for item in self.hydrate)

    @property
    def deferred_bytes(self) -> int:
        return sum(item.observation.size_bytes for item in self.deferred)


def catalog_sources(
    paths: tuple[Path, ...] | list[Path],
    *,
    checkpoints: Mapping[str, CatalogCheckpoint] | None = None,
) -> tuple[CatalogSource, ...]:
    """Observe every source and extract one bounded structural high water."""

    known = checkpoints or {}
    catalog_one = partial(_catalog_source, checkpoints=known)
    if len(paths) < _PARALLEL_CATALOG_MIN_SOURCES:
        return tuple(map(catalog_one, paths))
    with ThreadPoolExecutor(max_workers=_CATALOG_WORKERS) as pool:
        return tuple(pool.map(catalog_one, paths))


def _catalog_source(
    path: Path,
    *,
    checkpoints: Mapping[str, CatalogCheckpoint],
) -> CatalogSource:
    observation = observe_source(path)
    checkpoint = checkpoints.get(observation.source_id)
    unchanged = (
        checkpoint is not None
        and checkpoint.size_bytes == observation.size_bytes
        and checkpoint.modified_ns == observation.modified_ns
    )
    return CatalogSource(
        observation=observation,
        latest_event_at=(
            checkpoint.latest_event_at
            if unchanged and checkpoint is not None
            else _latest_structural_timestamp(observation)
        ),
    )


def catalog_checkpoints(
    catalog: tuple[CatalogSource, ...],
) -> dict[str, CatalogCheckpoint]:
    """Create reusable high-water metadata without retaining source content."""

    return {
        item.observation.source_id: CatalogCheckpoint(
            size_bytes=item.observation.size_bytes,
            modified_ns=item.observation.modified_ns,
            latest_event_at=item.latest_event_at,
        )
        for item in catalog
    }


def select_hydration_sources(
    catalog: tuple[CatalogSource, ...],
    *,
    preset: HydrationPreset,
    captured_at: datetime,
    hydrated_source_ids: frozenset[str] = frozenset(),
    hydrated_paths: frozenset[Path] = frozenset(),
) -> HydrationSelection:
    """Select whole sources without silently excluding uncertain history."""

    captured = _as_utc(captured_at)
    cutoff = _cutoff(preset, captured)
    hydrate: list[CatalogSource] = []
    deferred: list[CatalogSource] = []
    uncertain = 0
    for source in catalog:
        timestamp = source.latest_event_at
        if timestamp is None:
            uncertain += 1
        selected = (
            preset is HydrationPreset.COMPLETE
            or source.observation.source_id in hydrated_source_ids
            or source.path in hydrated_paths
            or timestamp is None
            or (cutoff is not None and timestamp >= cutoff)
        )
        (hydrate if selected else deferred).append(source)
    return HydrationSelection(
        preset=preset,
        captured_at=captured,
        cutoff_at=cutoff,
        hydrate=tuple(hydrate),
        deferred=tuple(deferred),
        uncertain_source_count=uncertain,
        complete_history=not deferred,
    )


def _cutoff(preset: HydrationPreset, captured_at: datetime) -> datetime | None:
    if preset is HydrationPreset.COMPLETE:
        return None
    days = 30 if preset is HydrationPreset.RECENT_30D else 90
    return captured_at - timedelta(days=days)


def _latest_structural_timestamp(
    observation: SourceObservation,
) -> datetime | None:
    end = observation.complete_size
    if end <= 0:
        return None
    start = max(0, end - _TAIL_SCAN_BYTES)
    with observation.path.open("rb") as handle:
        handle.seek(start)
        payload = handle.read(end - start)
    lines = payload.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    for raw_line in reversed(lines):
        try:
            item = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        parsed = _parse_timestamp(timestamp)
        if parsed is not None:
            return parsed
    return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return value.astimezone(timezone.utc)
