"""Spec-first MCP visualization implementation tools."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.interfaces.mcp import mcp_allowance, mcp_dashboard
from codex_usage_tracker.reports.visualization import (
    SUPPORTED_VISUALIZATION_KINDS,
    build_visualization_result,
    suggest_visualizations,
)


def usage_visualization_suggest(question: str, scope: str = "auto") -> dict[str, Any]:
    """Rank supported aggregate visualization intents for a usage question."""

    return suggest_visualizations(question, scope=scope)


def usage_visualization_render(
    kind: str,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    source_limit: int | None = 500,
    evidence_limit: int = 12,
    format: str = "spec",
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Return a renderer-independent VisualizationSpecV1 plus compact evidence."""

    normalized_kind = kind.strip().lower()
    _validate_render_request(normalized_kind, source_limit, evidence_limit, format)
    normalized_source_limit = 0 if source_limit is None else source_limit
    source = _visualization_source(
        normalized_kind,
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        source_limit=normalized_source_limit,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    )
    return build_visualization_result(
        normalized_kind,
        source,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
    )


def _validate_render_request(
    kind: str,
    source_limit: int | None,
    evidence_limit: int,
    output_format: str,
) -> None:
    if kind not in SUPPORTED_VISUALIZATION_KINDS:
        allowed = ", ".join(SUPPORTED_VISUALIZATION_KINDS)
        raise ValueError(f"kind must be one of: {allowed}")
    if output_format != "spec":
        raise ValueError(
            "format must be spec; SVG and PNG rendering are intentionally not base-runtime dependencies"
        )
    if source_limit is not None and source_limit < 0:
        raise ValueError("source_limit must be zero, None, or a positive integer")
    if evidence_limit < 1 or evidence_limit > 50:
        raise ValueError("evidence_limit must be between 1 and 50")


def _visualization_source(
    kind: str,
    *,
    search: str | None,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
    source_limit: int,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    if kind == "allowance_change":
        return mcp_allowance.usage_allowance_diagnostics(
            window_kind="weekly",
            limit=source_limit,
            include_archived=include_archived,
            privacy_mode=privacy_mode,
        )
    if kind == "thread_lifecycle":
        return _thread_source(
            search=search,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            source_limit=source_limit,
            privacy_mode=privacy_mode,
        )
    return mcp_dashboard.usage_report_pack(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        evidence_limit=min(50, max(evidence_limit * 4, evidence_limit)),
        include_archived=include_archived,
        sort="uncached" if kind == "cache_failure" else "tokens",
        direction="desc",
        limit=source_limit,
        privacy_mode=privacy_mode,
    )


def _thread_source(
    *,
    search: str | None,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
    source_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    if thread:
        return mcp_dashboard.usage_calls(
            search=search,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            sort="time",
            direction="asc",
            limit=source_limit,
            privacy_mode=privacy_mode,
        )
    return mcp_dashboard.usage_threads(
        search=search,
        include_archived=include_archived,
        sort="tokens",
        direction="desc",
        limit=source_limit,
    )
