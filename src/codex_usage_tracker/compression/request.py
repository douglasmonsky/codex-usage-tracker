"""Deterministic request identity for Compression Lab analysis runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.detector_protocol import CompressionDetector
from codex_usage_tracker.compression.detector_registry import (
    DETECTOR_FAMILIES,
    DETECTOR_SET_VERSION,
    select_detectors,
)
from codex_usage_tracker.compression.estimators import ESTIMATOR_POLICY_V1
from codex_usage_tracker.compression.identifiers import stable_scope_hash
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.store.compression_revisions import (
    current_compression_revision_vector,
)

COMPRESSION_SCHEMA_VERSION = 1
DetectorSelector = Callable[
    [Sequence[str] | None],
    Sequence[CompressionDetector],
]


@dataclass(frozen=True, slots=True)
class PreparedCompressionRequest:
    """One normalized point-in-time analysis request and cache identity."""

    detectors: tuple[CompressionDetector, ...]
    detector_families: tuple[str, ...]
    detector_set_version: str
    estimator_version: str
    compression_schema_version: int
    scope_hash: str
    revision_key: str
    source_generation: int
    request_key: str

    def cache_lookup(self) -> dict[str, Any]:
        return {
            "revision_key": self.revision_key,
            "scope_hash": self.scope_hash,
            "detector_set_version": self.detector_set_version,
            "estimator_version": self.estimator_version,
            "compression_schema_version": self.compression_schema_version,
        }


def prepare_compression_request(
    db_path: Path,
    scope: CompressionScope,
    *,
    detector_families: tuple[str, ...] | None = None,
    detector_selector: DetectorSelector = select_detectors,
) -> PreparedCompressionRequest:
    """Resolve detectors and the bounded SQLite revision identity once."""
    detectors = tuple(detector_selector(detector_families))
    selected_families = tuple(detector.family for detector in detectors)
    detector_version = _detector_set_version(detectors)
    scope_hash = stable_scope_hash(scope)
    revision = current_compression_revision_vector(
        db_path,
        detector_families=selected_families,
        estimator_revision=ESTIMATOR_POLICY_V1.version,
    )
    identity = {
        "compression_schema_version": COMPRESSION_SCHEMA_VERSION,
        "detector_set_version": detector_version,
        "estimator_version": ESTIMATOR_POLICY_V1.version,
        "revision_key": revision.cache_key,
        "scope_hash": scope_hash,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return PreparedCompressionRequest(
        detectors=detectors,
        detector_families=selected_families,
        detector_set_version=detector_version,
        estimator_version=ESTIMATOR_POLICY_V1.version,
        compression_schema_version=COMPRESSION_SCHEMA_VERSION,
        scope_hash=scope_hash,
        revision_key=revision.cache_key,
        source_generation=revision.generation,
        request_key=hashlib.sha256(encoded).hexdigest(),
    )


def _detector_set_version(detectors: tuple[CompressionDetector, ...]) -> str:
    families = tuple(detector.family for detector in detectors)
    if families == DETECTOR_FAMILIES:
        return DETECTOR_SET_VERSION
    return f"{DETECTOR_SET_VERSION}:{','.join(families)}"
