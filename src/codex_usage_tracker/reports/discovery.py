"""Coverage, content discovery, and token-waste candidate reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.formatting import format_pricing_coverage, format_source_coverage
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.pricing.api import (
    PricingConfig,
    load_pricing_config,
    summarize_pricing_coverage,
)
from codex_usage_tracker.store.api import (
    query_content_search,
    query_large_low_output_calls,
    query_pattern_scan,
    query_repeated_file_rediscovery,
    query_shell_churn,
    query_source_record_coverage,
    query_source_record_totals,
    query_summary,
    query_thread_trace,
)


@dataclass(frozen=True)
class PricingCoverageReport:
    """Resolved pricing coverage report."""

    payload: dict[str, Any]

    def render(self, limit: int = 20) -> str:
        return format_pricing_coverage(self.payload, limit=limit)


@dataclass(frozen=True)
class SourceCoverageReport:
    """Resolved source provenance parser coverage report."""

    payload: dict[str, Any]

    def render(self, limit: int = 20) -> str:
        return format_source_coverage(self.payload, limit=limit)


@dataclass(frozen=True)
class ContentSearchReport:
    """Stable machine-readable local content-index search result."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ThreadTraceReport:
    """Stable machine-readable local content-index thread trace."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class PatternScanReport:
    """Stable machine-readable local content/event-index pattern scan."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class RepeatedFileRediscoveryReport:
    """Stable machine-readable repeated safe file-identity report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ShellChurnReport:
    """Stable machine-readable repeated shell command churn report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class LargeLowOutputReport:
    """Stable machine-readable large low-output call report."""

    payload: dict[str, Any]


def build_pricing_coverage_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 1000,
    since: str | None = None,
    pricing: PricingConfig | None = None,
) -> PricingCoverageReport:
    """Build pricing coverage data grouped by model."""
    config = pricing or load_pricing_config(pricing_path)
    rows = query_summary(db_path, group_by="model", limit=limit, since=since)
    return PricingCoverageReport(summarize_pricing_coverage(rows, pricing=config))


def build_source_coverage_report(
    *,
    db_path: Path,
    include_archived: bool = False,
) -> SourceCoverageReport:
    """Build parser/source provenance coverage report."""
    rows = query_source_record_coverage(
        db_path=db_path,
        include_archived=include_archived,
    )
    totals = query_source_record_totals(
        db_path=db_path,
        include_archived=include_archived,
    )
    return SourceCoverageReport(
        {
            "schema": "codex-usage-tracker-source-coverage-v1",
            "content_mode": "aggregate_only",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "include_archived": include_archived,
            "source_record_count": int(totals.get("source_record_count") or 0),
            "source_file_count": int(totals.get("source_file_count") or 0),
            "parser_version_count": int(totals.get("parser_version_count") or 0),
            "warning_record_count": int(totals.get("warning_record_count") or 0),
            "rows": rows,
        }
    )


def build_content_search_report(
    *,
    db_path: Path,
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
) -> ContentSearchReport:
    """Build explicit local content-index search payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_content_search(
        db_path=db_path,
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
    )
    rows = result["rows"]
    normalized_limit = None if limit is None or limit <= 0 else limit
    normalized_offset = max(0, offset)
    total_matched = int(result["total_matched_rows"])
    has_more = False if normalized_limit is None else normalized_offset + len(rows) < total_matched
    return ContentSearchReport(
        {
            "schema": "codex-usage-tracker-content-search-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": True,
            "privacy_mode": privacy_mode,
            "query": query,
            "filters": {
                "since": since,
                "until": until,
                "model": model,
                "effort": effort,
                "thread": thread,
                "include_archived": include_archived,
                "limit": limit,
                "offset": normalized_offset,
                "max_snippet_chars": max_snippet_chars,
            },
            "search_mode": result["search_mode"],
            "row_count": len(rows),
            "total_matched_rows": total_matched,
            "truncated": has_more,
            "has_more": has_more,
            "next_offset": (normalized_offset + len(rows) if has_more else None),
            "rows": rows,
        }
    )


def build_thread_trace_report(
    *,
    db_path: Path,
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
) -> ThreadTraceReport:
    """Build explicit local content-index thread/session trace payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_thread_trace(
        db_path=db_path,
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
    )
    calls = result["calls"]
    normalized_limit = None if limit is None or limit <= 0 else limit
    normalized_offset = max(0, offset)
    total_matched = int(result["total_matched_calls"])
    has_more = False if normalized_limit is None else normalized_offset + len(calls) < total_matched
    return ThreadTraceReport(
        {
            "schema": "codex-usage-tracker-thread-trace-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": True,
            "privacy_mode": privacy_mode,
            "filters": {
                "thread": thread,
                "thread_key": thread_key,
                "session_id": session_id,
                "record_id": record_id,
                "since": since,
                "until": until,
                "include_archived": include_archived,
                "limit": limit,
                "offset": normalized_offset,
                "max_snippet_chars": max_snippet_chars,
            },
            "call_count": len(calls),
            "total_matched_calls": total_matched,
            "truncated": has_more,
            "has_more": has_more,
            "next_offset": (normalized_offset + len(calls) if has_more else None),
            "calls": calls,
        }
    )


def build_pattern_scan_report(
    *,
    db_path: Path,
    scan_type: str = "all",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> PatternScanReport:
    """Build local content/event-index pattern scan payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_pattern_scan(
        db_path=db_path,
        scan_type=scan_type,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
    )
    patterns = result["patterns"]
    return PatternScanReport(
        {
            "schema": "codex-usage-tracker-pattern-scan-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "scan_type": scan_type,
            "scan_types": list(result["scan_types"]),
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
            },
            "pattern_count": len(patterns),
            "total_patterns": result["total_patterns"],
            "patterns": patterns,
        }
    )


def build_repeated_file_rediscovery_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> RepeatedFileRediscoveryReport:
    """Build repeated safe file-identity rediscovery payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_repeated_file_rediscovery(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
    )
    rows = result["rows"]
    return RepeatedFileRediscoveryReport(
        {
            "schema": "codex-usage-tracker-repeated-file-rediscovery-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
                "sample_limit": max(1, sample_limit),
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
    )


def build_shell_churn_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> ShellChurnReport:
    """Build repeated shell command family churn payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    result = query_shell_churn(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
    )
    rows = result["rows"]
    return ShellChurnReport(
        {
            "schema": "codex-usage-tracker-shell-churn-v1",
            "content_mode": "local_content_index",
            "includes_indexed_content": True,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_occurrences": max(1, min_occurrences),
                "limit": limit,
                "sample_limit": max(1, sample_limit),
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
    )


def build_large_low_output_report(
    *,
    db_path: Path,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> LargeLowOutputReport:
    """Build aggregate-first large low-output call payload."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_min_total = max(0, min_total_tokens)
    normalized_max_output = max(0, max_output_tokens)
    result = query_large_low_output_calls(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=normalized_min_total,
        max_output_tokens=normalized_max_output,
        limit=limit,
    )
    rows = result["rows"]
    return LargeLowOutputReport(
        {
            "schema": "codex-usage-tracker-large-low-output-v1",
            "content_mode": "aggregate_with_local_activity",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "privacy_mode": privacy_mode,
            "filters": {
                "since": since,
                "until": until,
                "thread": thread,
                "include_archived": include_archived,
                "min_total_tokens": normalized_min_total,
                "max_output_tokens": normalized_max_output,
                "limit": limit,
            },
            "row_count": len(rows),
            "total_candidates": int(result["total_candidates"]),
            "rows": rows,
        }
    )
