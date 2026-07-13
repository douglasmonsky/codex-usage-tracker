"""Focused synthetic benchmarks for compression revision-state gates."""

from __future__ import annotations

import json
import shutil
import sqlite3
import statistics
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmark_synthetic_history import (
    _synthetic_events,
    _synthetic_source_envelopes,
    _synthetic_source_file,
    _write_synthetic_source_logs,
)

from codex_usage_tracker.compression.detector_registry import DETECTOR_FAMILIES
from codex_usage_tracker.compression.estimators import ESTIMATOR_POLICY_V1
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.compression_revisions import (
    current_compression_revision_vector,
)
from codex_usage_tracker.store.refresh import refresh_usage_index

MAX_REVISION_LOOKUP_SECONDS = 0.01
MAX_APPEND_REFRESH_SECONDS = 1.0


def benchmark_revision_and_append(db_path: Path, *, rows: int) -> dict[str, float]:
    """Measure bounded revision reads and one targeted aggregate append."""
    lookup_seconds: list[float] = []
    for _index in range(9):
        started = time.perf_counter()
        current_compression_revision_vector(
            db_path,
            detector_families=DETECTOR_FAMILIES,
            estimator_revision=ESTIMATOR_POLICY_V1.version,
        )
        lookup_seconds.append(time.perf_counter() - started)
    append_db = db_path.with_name(f"{db_path.stem}-append{db_path.suffix}")
    if append_db.exists():
        append_db.unlink()
    with sqlite3.connect(db_path) as source, sqlite3.connect(append_db) as target:
        source.backup(target)
    append_started = time.perf_counter()
    try:
        upsert_usage_events(
            _synthetic_events(rows, rows + 1),
            db_path=append_db,
            refresh_links=True,
        )
        return {
            "lookup_median_seconds": round(statistics.median(lookup_seconds), 6),
            "append_refresh_seconds": round(time.perf_counter() - append_started, 6),
        }
    finally:
        append_db.unlink(missing_ok=True)


def benchmark_source_append(db_dir: Path) -> dict[str, Any]:
    """Measure one real JSONL append after a representative indexed source."""
    source_root = db_dir / "cp4-source-append"
    source_db = db_dir / "cp4-source-append.sqlite3"
    if source_root.exists():
        shutil.rmtree(source_root)
    if source_db.exists():
        source_db.unlink()
    _write_synthetic_source_logs(source_root, 499)
    refresh_usage_index(codex_home=source_root, db_path=source_db)
    target = _synthetic_source_file(source_root, 499, events_per_file=500)
    turn_id = "turn-00000499"
    with target.open("a", encoding="utf-8") as handle:
        for envelope in _synthetic_source_envelopes(499, turn_id):
            handle.write(json.dumps(envelope, separators=(",", ":"), sort_keys=True) + "\n")
    started = time.perf_counter()
    result = refresh_usage_index(codex_home=source_root, db_path=source_db)
    return {
        "seconds": round(time.perf_counter() - started, 6),
        "parsed_events": result.parsed_events,
        "inserted_or_updated_events": result.inserted_or_updated_events,
        "scanned_files": result.scanned_files,
    }


def revision_threshold_failures(payload: Mapping[str, Any]) -> list[str]:
    """Validate CP4 lookup and append timing gates."""
    failures: list[str] = []
    revision_state = payload["revision_state"]
    revision_lookup = float(revision_state["lookup_median_seconds"])
    if revision_lookup > MAX_REVISION_LOOKUP_SECONDS:
        failures.append(
            "revision_state.lookup_median_seconds "
            f"{revision_lookup:.3f} exceeded {MAX_REVISION_LOOKUP_SECONDS:.3f}"
        )
    append_refresh = float(revision_state["append_refresh_seconds"])
    if append_refresh > MAX_APPEND_REFRESH_SECONDS:
        failures.append(
            "revision_state.append_refresh_seconds "
            f"{append_refresh:.3f} exceeded {MAX_APPEND_REFRESH_SECONDS:.3f}"
        )
    source_append = payload.get("source_append_refresh")
    if isinstance(source_append, Mapping):
        source_append_seconds = float(source_append["seconds"])
        if source_append_seconds > MAX_APPEND_REFRESH_SECONDS:
            failures.append(
                "source_append_refresh.seconds "
                f"{source_append_seconds:.3f} exceeded {MAX_APPEND_REFRESH_SECONDS:.3f}"
            )
    return failures
