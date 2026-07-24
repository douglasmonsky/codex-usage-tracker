"""Public Compression Lab revision API."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.compression_revision_state import (
    REVISION_DIMENSIONS,
    CompressionRevisionVector,
    read_compression_revision_vector,
    touch_compression_revisions,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

__all__ = [
    "REVISION_DIMENSIONS",
    "CompressionRevisionVector",
    "current_compression_revision_vector",
    "read_compression_revision_vector",
    "touch_compression_revisions",
]


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
