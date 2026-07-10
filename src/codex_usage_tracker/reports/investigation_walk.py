"""Bounded investigation walk and strict local evidence export reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.store.api import (
    query_large_low_output_calls,
    query_pattern_scan,
    record_investigation_run,
)


@dataclass(frozen=True)
class InvestigationWalkReport:
    """Stable machine-readable local investigation walk."""

    payload: dict[str, Any]


@dataclass(frozen=True)
class LocalEvidenceExportReport:
    """Stable shareable local evidence export without raw/indexed content."""

    payload: dict[str, Any]


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
    occurrences = _sum_int_field(evidence_rows, "occurrences")
    call_count = _sum_int_field(evidence_rows, "call_count")
    thread_count = _sum_int_field(evidence_rows, "thread_count")
    record_count = len(_unique_first_value(evidence_rows, "record_id"))
    unique_thread_count = len(_unique_first_value(evidence_rows, "thread_key", "thread_name"))
    return {
        "evidence_row_count": row_count,
        "total_tokens": _sum_int_field(evidence_rows, "total_tokens"),
        "occurrences": _first_nonzero(occurrences, row_count),
        "call_count": _first_nonzero(call_count, record_count, row_count),
        "thread_count": _first_nonzero(thread_count, unique_thread_count),
        "first_seen_date": _date_bucket(_first_seen(evidence_rows)),
        "last_seen_date": _date_bucket(_last_seen(evidence_rows)),
    }


def _sum_int_field(rows: list[dict[str, Any]], field: str) -> int:
    return sum(int(row.get(field) or 0) for row in rows)


def _unique_first_value(rows: list[dict[str, Any]], *fields: str) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = next((row.get(field) for field in fields if row.get(field)), None)
        if value is not None:
            values.add(str(value))
    return values


def _first_nonzero(*values: int) -> int:
    return next((value for value in values if value), 0)


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
