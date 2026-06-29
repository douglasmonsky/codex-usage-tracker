"""Dashboard pricing snapshot comparison helpers."""

from __future__ import annotations

from typing import Any


def pricing_snapshot_warning(
    previous_payload: dict[str, Any] | None,
    current_payload: dict[str, object],
) -> str | None:
    snapshots = _pricing_snapshot_pair(previous_payload, current_payload)
    if snapshots is None:
        return None
    previous, current = snapshots
    previous_fingerprint = _pricing_snapshot_fingerprint(previous)
    current_fingerprint = _pricing_snapshot_fingerprint(current)
    if previous_fingerprint is None or current_fingerprint is None:
        return None
    if previous_fingerprint == current_fingerprint:
        return None

    previous_label = _pricing_snapshot_label(previous, fallback=previous_fingerprint)
    current_label = _pricing_snapshot_label(current, fallback=current_fingerprint)
    return f"Pricing snapshot changed since the previous dashboard render: {previous_label} -> {current_label}."


def _pricing_snapshot_pair(
    previous_payload: dict[str, Any] | None,
    current_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]] | None:
    if not previous_payload:
        return None
    previous = previous_payload.get("pricing_snapshot")
    current = current_payload.get("pricing_snapshot")
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return None
    return previous, current


def _pricing_snapshot_fingerprint(snapshot: dict[str, object]) -> str | None:
    fingerprint = snapshot.get("fingerprint")
    return fingerprint if isinstance(fingerprint, str) and fingerprint else None


def _pricing_snapshot_label(snapshot: dict[str, object], *, fallback: str) -> object:
    return snapshot.get("fetched_at") or snapshot.get("pinned_at") or fallback
