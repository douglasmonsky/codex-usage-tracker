"""Compression Lab MCP tools."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.compression.api import (
    compression_candidate_detail,
    compression_candidates,
    compression_profile,
    compression_status,
    start_compression_analysis,
)
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.payloads import CANDIDATE_PAGE_BUDGET_BYTES
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH


@mcp.tool()
def usage_compression_start(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    model: str | None = None,
    effort: str | None = None,
    refresh: bool = False,
    detector_families: list[str] | None = None,
) -> dict[str, Any]:
    """Start or reuse an async Compression Lab analysis and return polling arguments."""
    return start_compression_analysis(
        DEFAULT_DB_PATH,
        _scope(since, until, thread, include_archived, model, effort),
        detector_families=detector_families,
        refresh=refresh,
    )


@mcp.tool()
def usage_compression_status(run_id: str) -> dict[str, Any]:
    """Poll monotonic Compression Lab progress without returning nested evidence."""
    return compression_status(DEFAULT_DB_PATH, run_id=run_id)


@mcp.tool()
def usage_compression_profile(
    run_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    model: str | None = None,
    effort: str | None = None,
    detector_families: list[str] | None = None,
) -> dict[str, Any]:
    """Return a completed compact profile; this tool never starts analysis."""
    return compression_profile(
        DEFAULT_DB_PATH,
        run_id=run_id,
        scope=_scope(since, until, thread, include_archived, model, effort),
        detector_families=detector_families,
    )


@mcp.tool()
def usage_compression_candidates(
    run_id: str,
    family: str | None = None,
    confidence_grade: str | None = None,
    model: str | None = None,
    thread: str | None = None,
    since: str | None = None,
    until: str | None = None,
    min_exposure: int = 0,
    min_likely_savings: int = 0,
    sort: str = "adjusted_likely",
    limit: int | None = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Page compact ranked candidates; limit zero/None requests full local scope."""
    return compression_candidates(
        DEFAULT_DB_PATH,
        run_id=run_id,
        family=family,
        confidence_grade=confidence_grade,
        model=model,
        thread=thread,
        since=since,
        until=until,
        min_exposure=min_exposure,
        min_likely_savings=min_likely_savings,
        sort=sort,
        limit=limit,
        offset=offset,
        max_payload_bytes=CANDIDATE_PAGE_BUDGET_BYTES,
    )


@mcp.tool()
def usage_compression_candidate_detail(
    candidate_id: str,
    evidence_mode: str = "handles",
    evidence_limit: int = 20,
    max_excerpt_chars: int = 400,
) -> dict[str, Any]:
    """Inspect one candidate using handles, summaries, or explicit bounded excerpts."""
    return compression_candidate_detail(
        DEFAULT_DB_PATH,
        candidate_id=candidate_id,
        evidence_mode=evidence_mode,
        evidence_limit=evidence_limit,
        max_excerpt_chars=max_excerpt_chars,
    )


def _scope(
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    model: str | None,
    effort: str | None,
) -> CompressionScope:
    return CompressionScope(
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        model=model,
        effort=effort,
    )
