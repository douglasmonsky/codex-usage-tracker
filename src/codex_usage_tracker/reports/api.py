"""Shared report application services for CLI and MCP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.formatting import (
    format_calls,
    format_summary,
)
from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import (
    apply_project_privacy_to_rows,
    apply_project_privacy_to_summary_rows,
    validate_privacy_mode,
)
from codex_usage_tracker.pricing.api import (
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.reports.action_brief import (
    ActionBriefReport as ActionBriefReport,
)
from codex_usage_tracker.reports.action_brief import (
    build_action_brief_report as build_action_brief_report,
)
from codex_usage_tracker.reports.agentic import (
    AgenticInvestigationReport as AgenticInvestigationReport,
)
from codex_usage_tracker.reports.agentic import (
    InvestigationSuggestionsReport as InvestigationSuggestionsReport,
)
from codex_usage_tracker.reports.agentic import (
    _dedupe_next_tools,
)
from codex_usage_tracker.reports.agentic import (
    build_agentic_investigation_report as build_agentic_investigation_report,
)
from codex_usage_tracker.reports.agentic import (
    build_investigation_suggestions_report as build_investigation_suggestions_report,
)
from codex_usage_tracker.reports.discovery import (
    ContentSearchReport as ContentSearchReport,
)
from codex_usage_tracker.reports.discovery import (
    LargeLowOutputReport as LargeLowOutputReport,
)
from codex_usage_tracker.reports.discovery import (
    PatternScanReport as PatternScanReport,
)
from codex_usage_tracker.reports.discovery import (
    PricingCoverageReport as PricingCoverageReport,
)
from codex_usage_tracker.reports.discovery import (
    RepeatedFileRediscoveryReport as RepeatedFileRediscoveryReport,
)
from codex_usage_tracker.reports.discovery import (
    ShellChurnReport as ShellChurnReport,
)
from codex_usage_tracker.reports.discovery import (
    SourceCoverageReport as SourceCoverageReport,
)
from codex_usage_tracker.reports.discovery import (
    ThreadTraceReport as ThreadTraceReport,
)
from codex_usage_tracker.reports.discovery import (
    build_content_search_report as build_content_search_report,
)
from codex_usage_tracker.reports.discovery import (
    build_large_low_output_report as build_large_low_output_report,
)
from codex_usage_tracker.reports.discovery import (
    build_pattern_scan_report as build_pattern_scan_report,
)
from codex_usage_tracker.reports.discovery import (
    build_pricing_coverage_report as build_pricing_coverage_report,
)
from codex_usage_tracker.reports.discovery import (
    build_repeated_file_rediscovery_report as build_repeated_file_rediscovery_report,
)
from codex_usage_tracker.reports.discovery import (
    build_shell_churn_report as build_shell_churn_report,
)
from codex_usage_tracker.reports.discovery import (
    build_source_coverage_report as build_source_coverage_report,
)
from codex_usage_tracker.reports.discovery import (
    build_thread_trace_report as build_thread_trace_report,
)
from codex_usage_tracker.reports.hypothesis_classification import (
    classify_hypothesis_family as _classify_hypothesis_family,
)
from codex_usage_tracker.reports.hypothesis_classification import (
    normalize_hypothesis_inputs as _normalize_hypothesis_inputs,
)
from codex_usage_tracker.reports.hypothesis_evaluators import (
    evaluate_hypothesis_spec as _evaluate_hypothesis_spec,
)
from codex_usage_tracker.reports.project_summary import project_summary_rows
from codex_usage_tracker.reports.query import (
    QUERY_CREDIT_CONFIDENCE_CHOICES as QUERY_CREDIT_CONFIDENCE_CHOICES,
)
from codex_usage_tracker.reports.query import (
    QUERY_PRICING_STATUS_CHOICES as QUERY_PRICING_STATUS_CHOICES,
)
from codex_usage_tracker.reports.query import (
    QueryReport as QueryReport,
)
from codex_usage_tracker.reports.query import (
    RecommendationsReport as RecommendationsReport,
)
from codex_usage_tracker.reports.query import (
    build_query_report as build_query_report,
)
from codex_usage_tracker.reports.query import (
    build_recommendations_report as build_recommendations_report,
)
from codex_usage_tracker.reports.recommendations import annotate_rows_with_recommendations
from codex_usage_tracker.store.api import (
    query_large_low_output_calls,
    query_most_expensive_calls,
    query_pattern_scan,
    query_summary,
    record_investigation_run,
)

SUMMARY_GROUP_BY_CHOICES = (
    "date",
    "model",
    "effort",
    "cwd",
    "project",
    "project_tag",
    "thread",
    "session",
    "thread_source",
    "subagent_type",
    "agent_role",
    "parent_session",
    "parent_thread",
)
SUMMARY_PRESET_CHOICES = (
    "today",
    "last-7-days",
    "by-model",
    "by-cwd",
    "by-project",
    "by-project-tag",
    "by-thread",
    "by-subagent-role",
    "by-subagent-type",
    "expensive",
)
EXPENSIVE_PRESET_CHOICES = ("today", "last-7-days")
_SUMMARY_PRESET_GROUPS = {
    "by-model": "model",
    "by-cwd": "cwd",
    "by-project": "project",
    "by-project-tag": "project_tag",
    "by-thread": "thread",
    "by-subagent-role": "agent_role",
    "by-subagent-type": "subagent_type",
}


@dataclass(frozen=True)
class SummaryReport:
    """Resolved aggregate usage summary for one display surface."""

    rows: list[dict[str, Any]]
    group_by: str
    is_expensive: bool = False
    privacy_mode: str = "normal"

    def render(self) -> str:
        if self.is_expensive:
            return format_calls(self.rows)
        return format_summary(self.rows, self.group_by)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "codex-usage-tracker-summary-v1",
            "group_by": self.group_by,
            "is_expensive": self.is_expensive,
            "privacy_mode": self.privacy_mode,
            "row_count": len(self.rows),
            "rows": self.rows,
        }


@dataclass(frozen=True)
class HypothesisTestReport:
    """Stable machine-readable agentic hypothesis test report."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class InvestigationWalkReport:
    """Stable machine-readable local investigation walk."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class LocalEvidenceExportReport:
    """Stable shareable local evidence export without raw/indexed content."""

    payload: dict[str, Any]


def resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    """Resolve summary presets into a group and since filter."""

    return _SUMMARY_PRESET_GROUPS.get(preset or "", group_by), resolve_since(preset, since)


def resolve_since(preset: str | None, since: str | None) -> str | None:
    """Resolve date presets into an ISO date string."""

    if since:
        return since
    if preset == "today":
        return date.today().isoformat()
    if preset == "last-7-days":
        return (date.today() - timedelta(days=6)).isoformat()
    return None


def build_summary_report(
    *,
    db_path: Path,
    pricing_path: Path,
    group_by: str = "thread",
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    privacy_mode: str = "normal",
) -> SummaryReport:
    """Build a usage summary or expensive-call preset from aggregate rows."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    resolved_group_by, since_filter = resolve_summary_options(group_by, preset, since)
    pricing = load_pricing_config(pricing_path)
    if preset == "expensive":
        rows = query_most_expensive_calls(db_path, limit=limit, since=since_filter)
        return SummaryReport(
            rows=apply_project_privacy_to_rows(
                annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
                privacy_mode=privacy_mode,
            ),
            group_by=resolved_group_by,
            is_expensive=True,
            privacy_mode=privacy_mode,
        )

    if resolved_group_by in {"project", "project_tag"}:
        rows = project_summary_rows(
            db_path=db_path,
            pricing=pricing,
            group_by=resolved_group_by,
            limit=limit,
            since=since_filter,
            projects_path=projects_path,
            privacy_mode=privacy_mode,
        )
        return SummaryReport(rows=rows, group_by=resolved_group_by, privacy_mode=privacy_mode)

    rows = query_summary(
        db_path,
        group_by=resolved_group_by,
        limit=limit,
        since=since_filter,
    )
    if resolved_group_by == "model":
        rows = annotate_rows_with_efficiency(rows, pricing, model_field="group_key")
    rows = apply_project_privacy_to_summary_rows(
        rows, group_by=resolved_group_by, privacy_mode=privacy_mode
    )
    return SummaryReport(rows=rows, group_by=resolved_group_by, privacy_mode=privacy_mode)


