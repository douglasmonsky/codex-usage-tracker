"""Stable canonical identity for physically distinct usage records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

FINGERPRINT_VERSION = "usage-fingerprint-v1"
CANONICAL_ID_VERSION = "canonical-usage-v1"

STRICT_IDENTITY_FIELDS = (
    "event_timestamp", "turn_id", "turn_timestamp", "model", "effort",
    "model_context_window", "input_tokens", "cached_input_tokens", "output_tokens",
    "reasoning_output_tokens", "total_tokens", "cumulative_input_tokens",
    "cumulative_cached_input_tokens", "cumulative_output_tokens",
    "cumulative_reasoning_output_tokens", "cumulative_total_tokens",
    "rate_limit_plan_type", "rate_limit_limit_id", "rate_limit_primary_used_percent",
    "rate_limit_primary_window_minutes", "rate_limit_primary_resets_at",
    "rate_limit_secondary_used_percent", "rate_limit_secondary_window_minutes",
    "rate_limit_secondary_resets_at",
)


@dataclass(frozen=True)
class UsageIdentity:
    upstream_usage_id: str | None
    usage_fingerprint: str
    canonical_record_id: str


def extract_upstream_usage_id(
    envelope: Mapping[str, object], payload: Mapping[str, object], info: Mapping[str, object]
) -> str | None:
    """Return a recognized event identifier, preserving its source path."""
    for label, values in (("envelope", envelope), ("payload", payload), ("info", info)):
        for name in ("usage_id", "event_id", "call_id"):
            value = values.get(name)
            if isinstance(value, str) and value:
                return f"{label}.{name}:{value}"
    return None


def usage_identity_from_values(
    values: Mapping[str, object], *, upstream_usage_id: str | None = None
) -> UsageIdentity:
    basis = (
        {"upstream_usage_id": upstream_usage_id}
        if upstream_usage_id
        else {name: values.get(name) for name in STRICT_IDENTITY_FIELDS}
    )
    digest = _sha256_json({"version": FINGERPRINT_VERSION, "basis": basis})
    fingerprint = f"{FINGERPRINT_VERSION}:{digest}"
    canonical = hashlib.sha256(
        f"{CANONICAL_ID_VERSION}|{fingerprint}".encode("utf-8")
    ).hexdigest()
    return UsageIdentity(upstream_usage_id, fingerprint, canonical)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
