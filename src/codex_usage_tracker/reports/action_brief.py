"""Build compact remediation briefs from aggregate diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_PROJECTS_PATH
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.reports.agentic import _normalize_agentic_goal
from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
    _count_confidence,
)
from codex_usage_tracker.reports.discovery import (
    build_large_low_output_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.reports.query import build_recommendations_report


@dataclass(frozen=True)
class ActionBriefReport:
    """Stable machine-readable aggregate action brief."""

    payload: dict[str, Any]


def build_action_brief_report(
    *,
    db_path: Path,
    pricing_path: Path,
    allowance_path: Path,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
    precomputed_reports: dict[str, dict[str, Any]] | None = None,
) -> ActionBriefReport:
    """Build a compact remediation brief from aggregate diagnostics."""
    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_goal = _normalize_agentic_goal(goal) or "token_waste"
    normalized_limit = max(1, evidence_limit)
    report_cache = precomputed_reports if precomputed_reports is not None else {}
    actions: list[dict[str, Any]] = []
    source_reports: list[str] = []
    caveats = [
        "Local Codex logs only; this is not an official OpenAI usage ledger.",
        "Actions are aggregate recommendations; expensive work may still have been valuable.",
        "Archived sessions are excluded unless include_archived is true.",
    ]

    if normalized_goal in {"overview", "token_waste", "cache_failure"}:
        large_low_output = report_cache.get("large_low_output")
        if large_low_output is None:
            large_low_output = build_large_low_output_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["large_low_output"] = large_low_output
        source_reports.append(str(large_low_output["schema"]))
        if large_low_output["rows"]:
            actions.append(
                _action_brief_action(
                    family="large_low_output_context_pressure",
                    finding="Large calls produced little output",
                    confidence=_count_confidence(int(large_low_output["total_candidates"])),
                    evidence=large_low_output["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "Large input or context payloads with little output can indicate cold resumes, "
                        "stale thread continuation, or context copied forward after the useful work ended."
                    ),
                    recommended_workflow_change=(
                        "Create a short handoff, start a fresh thread for the next task, and keep only the "
                        "specific files or facts needed for the follow-up."
                    ),
                    recommended_existing_tool={
                        "tool": "Headroom",
                        "reason": "Use when available to estimate context pressure before continuing a long thread.",
                    },
                    recommended_custom_solution=(
                        "Add a repo-local handoff/checkpoint command or template that summarizes stable facts "
                        "without rereading broad context."
                    ),
                    how_to_verify=(
                        "Re-run `usage_large_low_output_calls` and inspect whether future high-token calls have "
                        "higher output, lower context pressure, or clearer task boundaries."
                    ),
                    recommended_next_tools=[
                        "usage_large_low_output_calls",
                        "usage_call_detail",
                        "usage_threads",
                    ],
                    missing_access="The aggregate report cannot know whether a low-output call produced valuable reasoning.",
                )
            )

        recommendations = report_cache.get("recommendations")
        if recommendations is None:
            recommendations = build_recommendations_report(
                db_path=db_path,
                pricing_path=pricing_path,
                allowance_path=allowance_path,
                projects_path=projects_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["recommendations"] = recommendations
        source_reports.append(str(recommendations["schema"]))

    if normalized_goal in {"overview", "token_waste", "cache_failure", "workflow_churn"}:
        repeated_files = report_cache.get("repeated_files")
        if repeated_files is None:
            repeated_files = build_repeated_file_rediscovery_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["repeated_files"] = repeated_files
        source_reports.append(str(repeated_files["schema"]))
        if repeated_files["rows"]:
            actions.append(
                _action_brief_action(
                    family="repeated_file_rediscovery",
                    finding="Repeated file rediscovery",
                    confidence=_count_confidence(int(repeated_files["total_candidates"])),
                    evidence=repeated_files["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "The same safe file identities keep being rediscovered, which can mean the agent is "
                        "spending turns rebuilding local context instead of using a durable note or helper."
                    ),
                    recommended_workflow_change=(
                        "Write stable file roles or investigation findings into a project note, then ask Codex "
                        "to use that note before opening the same files again."
                    ),
                    recommended_existing_tool=None,
                    recommended_custom_solution=(
                        "Create a small repo command or skill section that returns the exact file map, owner, "
                        "or test selector the agent keeps rediscovering."
                    ),
                    how_to_verify=(
                        "Re-run `usage_repeated_file_rediscovery` and confirm repeated safe file identities "
                        "drop or move to intentional focused reads."
                    ),
                    recommended_next_tools=[
                        "usage_repeated_file_rediscovery",
                        "usage_thread_trace",
                    ],
                    missing_access="Safe hashes prove recurrence, not whether each reread was necessary.",
                )
            )

        shell_churn = report_cache.get("shell_churn")
        if shell_churn is None:
            shell_churn = build_shell_churn_report(
                db_path=db_path,
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                min_occurrences=2,
                limit=normalized_limit,
                privacy_mode=privacy_mode,
            ).payload
            report_cache["shell_churn"] = shell_churn
        source_reports.append(str(shell_churn["schema"]))
        if shell_churn["rows"]:
            actions.append(
                _action_brief_action(
                    family="shell_churn",
                    finding="Repeated shell probing",
                    confidence=_count_confidence(int(shell_churn["total_candidates"])),
                    evidence=shell_churn["rows"][:normalized_limit],
                    likely_waste_pattern=(
                        "Repeated command families can indicate trial-and-error probing, especially when reads, "
                        "searches, or failed checks repeat without converging on an edit."
                    ),
                    recommended_workflow_change=(
                        "After two similar failed probes, summarize what was learned and switch to a narrower "
                        "query, helper script, or test selector."
                    ),
                    recommended_existing_tool=None,
                    recommended_custom_solution=(
                        "Add a project command for the repeated search/test sequence, or encode the sequence "
                        "in a repo skill so it is executed once intentionally."
                    ),
                    how_to_verify=(
                        "Re-run `usage_shell_churn` and compare repeated sed/rg/git/nl families before and "
                        "after the workflow change."
                    ),
                    recommended_next_tools=["usage_shell_churn", "usage_investigation_walk"],
                    missing_access="Aggregate command families omit raw command arguments in strict/shareable modes.",
                )
            )

    if normalized_goal in {"overview", "allowance_change"}:
        actions.append(
            _action_brief_action(
                family="allowance_change_readiness",
                finding="Allowance-change claims need weekly evidence first",
                confidence="evidence_required",
                evidence=[],
                likely_waste_pattern=(
                    "Five-hour movement is rolling-window context and can look noisy even when weekly allowance "
                    "behavior is stable."
                ),
                recommended_workflow_change=(
                    "Use weekly diagnostics before making public claims; treat outside usage and missing "
                    "observations as downgrade caveats."
                ),
                recommended_existing_tool=None,
                recommended_custom_solution=(
                    "Keep a local strict evidence export for Reddit/issues rather than sharing screenshots or raw logs."
                ),
                how_to_verify=(
                    'Run `usage_allowance_diagnostics(window_kind="weekly", privacy_mode="strict")` and '
                    '`usage_allowance_export(window_kind="weekly")`.'
                ),
                recommended_next_tools=["usage_allowance_diagnostics", "usage_allowance_export"],
                missing_access="OpenAI's internal ledger and other-surface account usage are not available locally.",
            )
        )

    if not actions:
        actions.append(
            _action_brief_action(
                family="insufficient_signal",
                finding="No strong aggregate action candidate at default thresholds",
                confidence="insufficient_local_evidence",
                evidence=[],
                likely_waste_pattern="No supported aggregate diagnostic crossed the default action threshold.",
                recommended_workflow_change=(
                    "Widen the time range, include archived sessions, lower tool-specific thresholds, or inspect "
                    "top calls/threads manually."
                ),
                recommended_existing_tool=None,
                recommended_custom_solution="Create a narrower hypothesis and test it with direct aggregate tools.",
                how_to_verify="Run `usage_suggest_investigations` or `usage_investigate` with a more specific goal.",
                recommended_next_tools=[
                    "usage_suggest_investigations",
                    "usage_investigate",
                    "usage_calls",
                ],
                missing_access="The brief needs stronger aggregate signals or a narrower user question.",
            )
        )

    payload = {
        "schema": "codex-usage-tracker-action-brief-v1",
        "content_mode": "aggregate_action_brief",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "goal": normalized_goal,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": normalized_limit,
        },
        "summary": {
            "action_count": len(actions),
            "top_action_family": actions[0]["family"] if actions else None,
            "source_reports": source_reports,
            "shared_report_cache_keys": sorted(report_cache),
        },
        "actions": actions,
        "recommended_next_tools": _dedupe_action_tools(actions),
        "caveats": caveats,
    }
    return ActionBriefReport(payload)


def _action_brief_action(
    *,
    family: str,
    finding: str,
    confidence: str,
    evidence: list[dict[str, Any]],
    likely_waste_pattern: str,
    recommended_workflow_change: str,
    recommended_existing_tool: dict[str, str] | None,
    recommended_custom_solution: str,
    how_to_verify: str,
    recommended_next_tools: list[str],
    missing_access: str,
) -> dict[str, Any]:
    return {
        "family": family,
        "finding": finding,
        "confidence": confidence,
        "evidence_count": len(evidence),
        "evidence_summary": _agentic_evidence_summary(evidence),
        "evidence": [_compact_agentic_evidence_row(row) for row in evidence],
        "likely_waste_pattern": likely_waste_pattern,
        "recommended_workflow_change": recommended_workflow_change,
        "recommended_existing_tool": recommended_existing_tool,
        "recommended_custom_solution": recommended_custom_solution,
        "how_to_verify": how_to_verify,
        "recommended_next_tools": recommended_next_tools,
        "missing_access": missing_access,
    }


def _dedupe_action_tools(actions: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    seen: set[str] = set()
    for action in actions:
        for tool in action.get("recommended_next_tools", []):
            tool_name = str(tool)
            if tool_name in seen:
                continue
            seen.add(tool_name)
            tools.append(tool_name)
    return tools
