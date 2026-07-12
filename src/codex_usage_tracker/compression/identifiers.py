"""Deterministic identifiers for compression scopes and candidates."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from codex_usage_tracker.compression.models import CompressionScope


def stable_scope_hash(scope: CompressionScope) -> str:
    """Return a stable hash for normalized compression filters."""
    return _stable_hash("compression-scope-v1", scope.as_dict())


def stable_candidate_id(
    *,
    source_revision: str,
    scope_hash: str,
    family: str,
    pattern_key: str,
    detector_version: str,
    estimator_version: str,
) -> str:
    """Return a deterministic candidate ID for one analysis revision."""
    digest = _stable_hash(
        "compression-candidate-v1",
        {
            "source_revision": source_revision,
            "scope_hash": scope_hash,
            "family": family,
            "pattern_key": pattern_key,
            "detector_version": detector_version,
            "estimator_version": estimator_version,
        },
    )
    return f"cmp_{digest}"


def _stable_hash(namespace: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"namespace": namespace, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]
