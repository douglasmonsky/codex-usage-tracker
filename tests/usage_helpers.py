"""Synthetic usage fixtures shared by focused store and server tests."""

from __future__ import annotations

from dataclasses import replace

from codex_usage_tracker.core.models import UsageEvent
from tests.store_dashboard_helpers import _usage_event


def synthetic_usage_event(
    record_id: str,
    conversation_id: str,
    tokens: tuple[int, int, int, int],
    *,
    canonical: str = "canonical-a",
    model: str = "gpt-5.6-sol",
    effort: str = "high",
    service_tier: str | None = None,
    fast: int | None = None,
    duplicate: int = 0,
) -> UsageEvent:
    """Build one complete usage event without depending on removed sidecar fixtures."""

    input_tokens, cached_tokens, output_tokens, reasoning_tokens = tokens
    total_tokens = input_tokens + output_tokens
    effective_service_tier = service_tier
    if effective_service_tier is None and fast is not None:
        effective_service_tier = "fast" if fast else "standard"
    event = _usage_event(
        record_id=record_id,
        session_id=conversation_id,
        thread_key="thread:Synthetic",
        event_timestamp="2026-07-16T00:00:00Z",
        cumulative_total_tokens=total_tokens,
    )
    return replace(
        event,
        model=model,
        effort=effort,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        cumulative_input_tokens=input_tokens,
        cumulative_cached_input_tokens=cached_tokens,
        cumulative_output_tokens=output_tokens,
        cumulative_reasoning_output_tokens=reasoning_tokens,
        cumulative_total_tokens=total_tokens,
        usage_fingerprint=f"synthetic-fingerprint-{canonical}",
        canonical_record_id=canonical,
        is_duplicate=duplicate,
        service_tier=effective_service_tier,
        fast=fast,
        service_tier_source="usage_event" if effective_service_tier is not None else None,
        service_tier_confidence="exact" if effective_service_tier is not None else None,
    )