def build_expensive_calls_report(
    *,
    db_path: Path,
    pricing_path: Path,
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    privacy_mode: str = "normal",
) -> SummaryReport:
    """Build a highest-token-call report with pricing efficiency annotations."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    pricing = load_pricing_config(pricing_path)
    rows = query_most_expensive_calls(
        db_path,
        limit=limit,
        since=resolve_since(preset, since),
    )
    return SummaryReport(
        rows=apply_project_privacy_to_rows(
            annotate_rows_with_recommendations(annotate_rows_with_efficiency(rows, pricing)),
            privacy_mode=privacy_mode,
        ),
        group_by="call",
        is_expensive=True,
        privacy_mode=privacy_mode,
    )


HYPOTHESIS_TEST_FAMILIES = (
    "token_waste",
    "cache_failure",
    "repeated_file_rediscovery",
    "shell_churn",
    "effort_model_choice",
    "allowance_change",
)

_DEFAULT_HYPOTHESES = {
    "token_waste": "Token waste is concentrated in obvious high-token low-output calls.",
    "cache_failure": "Cache misses or cold resumes are inflating large calls.",
    "repeated_file_rediscovery": "Repeated file rediscovery is wasting tokens.",
    "shell_churn": "Repeated shell probing is creating workflow churn.",
    "effort_model_choice": "Model or effort choices are a meaningful usage driver.",
    "allowance_change": "Weekly allowance behavior may have changed.",
}


def build_hypothesis_test_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    question: str,
    hypotheses: list[str] | str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> HypothesisTestReport:
    """Test usage hypotheses using bounded existing diagnostics."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = max(1, evidence_limit)
    requested = _normalize_hypothesis_inputs(hypotheses)
    hypothesis_specs = (
        [
            {
                "id": f"hypothesis-{index}",
                "hypothesis": hypothesis,
                "family": _classify_hypothesis_family(hypothesis, question),
            }
            for index, hypothesis in enumerate(requested, start=1)
        ]
        if requested
        else [
            {
                "id": family,
                "hypothesis": _DEFAULT_HYPOTHESES[family],
                "family": family,
            }
            for family in HYPOTHESIS_TEST_FAMILIES
        ]
    )

    context: dict[str, Any] = {}
    tested = [
        _evaluate_hypothesis_spec(
            spec,
            context=context,
            db_path=db_path,
            pricing_path=pricing_path,
            allowance_path=allowance_path,
            projects_path=projects_path,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=normalized_limit,
            privacy_mode=privacy_mode,
        )
        for spec in hypothesis_specs
    ]
    status_counts: dict[str, int] = {}
    for result in tested:
        status = str(result["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    payload = {
        "schema": "codex-usage-tracker-hypothesis-test-v1",
        "content_mode": "aggregate_with_local_index_signals",
        "includes_indexed_content": True,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "question": question,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": normalized_limit,
        },
        "summary": {
            "hypothesis_count": len(tested),
            "status_counts": status_counts,
            "top_status": tested[0]["status"] if tested else None,
        },
        "hypotheses": tested,
        "recommended_next_tools": _dedupe_next_tools(
            [
                tool
                for result in tested
                for tool in result.get("recommended_next_tools", [])
                if isinstance(tool, dict)
            ]
        ),
        "caveats": [
            "Local Codex logs only; this is not an official OpenAI usage ledger.",
            "Hypothesis results are local evidence classifications, not proof of user intent.",
            "Raw prompts, assistant text, tool output, raw commands, and full paths are not included.",
        ],
    }
    return HypothesisTestReport(payload)


