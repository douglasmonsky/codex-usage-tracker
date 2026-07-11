"""Renderer-independent visualization payloads for MCP clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from codex_usage_tracker.reports.visualization_support import (
    _allowance_annotations,
    _allowance_row,
    _call_columns,
    _call_rows,
    _cartesian_spec,
    _column,
    _number,
    _series,
    _thread_call_row,
    _thread_summary_row,
)

VISUALIZATION_SUGGESTIONS_SCHEMA = "codex-usage-tracker-visualization-suggestions-v1"
VISUALIZATION_RESULT_SCHEMA = "codex-usage-tracker-visualization-result-v1"
SUPPORTED_VISUALIZATION_KINDS = (
    "token_waste",
    "allowance_change",
    "cache_failure",
    "thread_lifecycle",
)

_INTENTS = (
    {
        "kind": "token_waste",
        "title": "Token waste candidates",
        "keywords": ("token waste", "waste", "expensive", "large call", "low output", "cost"),
        "source_tools": ["usage_report_pack", "usage_large_low_output_calls"],
        "reason": "Compare uncached input with output on the largest aggregate calls.",
    },
    {
        "kind": "allowance_change",
        "title": "Weekly allowance change evidence",
        "keywords": ("allowance", "weekly", "limit", "quota", "throttled", "5-hour", "5 hour"),
        "source_tools": ["usage_allowance_diagnostics", "usage_allowance_history"],
        "reason": "Plot weekly capacity-proxy spans and candidate regime boundaries.",
    },
    {
        "kind": "cache_failure",
        "title": "Cache failure candidates",
        "keywords": ("cache", "context", "cold resume", "cached", "uncached"),
        "source_tools": ["usage_report_pack", "usage_calls"],
        "reason": "Rank calls with weak cache reuse and large uncached input.",
    },
    {
        "kind": "thread_lifecycle",
        "title": "Thread lifecycle load",
        "keywords": ("thread", "lifecycle", "session", "handoff", "long chat", "resume"),
        "source_tools": ["usage_threads", "usage_calls"],
        "reason": "Compare thread load or plot one thread's calls in chronological order.",
    },
)


def suggest_visualizations(question: str, *, scope: str = "auto") -> dict[str, Any]:
    """Rank supported visualization intents using deterministic question cues."""

    normalized_scope = scope.strip().lower() or "auto"
    if normalized_scope not in {"auto", "aggregate", "allowance", "thread"}:
        raise ValueError("scope must be one of: auto, aggregate, allowance, thread")
    normalized_question = question.strip().lower()
    ranked = sorted(
        (_ranked_intent(intent, normalized_question, normalized_scope) for intent in _INTENTS),
        key=lambda item: (-item["score"], SUPPORTED_VISUALIZATION_KINDS.index(item["kind"])),
    )
    return {
        "schema": VISUALIZATION_SUGGESTIONS_SCHEMA,
        "question": question,
        "scope": normalized_scope,
        "summary": {
            "suggestion_count": len(ranked),
            "top_kind": ranked[0]["kind"],
            "render_format": "spec",
        },
        "suggestions": ranked,
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
    }


def build_visualization_result(
    kind: str,
    source: dict[str, Any],
    *,
    include_archived: bool = False,
    evidence_limit: int = 12,
) -> dict[str, Any]:
    """Build one VisualizationSpecV1 result from an existing aggregate report payload."""

    normalized_kind = kind.strip().lower()
    if normalized_kind not in SUPPORTED_VISUALIZATION_KINDS:
        allowed = ", ".join(SUPPORTED_VISUALIZATION_KINDS)
        raise ValueError(f"kind must be one of: {allowed}")
    if evidence_limit < 1 or evidence_limit > 50:
        raise ValueError("evidence_limit must be between 1 and 50")
    builders: dict[
        str, Callable[..., tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]]
    ] = {
        "token_waste": _token_waste_visualization,
        "allowance_change": _allowance_visualization,
        "cache_failure": _cache_visualization,
        "thread_lifecycle": _thread_visualization,
    }
    spec, evidence_rows, narrative = builders[normalized_kind](
        source,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
    )
    caveats = list(spec.get("caveats") or [])
    return {
        "schema": VISUALIZATION_RESULT_SCHEMA,
        "format": "spec",
        "kind": normalized_kind,
        "source_schema": str(source.get("schema") or "unknown"),
        "visualization": spec,
        "evidence": {"row_count": len(evidence_rows), "rows": evidence_rows},
        "narrative": narrative,
        "caveats": caveats,
        "artifact_rendering": {
            "available": False,
            "supported_formats": ["spec"],
            "reason": "SVG and PNG rendering are intentionally not base-runtime dependencies.",
        },
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
    }


def _ranked_intent(intent: dict[str, Any], question: str, scope: str) -> dict[str, Any]:
    score = sum(3 for keyword in intent["keywords"] if keyword in question)
    if scope == "allowance" and intent["kind"] == "allowance_change":
        score += 4
    if scope == "thread" and intent["kind"] == "thread_lifecycle":
        score += 4
    if scope == "aggregate" and intent["kind"] in {"token_waste", "cache_failure"}:
        score += 2
    return {
        "kind": intent["kind"],
        "title": intent["title"],
        "score": score,
        "reason": intent["reason"],
        "render_tool": "usage_visualization_render",
        "default_arguments": {"kind": intent["kind"], "format": "spec"},
        "source_tools": intent["source_tools"],
        "privacy_notes": "Aggregate-only by default; no prompts, tool output, or raw fragments.",
    }


def _token_waste_visualization(
    source: dict[str, Any], *, include_archived: bool, evidence_limit: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    rows = _call_rows(source, evidence_limit=evidence_limit)
    rows.sort(
        key=lambda row: (-_number(row, "uncached_input_tokens"), _number(row, "output_tokens"))
    )
    rows = rows[:evidence_limit]
    caveats = [
        "Large uncached input with little output is a candidate signal, not proof that the context was unnecessary.",
        "Only aggregate call fields are included; inspect a linked call explicitly for local context.",
    ]
    spec = _cartesian_spec(
        source,
        identifier="mcp-token-waste",
        title="Large-input, low-output candidates",
        description="Uncached input and output tokens for the strongest loaded aggregate candidates.",
        rows=rows,
        include_archived=include_archived,
        y_field="uncached_input_tokens",
        y_label="Tokens",
        y_unit="tokens",
        series=[
            _series("uncached-input", "Uncached input", "uncached_input_tokens", "bar", "#2f6fed"),
            _series("output", "Output", "output_tokens", "bar", "#16866b"),
        ],
        columns=_call_columns(),
        caveats=caveats,
    )
    headline = (
        f"{len(rows)} token-waste candidates are ready to compare"
        if rows
        else "No token-waste candidates are available"
    )
    return (
        spec,
        rows,
        {
            "headline": headline,
            "summary": "The chart prioritizes uncached input while keeping output visible as the comparison signal.",
            "next_step": "Open the largest high-input, low-output call and verify whether a shorter handoff or bounded tool output would preserve the result.",
        },
    )


def _cache_visualization(
    source: dict[str, Any], *, include_archived: bool, evidence_limit: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    rows = _call_rows(source, evidence_limit=evidence_limit)
    rows.sort(
        key=lambda row: (_number(row, "cached_percent"), -_number(row, "uncached_input_tokens"))
    )
    rows = rows[:evidence_limit]
    caveats = [
        "Cache percentage is aggregate accounting evidence and does not identify the exact text that missed cache.",
        "Cold resumes, compaction, and genuinely new context can all raise uncached input.",
    ]
    spec = _cartesian_spec(
        source,
        identifier="mcp-cache-failure",
        title="Cache failure candidates",
        description="Calls ranked by weak cache reuse and large uncached input.",
        rows=rows,
        include_archived=include_archived,
        y_field="uncached_input_tokens",
        y_label="Uncached input",
        y_unit="tokens",
        series=[
            _series("uncached-input", "Uncached input", "uncached_input_tokens", "bar", "#9a5900")
        ],
        columns=_call_columns(),
        caveats=caveats,
    )
    return (
        spec,
        rows,
        {
            "headline": f"{len(rows)} calls are ranked for cache review"
            if rows
            else "No cache evidence is available",
            "summary": "The lowest cache percentages are considered first, with uncached input breaking ties.",
            "next_step": "Inspect a large candidate for a cold resume, oversized handoff, or repeated context that can move into a reusable artifact.",
        },
    )


def _allowance_visualization(
    source: dict[str, Any], *, include_archived: bool, evidence_limit: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    weekly = next(
        (window for window in source.get("windows", []) if window.get("window_kind") == "weekly"),
        {},
    )
    grade = str(
        weekly.get("evidence_grade")
        or source.get("summary", {}).get("primary_evidence_grade")
        or "insufficient_data"
    )
    rows = [
        _allowance_row(span, index, grade) for index, span in enumerate(weekly.get("spans", []))
    ]
    rows = [row for row in rows if row is not None][-evidence_limit:]
    candidate = next(iter(source.get("change_candidates", [])), None)
    annotations = _allowance_annotations(candidate, rows)
    caveats = [
        "This is a local weekly capacity proxy, not an official OpenAI allowance or billing ledger.",
        "Outside usage and sparse observations can weaken attribution even when a change point is visible.",
    ]
    spec = _cartesian_spec(
        source,
        identifier="mcp-allowance-change",
        title="Weekly allowance change evidence",
        description="Estimated credits per 100 percentage points of observed weekly movement.",
        rows=rows,
        include_archived=include_archived,
        y_field="capacity_proxy",
        y_label="Capacity proxy",
        y_unit="credits",
        series=[
            _series("capacity-proxy", "Local capacity proxy", "capacity_proxy", "line", "#2f6fed")
        ],
        columns=[
            _column("label", "Observed span", "time"),
            _column("capacity_proxy", "Credits per 100%", "number", "credits", "right"),
            _column("delta_usage_percent", "Observed movement", "number", "percent", "right"),
            _column("estimated_credits", "Estimated credits", "number", "credits", "right"),
            _column("evidence_grade", "Evidence grade", "text"),
        ],
        caveats=caveats,
        annotations=annotations,
        x_type="time",
    )
    return (
        spec,
        rows,
        {
            "headline": grade.replace("_", " "),
            "summary": f"{len(rows)} usable weekly spans are shown with the backend evidence grade.",
            "next_step": "Treat the candidate as local evidence only and review outside-usage caveats before making a public allowance claim.",
        },
    )


def _thread_visualization(
    source: dict[str, Any], *, include_archived: bool, evidence_limit: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    source_schema = str(source.get("schema") or "")
    if source_schema == "codex-usage-tracker-calls-v1":
        row_builder = _thread_call_row
        title = "Thread call lifecycle"
        description = "Chronological aggregate calls for the selected thread."
        series_kind = "line"
        column_label = "Call"
        x_type = "time"
        item_label = "calls"
    else:
        row_builder = _thread_summary_row
        title = "Thread lifecycle load"
        description = "Highest-token aggregate threads with lifecycle and cache context."
        series_kind = "bar"
        column_label = "Thread"
        x_type = "category"
        item_label = "threads"

    rows = [row_builder(row, index) for index, row in enumerate(source.get("rows", []))][
        :evidence_limit
    ]
    spec = _cartesian_spec(
        source,
        identifier="mcp-thread-lifecycle",
        title=title,
        description=description,
        rows=rows,
        include_archived=include_archived,
        y_field="total_tokens",
        y_label="Total tokens",
        y_unit="tokens",
        series=[
            _series(
                "total-tokens",
                "Total tokens",
                "total_tokens",
                series_kind,
                "#5f49b7",
            )
        ],
        columns=[
            _column("label", column_label, x_type),
            _column("total_tokens", "Total tokens", "number", "tokens", "right"),
            _column("call_count", "Calls", "number", "count", "right"),
            _column("cached_percent", "Cached", "number", "percent", "right"),
            _column(
                "estimated_cost_usd",
                "Estimated cost",
                "number",
                "usd",
                "right",
            ),
        ],
        caveats=[
            "Aggregate lifecycle evidence cannot determine whether the work product justified the token load."
        ],
        x_type=x_type,
    )
    return (
        spec,
        rows,
        {
            "headline": f"{len(rows)} {item_label} are visible in the lifecycle view",
            "summary": description,
            "next_step": "Inspect the largest transition and decide whether a concise handoff, fresh thread, or reusable artifact would reduce repeated context.",
        },
    )
