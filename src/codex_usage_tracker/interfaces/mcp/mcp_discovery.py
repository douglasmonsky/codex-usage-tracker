"""Read-only usage discovery MCP implementation tools."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
)
from codex_usage_tracker.recommendation_engine.query import build_recommendations_report
from codex_usage_tracker.reports.api import (
    build_content_search_report,
    build_large_low_output_report,
    build_pattern_scan_report,
    build_pricing_coverage_report,
    build_query_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
    build_source_coverage_report,
    build_thread_trace_report,
)


def usage_query(
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    min_tokens: int | None = None,
    min_credits: float | None = None,
    limit: int = 100,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return stable JSON aggregate usage rows with filters for automation."""
    return build_query_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        min_tokens=min_tokens,
        min_credits=min_credits,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


def usage_recommendations(
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    min_score: float | None = None,
    limit: int = 20,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Rank aggregate usage rows and threads by recommendation severity."""
    report = build_recommendations_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        include_archived=include_archived,
        min_score=min_score,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    if response_format == "json":
        return report.payload
    return report.render()


def usage_pricing_coverage(
    limit: int = 20,
    since: str | None = None,
    response_format: str = "markdown",
) -> str | dict[str, Any]:
    """Show priced, estimated, and unpriced token coverage by model."""
    report = build_pricing_coverage_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        since=since,
    )
    if response_format == "json":
        return report.payload
    return report.render(limit=limit)


def usage_source_coverage(
    include_archived: bool = False,
    limit: int = 20,
    response_format: str = "markdown",
) -> str | dict[str, Any]:
    """Show source provenance parser coverage aggregate-only."""
    report = build_source_coverage_report(
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
    )
    if response_format == "json":
        return report.payload
    return report.render(limit=limit)


def usage_content_search(
    query: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 20,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Search explicit local content index snippets with aggregate call metadata."""
    return build_content_search_report(
        db_path=DEFAULT_DB_PATH,
        query=query,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
        privacy_mode=privacy_mode,
    ).payload


def usage_thread_trace(
    thread: str | None = None,
    thread_key: str | None = None,
    session_id: str | None = None,
    record_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return a local content-index call timeline for one thread/session."""
    return build_thread_trace_report(
        db_path=DEFAULT_DB_PATH,
        thread=thread,
        thread_key=thread_key,
        session_id=session_id,
        record_id=record_id,
        since=since,
        until=until,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
        privacy_mode=privacy_mode,
    ).payload


def _pattern_scan_payload(
    *,
    scan_type: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
    privacy_mode: str,
) -> dict[str, Any]:
    return build_pattern_scan_report(
        db_path=DEFAULT_DB_PATH,
        scan_type=scan_type,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


def usage_repetition_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated local content fragment hashes."""
    return _pattern_scan_payload(
        scan_type="repetition",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


def usage_command_loop_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated command roots/labels and failing command loops."""
    return _pattern_scan_payload(
        scan_type="command_loop",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


def usage_file_churn_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated normalized file read/modify events."""
    return _pattern_scan_payload(
        scan_type="file_churn",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


def usage_repeated_file_rediscovery(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Rank repeated safe file identities likely rediscovered across calls."""
    return build_repeated_file_rediscovery_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
        privacy_mode=privacy_mode,
    ).payload


def usage_shell_churn(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Rank repeated shell command families and adjacent command loops."""
    return build_shell_churn_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
        privacy_mode=privacy_mode,
    ).payload


def usage_large_low_output_calls(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find high-token calls with low output as token-waste candidates."""
    return build_large_low_output_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=min_total_tokens,
        max_output_tokens=max_output_tokens,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload
