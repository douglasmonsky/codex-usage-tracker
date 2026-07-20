"""Goal-led investigation MCP tools."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.cli.mcp_compression_router import (
    build_compression_action_router,
    build_compression_investigation_router,
    is_compression_router_goal,
)
from codex_usage_tracker.cli.mcp_dashboard import attach_dashboard_targets
from codex_usage_tracker.cli.mcp_discovery import _pattern_scan_payload
from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
)
from codex_usage_tracker.recommendation_engine.query import (
    build_recommendations_report as build_indexed_recommendations_report,
)
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_agentic_investigation_report,
    build_hypothesis_test_report,
    build_investigation_suggestions_report,
    build_investigation_walk_report,
    build_local_evidence_export_report,
)


@mcp.tool()
def usage_suggest_investigations(
    goal: str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 10,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Suggest goal-led usage investigations and next MCP tools."""
    return build_investigation_suggestions_report(
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_investigate(
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    detail_mode: str = "compact",
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Run a goal-led aggregate usage investigation."""
    if detail_mode == "compact" and is_compression_router_goal(goal):
        return attach_dashboard_targets(
            build_compression_investigation_router(
                db_path=DEFAULT_DB_PATH,
                goal=goal,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                evidence_limit=evidence_limit,
                privacy_mode=privacy_mode,
            ),
            privacy_mode=privacy_mode,
            history="all" if include_archived else "active",
        )
    payload = build_agentic_investigation_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        detail_mode=detail_mode,
        privacy_mode=privacy_mode,
        recommendation_report_builder=build_indexed_recommendations_report,
    ).payload
    return attach_dashboard_targets(
        payload,
        privacy_mode=privacy_mode,
        history="all" if include_archived else "active",
    )


@mcp.tool()
def usage_action_brief(
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return compact aggregate remediation brief with concrete next actions."""
    if is_compression_router_goal(goal):
        return build_compression_action_router(
            db_path=DEFAULT_DB_PATH,
            goal=goal,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=evidence_limit,
            privacy_mode=privacy_mode,
        )
    return build_action_brief_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_test_hypotheses(
    question: str,
    hypotheses: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Test usage hypotheses against aggregate/local-index diagnostics."""
    return build_hypothesis_test_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        question=question,
        hypotheses=hypotheses,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_context_bloat_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find high-token threads with local content/event density."""
    return _pattern_scan_payload(
        scan_type="context_bloat",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_investigation_walk(
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Run a bounded local hypothesis walk over normalized usage evidence."""
    return build_investigation_walk_report(
        db_path=DEFAULT_DB_PATH,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_local_evidence_export(
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
) -> dict[str, Any]:
    """Return a strict shareable local evidence summary without raw content."""
    return build_local_evidence_export_report(
        db_path=DEFAULT_DB_PATH,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
    ).payload
