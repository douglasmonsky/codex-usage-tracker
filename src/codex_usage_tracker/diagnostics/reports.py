"""Shared diagnostics report builders for CLI and localhost API surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.projects import apply_project_privacy_to_rows, validate_privacy_mode
from codex_usage_tracker.diagnostics.action_hints import action_hint as _action_hint
from codex_usage_tracker.store.api import (
    query_diagnostic_fact_call_count,
    query_diagnostic_fact_calls,
    query_diagnostic_facts,
    query_diagnostic_summary,
)

DIAGNOSTICS_SCHEMA = "codex-usage-tracker-diagnostics-v1"
DIAGNOSTICS_NOTES = [
    "Associated token totals are not additive when one call has multiple diagnostic facts.",
    "Diagnostics use structured event metadata only; raw context remains explicit and on-demand.",
]
DIAGNOSTIC_FACT_SORT_CHOICES = (
    "uncached",
    "tokens",
    "cached",
    "output",
    "cache",
    "largest",
    "calls",
    "occurrences",
    "time",
    "fact",
)
DIAGNOSTIC_CALL_SORT_CHOICES = (
    "tokens",
    "time",
    "uncached",
    "input",
    "cached",
    "output",
    "reasoning",
    "cache",
    "model",
    "effort",
    "thread",
)
DIAGNOSTIC_DIRECTION_CHOICES = ("asc", "desc")
DIAGNOSTIC_TOOL_FACT_TYPES = {
    "activity",
    "command_family",
    "function",
    "mcp_server",
    "mcp_tool",
    "skill",
    "tool",
}


@dataclass(frozen=True)
class DiagnosticsReport:
    """Resolved diagnostics payload for one display surface."""

    payload: dict[str, Any]

    def render(self) -> str:
        view = self.payload.get("view")
        rows = self.payload.get("rows")
        if not isinstance(rows, list) or not rows:
            return "No diagnostic facts matched the requested filters."
        if view == "fact-calls":
            return _render_fact_calls(rows)
        if view == "summary":
            return _render_summary(rows)
        return _render_facts(rows)


def build_diagnostics_summary_report(
    *,
    db_path: Path,
    limit: int = 20,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    fact_type: str | None = None,
    fact_name: str | None = None,
    fact_category: str | None = None,
    include_archived: bool = False,
    sort: str = "uncached",
    direction: str = "desc",
) -> DiagnosticsReport:
    """Build diagnostic summaries grouped by fact type."""

    _validate_fact_sort(sort)
    _validate_direction(direction)
    normalized_limit = _normalize_limit(limit)
    all_rows = query_diagnostic_summary(
        db_path=db_path,
        limit=0,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=fact_category,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
    )
    rows = _limit_rows(all_rows, normalized_limit)
    for row in rows:
        row["action_hint"] = _action_hint(
            fact_type=str(row.get("fact_type") or ""),
            fact_name=str(row.get("top_fact_name") or ""),
        )
    return DiagnosticsReport(
        _diagnostics_payload(
            view="summary",
            rows=rows,
            total_matched_rows=len(all_rows),
            filters=_filters(
                since=since,
                until=until,
                model=model,
                effort=effort,
                thread=thread,
                min_tokens=min_tokens,
                fact_type=fact_type,
                fact_name=fact_name,
                fact_category=fact_category,
                fact_group=None,
                include_archived=include_archived,
                sort=sort,
                direction=direction,
                limit=normalized_limit,
                offset=0,
            ),
        )
    )


def build_diagnostics_facts_report(
    *,
    db_path: Path,
    limit: int = 50,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    fact_type: str | None = None,
    fact_name: str | None = None,
    fact_category: str | None = None,
    include_archived: bool = False,
    sort: str = "uncached",
    direction: str = "desc",
    fact_group: str | None = None,
    view: str = "facts",
) -> DiagnosticsReport:
    """Build diagnostic fact rows with associated token totals."""

    _validate_fact_sort(sort)
    _validate_direction(direction)
    _validate_fact_group(fact_group)
    normalized_limit = _normalize_limit(limit)
    all_rows = query_diagnostic_facts(
        db_path=db_path,
        limit=0,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=fact_category,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
    )
    grouped_rows = _filter_fact_group(all_rows, fact_group)
    rows = _limit_rows(grouped_rows, normalized_limit)
    for row in rows:
        row["action_hint"] = _action_hint(
            fact_type=str(row.get("fact_type") or ""),
            fact_name=str(row.get("fact_name") or ""),
        )
    return DiagnosticsReport(
        _diagnostics_payload(
            view=view,
            rows=rows,
            total_matched_rows=len(grouped_rows),
            filters=_filters(
                since=since,
                until=until,
                model=model,
                effort=effort,
                thread=thread,
                min_tokens=min_tokens,
                fact_type=fact_type,
                fact_name=fact_name,
                fact_category=fact_category,
                fact_group=fact_group,
                include_archived=include_archived,
                sort=sort,
                direction=direction,
                limit=normalized_limit,
                offset=0,
            ),
        )
    )


def build_diagnostics_fact_calls_report(
    *,
    db_path: Path,
    fact_type: str,
    fact_name: str,
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
    privacy_mode: str = "normal",
) -> DiagnosticsReport:
    """Build calls associated with one diagnostic fact."""

    if not fact_type:
        raise ValueError("fact_type is required")
    if not fact_name:
        raise ValueError("fact_name is required")
    _validate_call_sort(sort)
    _validate_direction(direction)
    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = _normalize_limit(limit)
    normalized_offset = max(offset, 0)
    rows = query_diagnostic_fact_calls(
        db_path=db_path,
        fact_type=fact_type,
        fact_name=fact_name,
        limit=normalized_limit,
        offset=normalized_offset,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
    )
    rows = apply_project_privacy_to_rows(rows, privacy_mode=privacy_mode)
    total_matched = query_diagnostic_fact_call_count(
        db_path=db_path,
        fact_type=fact_type,
        fact_name=fact_name,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
    )
    truncated = normalized_limit is not None and normalized_offset + len(rows) < total_matched
    return DiagnosticsReport(
        _diagnostics_payload(
            view="fact-calls",
            rows=rows,
            total_matched_rows=total_matched,
            filters=_filters(
                since=since,
                until=until,
                model=model,
                effort=effort,
                thread=thread,
                min_tokens=min_tokens,
                fact_type=fact_type,
                fact_name=fact_name,
                fact_category=None,
                fact_group=None,
                include_archived=include_archived,
                sort=sort,
                direction=direction,
                limit=normalized_limit,
                offset=normalized_offset,
                privacy_mode=privacy_mode,
            ),
            truncated=truncated,
        )
    )


def _diagnostics_payload(
    *,
    view: str,
    rows: list[dict[str, Any]],
    total_matched_rows: int,
    filters: dict[str, Any],
    truncated: bool | None = None,
) -> dict[str, Any]:
    if truncated is None:
        limit = filters.get("limit")
        offset = int(filters.get("offset") or 0)
        truncated = isinstance(limit, int) and offset + len(rows) < total_matched_rows
    return {
        "schema": DIAGNOSTICS_SCHEMA,
        "view": view,
        "filters": filters,
        "row_count": len(rows),
        "total_matched_rows": total_matched_rows,
        "truncated": truncated,
        "raw_context_included": False,
        "rows": rows,
        "notes": list(DIAGNOSTICS_NOTES),
    }


def _filters(
    *,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    min_tokens: int | None,
    fact_type: str | None,
    fact_name: str | None,
    fact_category: str | None,
    fact_group: str | None,
    include_archived: bool,
    sort: str,
    direction: str,
    limit: int | None,
    offset: int,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    return {
        "since": since,
        "until": until,
        "model": model,
        "effort": effort,
        "thread": thread,
        "min_tokens": min_tokens,
        "fact_type": fact_type,
        "fact_name": fact_name,
        "fact_category": fact_category,
        "fact_group": fact_group,
        "include_archived": include_archived,
        "sort": sort,
        "direction": direction,
        "limit": limit,
        "offset": offset,
        "privacy_mode": privacy_mode,
    }


def _render_facts(rows: list[dict[str, Any]]) -> str:
    lines = [_header("Fact", "Occ", "Calls", "Uncached", "Total")]
    for row in rows:
        fact = f"{row.get('fact_type')}/{row.get('fact_name')}"
        lines.append(
            _line(
                fact,
                _int(row.get("occurrences")),
                _int(row.get("associated_calls")),
                _int(row.get("associated_uncached_input_tokens")),
                _int(row.get("associated_total_tokens")),
            )
        )
    return "\n".join(lines)


def _render_summary(rows: list[dict[str, Any]]) -> str:
    lines = [_header("Type", "Occ", "Calls", "Uncached", "Top fact")]
    for row in rows:
        lines.append(
            _line(
                str(row.get("fact_type") or ""),
                _int(row.get("occurrences")),
                _int(row.get("associated_calls")),
                _int(row.get("associated_uncached_input_tokens")),
                str(row.get("top_fact_name") or ""),
            )
        )
    return "\n".join(lines)


def _render_fact_calls(rows: list[dict[str, Any]]) -> str:
    lines = [_header("Record", "Time", "Model", "Tokens", "Uncached")]
    for row in rows:
        lines.append(
            _line(
                str(row.get("record_id") or "")[:12],
                str(row.get("event_timestamp") or ""),
                str(row.get("model") or ""),
                _int(row.get("total_tokens")),
                _int(row.get("uncached_input_tokens")),
            )
        )
    return "\n".join(lines)


def _header(*columns: str) -> str:
    return _line(*columns)


def _line(*columns: str) -> str:
    return "  ".join(str(column) for column in columns)


def _int(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.0f}"
    return "0"


def _normalize_limit(limit: int) -> int | None:
    return None if limit <= 0 else int(limit)


def _limit_rows(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    return rows if limit is None else rows[:limit]


def _filter_fact_group(
    rows: list[dict[str, Any]],
    fact_group: str | None,
) -> list[dict[str, Any]]:
    if fact_group is None:
        return rows
    if fact_group == "tools":
        return [
            row for row in rows if str(row.get("fact_type") or "") in DIAGNOSTIC_TOOL_FACT_TYPES
        ]
    raise ValueError(f"unknown diagnostic fact group: {fact_group}")


def _validate_fact_group(fact_group: str | None) -> None:
    if fact_group not in {None, "tools"}:
        raise ValueError("fact_group must be one of: tools")


def _validate_fact_sort(sort: str) -> None:
    if sort not in DIAGNOSTIC_FACT_SORT_CHOICES:
        allowed = ", ".join(DIAGNOSTIC_FACT_SORT_CHOICES)
        raise ValueError(f"sort must be one of: {allowed}")


def _validate_call_sort(sort: str) -> None:
    if sort not in DIAGNOSTIC_CALL_SORT_CHOICES:
        allowed = ", ".join(DIAGNOSTIC_CALL_SORT_CHOICES)
        raise ValueError(f"sort must be one of: {allowed}")


def _validate_direction(direction: str) -> None:
    if direction not in DIAGNOSTIC_DIRECTION_CHOICES:
        allowed = ", ".join(DIAGNOSTIC_DIRECTION_CHOICES)
        raise ValueError(f"direction must be one of: {allowed}")
