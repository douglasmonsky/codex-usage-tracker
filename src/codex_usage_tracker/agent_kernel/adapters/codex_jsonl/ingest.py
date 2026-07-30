"""Bounded Codex source ingestion orchestration."""

from __future__ import annotations

import resource
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import IngestMetrics, SourceCursor
from .canonicalize import ProposedChangeSet, build_change_set
from .discovery import discover_inventory, select_sources
from .parser import ParseBatch, parse_sources


@dataclass(frozen=True, slots=True)
class IngestResult:
    changes: ProposedChangeSet
    metrics: IngestMetrics


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if __import__("sys").platform == "darwin" else value * 1024


def ingest(
    root: Path,
    *,
    manifest: Path | dict[str, Any] | None = None,
    window: tuple[int, int] | None = None,
    max_files: int = 4096,
    max_bytes: int = 1 << 40,
    workers: int = 1,
    batch_size: int = 256,
    queue_capacity: int | None = None,
    cursors: Mapping[int, SourceCursor] | None = None,
    late_cutoff_us: int | None = None,
) -> IngestResult:
    """Discover, select, parse, and propose changes without publication writes."""

    started_ns = time.perf_counter_ns()
    inventory = discover_inventory(root, manifest=manifest, max_files=max_files, max_bytes=max_bytes)
    selected = select_sources(inventory, window=window, max_files=max_files, max_bytes=max_bytes)
    selected_sources = tuple(plan.inventory for plan in selected if plan.inventory.selected)
    deferred_sources = tuple(plan.inventory for plan in selected if not plan.inventory.selected)
    parser_metrics: list[dict[str, int]] = []
    batches: list[ParseBatch] = []
    for batch in parse_sources(
        selected,
        workers=workers,
        batch_size=batch_size,
        queue_capacity=queue_capacity,
        cursors=cursors,
        late_cutoff_us=late_cutoff_us,
        metrics_sink=parser_metrics,
    ):
        batches.append(batch)
    changes = build_change_set(
        batches,
        selected_sources=selected_sources,
        deferred_sources=deferred_sources,
        window=window,
    )
    final_by_source = {
        batch.source_rank: batch
        for batch in batches
        if batch.done
    }
    records_seen = sum(batch.records_seen for batch in final_by_source.values())
    diagnostics_emitted = len(changes.diagnostics)
    observations_emitted = len(changes.observations)
    metrics = IngestMetrics(
        sources_considered=len(inventory),
        sources_selected=len(selected_sources),
        sources_deferred=len(deferred_sources),
        source_bytes_selected=sum(item.size_bytes for item in selected_sources),
        records_seen=records_seen,
        observations_emitted=observations_emitted,
        diagnostics_emitted=diagnostics_emitted,
        batches_emitted=sum(not batch.done for batch in batches),
        max_queue_depth=(parser_metrics[-1]["max_queue_depth"] if parser_metrics else 0),
        workers=workers,
        batch_size=batch_size,
        peak_rss_bytes=_peak_rss_bytes(),
        elapsed_ns=time.perf_counter_ns() - started_ns,
    )
    return IngestResult(changes=changes, metrics=metrics)
