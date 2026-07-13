"""Compact dependency revisions for Compression Lab cache invalidation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.compression_schema import (
    create_compression_revision_tables,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

REVISION_DIMENSIONS = frozenset({"calls", "threads", "tools", "commands", "files", "fragments"})
_DIMENSION_COLUMNS = {
    "calls": "call_generation",
    "threads": "thread_generation",
    "tools": "tool_generation",
    "commands": "command_generation",
    "files": "file_generation",
    "fragments": "fragment_generation",
}
_DETECTOR_DEPENDENCIES = {
    "stale_context": frozenset({"calls", "threads"}),
    "cache_break_resume": frozenset({"calls", "threads"}),
    "file_rediscovery": frozenset({"calls", "threads", "files", "fragments"}),
    "shell_retry": frozenset({"calls", "threads", "commands"}),
    "validation_repetition": frozenset({"calls", "threads", "commands"}),
    "tool_output_bloat": frozenset({"calls", "threads", "tools"}),
}


@dataclass(frozen=True, slots=True)
class CompressionRevisionVector:
    """One bounded cache identity plus its diagnostic global generation."""

    generation: int
    revisions: tuple[tuple[str, int], ...]
    estimator_revision: str

    @property
    def cache_key(self) -> str:
        payload = {
            "estimator_revision": self.estimator_revision,
            "revisions": self.revisions,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def current_compression_revision_vector(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    detector_families: Collection[str] | None,
    estimator_revision: str,
) -> CompressionRevisionVector:
    """Read the detector-specific revision vector in one bounded database query."""
    with connect(db_path) as conn:
        init_db(conn)
        return read_compression_revision_vector(
            conn,
            detector_families=detector_families,
            estimator_revision=estimator_revision,
        )


def read_compression_revision_vector(
    conn: sqlite3.Connection,
    *,
    detector_families: Collection[str] | None,
    estimator_revision: str,
) -> CompressionRevisionVector:
    """Build a stable key from only the dimensions selected detectors consume."""
    row = conn.execute("SELECT * FROM compression_revision_state WHERE singleton = 1").fetchone()
    if row is None:
        raise RuntimeError("compression revision state is missing")
    dimensions = _detector_dimensions(detector_families)
    revisions = tuple(
        (dimension, int(row[_DIMENSION_COLUMNS[dimension]])) for dimension in sorted(dimensions)
    )
    return CompressionRevisionVector(
        generation=int(row["generation"]),
        revisions=revisions,
        estimator_revision=estimator_revision,
    )


def touch_compression_revisions(
    conn: sqlite3.Connection,
    dimensions: Iterable[str] = REVISION_DIMENSIONS,
) -> int:
    """Advance the global revision and the explicitly affected dimensions."""
    selected = frozenset(dimensions)
    unknown = selected.difference(REVISION_DIMENSIONS)
    if unknown:
        raise ValueError(f"unknown compression revision dimensions: {sorted(unknown)}")
    if not selected:
        return _read_global_generation(conn)
    create_compression_revision_tables(conn)
    assignments = ["generation = generation + 1"]
    assignments.extend(
        f"{_DIMENSION_COLUMNS[dimension]} = {_DIMENSION_COLUMNS[dimension]} + 1"
        for dimension in sorted(selected)
    )
    # Every identifier comes from the fixed dimension allowlist above.
    conn.execute(
        f"UPDATE compression_revision_state SET {', '.join(assignments)} WHERE singleton = 1"  # nosec B608
    )
    conn.execute(
        "UPDATE compression_source_state SET generation = generation + 1 WHERE singleton = 1"
    )
    return _read_global_generation(conn)


def _detector_dimensions(detector_families: Collection[str] | None) -> frozenset[str]:
    if detector_families is None:
        return REVISION_DIMENSIONS
    dimensions: set[str] = set()
    for family in detector_families:
        dependencies = _DETECTOR_DEPENDENCIES.get(family)
        if dependencies is None:
            return REVISION_DIMENSIONS
        dimensions.update(dependencies)
    return frozenset(dimensions)


def _read_global_generation(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT generation FROM compression_revision_state WHERE singleton = 1"
    ).fetchone()
    return int(row["generation"] if row is not None else 0)