def build_investigation_walk_report(
    *,
    db_path: Path,
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> InvestigationWalkReport:
    """Build a bounded local investigation walk over normalized pattern evidence."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_evidence_limit = max(1, evidence_limit)
    pattern_result = query_pattern_scan(
        db_path=db_path,
        scan_type="all",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=normalized_evidence_limit * 4,
    )
    large_low_output_result = query_large_low_output_calls(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=20_000,
        max_output_tokens=1_000,
        limit=normalized_evidence_limit,
    )
    patterns = pattern_result["patterns"]
    branches = _investigation_branches(patterns=patterns, evidence_limit=normalized_evidence_limit)
    branches.append(
        _large_low_output_branch(
            rows=large_low_output_result["rows"],
            evidence_limit=normalized_evidence_limit,
        )
    )
    branches.sort(key=lambda branch: (-int(branch["score"]), str(branch["scan_type"])))
    supported = [branch for branch in branches if branch["status"] != "no_evidence"]
    payload = {
        "schema": "codex-usage-tracker-investigation-walk-v1",
        "content_mode": "local_content_index",
        "includes_indexed_content": True,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "question": question,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "min_occurrences": max(1, min_occurrences),
            "evidence_limit": normalized_evidence_limit,
        },
        "summary": {
            "branch_count": len(branches),
            "supported_branch_count": len(supported),
            "top_hypothesis": supported[0]["hypothesis"] if supported else None,
            "confidence": _walk_confidence(supported),
        },
        "branches": branches,
        "recommended_next_tools": _recommended_investigation_tools(supported),
    }
    record_investigation_run(db_path=db_path, run_kind="investigation_walk", payload=payload)
    return InvestigationWalkReport(payload)


def _investigation_branches(
    *,
    patterns: list[dict[str, Any]],
    evidence_limit: int,
) -> list[dict[str, Any]]:
    specs = (
        (
            "context_bloat",
            "High-token thread/context bloat",
            "Threads with concentrated token use or dense local evidence may be driving usage.",
        ),
        (
            "command_loop",
            "Repeated or failing command loop",
            "Repeated command roots/labels can indicate retry loops or avoidable automation waste.",
        ),
        (
            "file_churn",
            "Repeated file rediscovery or churn",
            "Repeated reads or edits of the same path hash can indicate rediscovery or unstable workflow loops.",
        ),
        (
            "repetition",
            "Repeated local content pattern",
            "Repeated fragment hashes can indicate recurring prompts, summaries, or copied context.",
        ),
    )
    branches: list[dict[str, Any]] = []
    for scan_type, hypothesis, rationale in specs:
        evidence = [row for row in patterns if row.get("scan_type") == scan_type]
        evidence.sort(
            key=lambda row: (-int(row.get("total_tokens") or 0), -int(row.get("occurrences") or 0))
        )
        selected = evidence[:evidence_limit]
        score = _branch_score(selected)
        branches.append(
            {
                "scan_type": scan_type,
                "hypothesis": hypothesis,
                "rationale": rationale,
                "status": _branch_status(score, selected),
                "score": score,
                "evidence_count": len(selected),
                "evidence": selected,
                "pruned_reason": None
                if selected
                else "No matching normalized local evidence at this threshold.",
            }
        )
    branches.sort(key=lambda branch: (-int(branch["score"]), str(branch["scan_type"])))
    return branches


def _large_low_output_branch(
    *,
    rows: list[dict[str, Any]],
    evidence_limit: int,
) -> dict[str, Any]:
    selected = [dict(row, scan_type="large_low_output") for row in rows[:evidence_limit]]
    score = _branch_score(selected)
    return {
        "scan_type": "large_low_output",
        "hypothesis": "Large calls with little output",
        "rationale": (
            "Large input/context usage with low output can indicate cold resumes, "
            "tool-output pressure, stale thread continuation, or low-value continuation."
        ),
        "status": _branch_status(score, selected),
        "score": score,
        "evidence_count": len(selected),
        "evidence": selected,
        "pruned_reason": None if selected else "No calls matched large low-output thresholds.",
    }


def _branch_score(evidence: list[dict[str, Any]]) -> int:
    total = 0
    for row in evidence:
        total += int(row.get("total_tokens") or 0)
        total += int(row.get("occurrences") or 0) * 100
        total += int(row.get("call_count") or 0) * 50
    return total


def _branch_status(score: int, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "no_evidence"
    if score >= 10_000:
        return "strong_local_signal"
    return "candidate"


def _walk_confidence(supported: list[dict[str, Any]]) -> str:
    if not supported:
        return "insufficient_local_evidence"
    if supported[0]["status"] == "strong_local_signal":
        return "moderate_local_evidence"
    return "weak_local_evidence"


def _recommended_investigation_tools(supported: list[dict[str, Any]]) -> list[dict[str, str]]:
    tools = [
        {
            "tool": "usage_calls",
            "reason": "Inspect the aggregate call rows behind high-token evidence.",
        }
    ]
    if not supported:
        tools.append(
            {
                "tool": "usage_report_pack",
                "reason": "Start from aggregate report cards when local pattern evidence is sparse.",
            }
        )
        return tools
    top_scan = str(supported[0]["scan_type"])
    if top_scan == "context_bloat":
        tools.append(
            {
                "tool": "usage_thread_trace",
                "reason": "Trace the highest-scoring thread to inspect call sequence and indexed fragments.",
            }
        )
    elif top_scan == "command_loop":
        tools.append(
            {
                "tool": "usage_command_loop_scan",
                "reason": "Raise limit or lower occurrence threshold to inspect repeated command families.",
            }
        )
    elif top_scan == "file_churn":
        tools.append(
            {
                "tool": "usage_file_churn_scan",
                "reason": "Inspect repeated file path hashes and linked aggregate calls.",
            }
        )
    elif top_scan == "large_low_output":
        tools.append(
            {
                "tool": "usage_large_low_output_calls",
                "reason": "Inspect large input/context calls that produced little output.",
            }
        )
    else:
        tools.append(
            {
                "tool": "usage_content_search",
                "reason": "Use explicit local snippet search only when transcript-level evidence is needed.",
            }
        )
    if any(str(branch["scan_type"]) == "large_low_output" for branch in supported) and all(
        tool["tool"] != "usage_large_low_output_calls" for tool in tools
    ):
        tools.append(
            {
                "tool": "usage_large_low_output_calls",
                "reason": "Inspect large input/context calls that produced little output.",
            }
        )
    return tools


def build_local_evidence_export_report(
    *,
    db_path: Path,
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
) -> LocalEvidenceExportReport:
    """Build shareable local evidence summary without raw/indexed records."""

    walk = build_investigation_walk_report(
        db_path=db_path,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
        privacy_mode="strict",
    ).payload
    branches = [_export_branch(branch) for branch in walk["branches"]]
    payload = {
        "schema": "codex-usage-tracker-local-evidence-export-v1",
        "content_mode": "shareable_local_evidence",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": "strict",
        "question": question,
        "filters": walk["filters"],
        "summary": {
            **walk["summary"],
            "export_branch_count": len(branches),
        },
        "branches": branches,
        "omitted_fields": [
            "record_id",
            "session_id",
            "thread_name",
            "raw_fragment",
            "snippet",
            "raw_command",
            "raw_tool_output",
            "full_path",
            "path_basename",
            "command_label",
        ],
        "caveats": [
            "Local evidence only; not an official OpenAI ledger.",
            "Counts are derived from local Codex logs and normalized tracker indexes.",
            "Export intentionally omits prompts, snippets, thread names, record ids, raw command output, and file names.",
        ],
    }
    record_investigation_run(db_path=db_path, run_kind="local_evidence_export", payload=payload)
    return LocalEvidenceExportReport(payload)


def _export_branch(branch: dict[str, Any]) -> dict[str, Any]:
    evidence = branch.get("evidence")
    evidence_rows = evidence if isinstance(evidence, list) else []
    return {
        "scan_type": branch["scan_type"],
        "hypothesis": branch["hypothesis"],
        "status": branch["status"],
        "score_bucket": _score_bucket(int(branch.get("score") or 0)),
        "evidence_count": int(branch.get("evidence_count") or 0),
        "pruned": branch["status"] == "no_evidence",
        "pruned_reason": branch.get("pruned_reason"),
        "aggregate_evidence": _export_aggregate_evidence(evidence_rows),
    }


def _export_aggregate_evidence(evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(evidence_rows)
    occurrences = sum(int(row.get("occurrences") or 0) for row in evidence_rows)
    call_count = sum(int(row.get("call_count") or 0) for row in evidence_rows)
    thread_count = sum(int(row.get("thread_count") or 0) for row in evidence_rows)
    record_ids = {str(row.get("record_id")) for row in evidence_rows if row.get("record_id")}
    thread_keys = {
        str(row.get("thread_key") or row.get("thread_name"))
        for row in evidence_rows
        if row.get("thread_key") or row.get("thread_name")
    }
    return {
        "evidence_row_count": row_count,
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in evidence_rows),
        "occurrences": occurrences or row_count,
        "call_count": call_count or len(record_ids) or row_count,
        "thread_count": thread_count or len(thread_keys),
        "first_seen_date": _date_bucket(_first_seen(evidence_rows)),
        "last_seen_date": _date_bucket(_last_seen(evidence_rows)),
    }


def _score_bucket(score: int) -> str:
    if score >= 100_000:
        return "100k_plus"
    if score >= 10_000:
        return "10k_to_100k"
    if score > 0:
        return "under_10k"
    return "none"


def _first_seen(rows: list[dict[str, Any]]) -> str | None:
    values = [str(row["first_seen_at"]) for row in rows if row.get("first_seen_at")]
    return min(values) if values else None


def _last_seen(rows: list[dict[str, Any]]) -> str | None:
    values = [str(row["last_seen_at"]) for row in rows if row.get("last_seen_at")]
    return max(values) if values else None


def _date_bucket(value: str | None) -> str | None:
    return value[:10] if value else None
