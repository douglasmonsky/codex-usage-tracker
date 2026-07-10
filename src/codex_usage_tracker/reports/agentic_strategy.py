"""Goal normalization and finding strategy helpers."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
)

AGENTIC_INVESTIGATION_GOALS = (
    "overview",
    "token_waste",
    "allowance_change",
    "cache_failure",
    "workflow_churn",
)


def _normalize_agentic_goal(goal: str | None) -> str | None:
    if goal is None:
        return None
    normalized = goal.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "waste": "token_waste",
        "token": "token_waste",
        "tokens": "token_waste",
        "usage_waste": "token_waste",
        "limits": "allowance_change",
        "limit_change": "allowance_change",
        "allowance": "allowance_change",
        "usage_limit": "allowance_change",
        "cache": "cache_failure",
        "caching": "cache_failure",
        "churn": "workflow_churn",
        "workflow": "workflow_churn",
        "summary": "overview",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in AGENTIC_INVESTIGATION_GOALS:
        return normalized
    return None


def _investigation_suggestions(goal: str | None) -> list[dict[str, Any]]:
    suggestions = [
        {
            "goal": "token_waste",
            "label": "Find obvious token-waste candidates",
            "why_it_matters": "Combines large low-output calls, shell churn, repeated file rediscovery, and recommendation scores.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "token_waste", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_large_low_output_calls",
                "usage_shell_churn",
                "usage_repeated_file_rediscovery",
                "usage_calls",
            ],
            "privacy_notes": "Aggregate-first; no raw prompts, tool output, or full paths.",
        },
        {
            "goal": "allowance_change",
            "label": "Check whether weekly allowance behavior changed",
            "why_it_matters": "Separates weekly evidence from noisy 5-hour rolling-window behavior.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "allowance_change", "privacy_mode": "strict"},
            "follow_up_tools": ["usage_allowance_diagnostics", "usage_allowance_export"],
            "privacy_notes": "Use strict privacy for shareable evidence bundles.",
        },
        {
            "goal": "cache_failure",
            "label": "Find cache misses and high-context continuations",
            "why_it_matters": "Low cache ratio and high context-window use often explain avoidable usage spikes.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "cache_failure", "evidence_limit": 5},
            "follow_up_tools": ["usage_large_low_output_calls", "usage_calls", "usage_call_detail"],
            "privacy_notes": "Aggregate token/cache fields only.",
        },
        {
            "goal": "workflow_churn",
            "label": "Find repeated shell and file rediscovery loops",
            "why_it_matters": "Repeated probes, command failures, and rereads suggest automation or documentation opportunities.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "workflow_churn", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_shell_churn",
                "usage_repeated_file_rediscovery",
                "usage_thread_trace",
            ],
            "privacy_notes": "Uses safe command labels and path identities, not raw command output or full paths.",
        },
        {
            "goal": "overview",
            "label": "Summarize current usage drivers",
            "why_it_matters": "Starts with index freshness, thread/model/project summaries, and existing recommendation cards.",
            "primary_tool": "usage_investigate",
            "default_arguments": {"goal": "overview", "evidence_limit": 5},
            "follow_up_tools": [
                "usage_status",
                "usage_summary",
                "usage_report_pack",
                "usage_recommendations",
            ],
            "privacy_notes": "Aggregate dashboard/report-pack evidence.",
        },
    ]
    if goal is None:
        return suggestions
    related_goals = {
        "overview": [
            "overview",
            "token_waste",
            "cache_failure",
            "workflow_churn",
            "allowance_change",
        ],
        "token_waste": ["token_waste", "cache_failure", "workflow_churn", "overview"],
        "cache_failure": ["cache_failure", "token_waste", "overview"],
        "workflow_churn": ["workflow_churn", "token_waste", "cache_failure", "overview"],
        "allowance_change": ["allowance_change", "overview", "token_waste"],
    }.get(goal, [goal])
    by_goal = {row["goal"]: row for row in suggestions}
    return [by_goal[row_goal] for row_goal in related_goals if row_goal in by_goal] or suggestions


def _normalize_agentic_detail_mode(detail_mode: str | None) -> str:
    normalized = (detail_mode or "compact").strip().lower().replace("-", "_")
    if normalized in {"full", "verbose", "raw", "rows"}:
        return "full"
    return "compact"


def _agentic_finding(
    *,
    finding: str,
    evidence: list[dict[str, Any]],
    detail_mode: str,
    confidence: str,
    why_it_matters: str,
    recommended_action: str,
    verify_with: list[str],
    privacy_notes: str,
    missing_access: str,
) -> dict[str, Any]:
    evidence_rows = (
        evidence
        if detail_mode == "full"
        else [_compact_agentic_evidence_row(row) for row in evidence]
    )
    return {
        "finding": finding,
        "evidence_count": len(evidence),
        "evidence_summary": _agentic_evidence_summary(evidence),
        "evidence": evidence_rows,
        "confidence": confidence,
        "why_it_matters": why_it_matters,
        "recommended_action": recommended_action,
        "verify_with": verify_with,
        "missing_access": missing_access,
        "privacy_notes": privacy_notes,
    }


def _overall_agentic_confidence(findings: list[dict[str, Any]]) -> str:
    priorities = {
        "high": 4,
        "medium": 3,
        "low": 2,
        "insufficient_local_evidence": 1,
    }
    if not findings:
        return "insufficient_local_evidence"
    return max(
        (str(row.get("confidence") or "") for row in findings),
        key=lambda value: priorities.get(value, 0),
    )


def _goal_next_tools(goal: str) -> list[dict[str, Any]]:
    mapping: dict[str, list[dict[str, Any]]] = {
        "token_waste": [
            {
                "tool": "usage_report_pack",
                "reason": "Inspect dashboard-shaped evidence rows for top aggregate drivers.",
                "default_arguments": {"evidence_limit": 10},
            },
            {
                "tool": "usage_calls",
                "reason": "Open high-token rows and sort/filter the underlying call table.",
                "default_arguments": {"sort": "tokens", "direction": "desc", "limit": 20},
            },
        ],
        "allowance_change": [
            {
                "tool": "usage_allowance_diagnostics",
                "reason": "Compare observed usage movement against estimated local credits.",
                "default_arguments": {"window_kind": "weekly", "privacy_mode": "strict"},
            }
        ],
        "cache_failure": [
            {
                "tool": "usage_calls",
                "reason": "Filter high context-window and low-cache calls.",
                "default_arguments": {"sort": "tokens", "direction": "desc", "limit": 20},
            }
        ],
        "workflow_churn": [
            {
                "tool": "usage_shell_churn",
                "reason": "Inspect repeated command families and failure/retry patterns.",
                "default_arguments": {"min_occurrences": 3, "limit": 20},
            }
        ],
        "overview": [
            {"tool": "usage_status", "reason": "Check index freshness.", "default_arguments": {}}
        ],
    }
    return mapping.get(goal, [])


def _dedupe_next_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("tool") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(tool)
    return deduped
