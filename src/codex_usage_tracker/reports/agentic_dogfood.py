"""Repeatable local dogfood harness for agentic MCP investigation reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance_intelligence import build_allowance_diagnostics_report
from codex_usage_tracker.core.api_payloads import refresh_result_payload
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.reports.api import (
    build_agentic_investigation_report,
    build_hypothesis_test_report,
    build_investigation_suggestions_report,
    build_large_low_output_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.store.api import refresh_usage_index

DEFAULT_AGENTIC_DOGFOOD_DIR = DEFAULT_DB_PATH.parent / "agentic-dogfood"

OLD_AGENTIC_HYPOTHESES = [
    "Token waste is concentrated in obvious high-token low-output calls.",
    "Cache misses and cold resumes are inflating large calls.",
    "Repeated file rediscovery is causing avoidable rereads.",
    "Shell churn from repeated sed, rg, git, and nl sequences is wasting turns and tokens.",
    "Model or effort choice is driving a disproportionate share of usage.",
    "Weekly allowance changed recently.",
]

NEW_AGENTIC_HYPOTHESES = [
    "Large low-output calls are the highest-leverage near-term cleanup target.",
    "Repeated file rediscovery is concentrated in a small number of safe file identities.",
    "Shell churn is mostly repeated search/read command probing rather than productive modification.",
    "Recent context pressure, not output length, is driving the largest expensive calls.",
    "The MCP needs local content-index or thread-trace follow-up to explain intent behind repeated reads.",
    "Allowance-change claims are not ready for public posting without more weekly positive spans.",
]

EXPECTED_OLD_FAMILIES = [
    "token_waste",
    "cache_failure",
    "repeated_file_rediscovery",
    "shell_churn",
    "effort_model_choice",
    "allowance_change",
]

EXPECTED_NEW_FAMILIES = [
    "token_waste",
    "repeated_file_rediscovery",
    "shell_churn",
    "token_waste",
    "repeated_file_rediscovery",
    "allowance_change",
]


def build_agentic_dogfood_report(
    *,
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    projects_path: Path = DEFAULT_PROJECTS_PATH,
    output_dir: Path = DEFAULT_AGENTIC_DOGFOOD_DIR,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "strict",
    refresh: bool = True,
    write_markdown: bool = True,
) -> dict[str, Any]:
    """Run the repeatable agentic MCP dogfood battery and write compact artifacts."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = max(1, evidence_limit)
    output_dir.mkdir(parents=True, exist_ok=True)

    refresh_payload: dict[str, Any] | None = None
    if refresh:
        refresh_result = refresh_usage_index(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=include_archived,
            aggregate_only=False,
        )
        refresh_payload = refresh_result_payload(
            refresh_result,
            schema="codex-usage-tracker-refresh-v1",
        )

    old_hypotheses = build_hypothesis_test_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        question="Re-test prior usage-efficiency hypotheses against current local aggregate data.",
        hypotheses=OLD_AGENTIC_HYPOTHESES,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=normalized_limit,
        privacy_mode=privacy_mode,
    ).payload
    new_hypotheses = build_hypothesis_test_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        question=(
            "Test newer MCP investigation hypotheses around repeated files, shell churn, "
            "local evidence, and allowance readiness."
        ),
        hypotheses=NEW_AGENTIC_HYPOTHESES,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=normalized_limit,
        privacy_mode=privacy_mode,
    ).payload

    large_low_output = build_large_low_output_report(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=normalized_limit,
        privacy_mode=privacy_mode,
    ).payload
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
    repeated_files = build_repeated_file_rediscovery_report(
        db_path=db_path,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=2,
        limit=normalized_limit,
        privacy_mode=privacy_mode,
    ).payload
    allowance = build_allowance_diagnostics_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        limit=50,
        privacy_mode=privacy_mode,
    ).payload
    suggestions = build_investigation_suggestions_report(
        goal=None,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=10,
        privacy_mode=privacy_mode,
    ).payload
    token_waste = build_agentic_investigation_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        goal="token_waste",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=normalized_limit,
        detail_mode="compact",
        privacy_mode=privacy_mode,
    ).payload
    workflow_churn = build_agentic_investigation_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        projects_path=projects_path,
        goal="workflow_churn",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=normalized_limit,
        detail_mode="compact",
        privacy_mode=privacy_mode,
    ).payload

    payload = _compact_dogfood_payload(
        refresh=refresh_payload,
        output_dir=output_dir,
        old_hypotheses=old_hypotheses,
        new_hypotheses=new_hypotheses,
        large_low_output=large_low_output,
        shell_churn=shell_churn,
        repeated_files=repeated_files,
        allowance=allowance,
        suggestions=suggestions,
        token_waste=token_waste,
        workflow_churn=workflow_churn,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=normalized_limit,
        privacy_mode=privacy_mode,
    )

    json_path = output_dir / "summary.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifacts"]["summary_json_path"] = str(json_path)
    if write_markdown:
        markdown_path = output_dir / "summary.md"
        markdown_path.write_text(render_agentic_dogfood_markdown(payload), encoding="utf-8")
        payload["artifacts"]["summary_markdown_path"] = str(markdown_path)
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _compact_dogfood_payload(
    *,
    refresh: dict[str, Any] | None,
    output_dir: Path,
    old_hypotheses: dict[str, Any],
    new_hypotheses: dict[str, Any],
    large_low_output: dict[str, Any],
    shell_churn: dict[str, Any],
    repeated_files: dict[str, Any],
    allowance: dict[str, Any],
    suggestions: dict[str, Any],
    token_waste: dict[str, Any],
    workflow_churn: dict[str, Any],
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    old_summary = _compact_hypotheses(old_hypotheses)
    new_summary = _compact_hypotheses(new_hypotheses)
    payload: dict[str, Any] = {
        "schema": "codex-usage-tracker-agentic-dogfood-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "content_mode": "compact_aggregate_dogfood_summary",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": evidence_limit,
        },
        "refresh": refresh,
        "summary": {
            "old_hypothesis_count": len(old_summary),
            "new_hypothesis_count": len(new_summary),
            "large_low_output_candidates": large_low_output.get("total_candidates"),
            "shell_churn_candidates": shell_churn.get("total_candidates"),
            "repeated_file_candidates": repeated_files.get("total_candidates"),
            "allowance_primary_evidence_grade": (allowance.get("summary") or {}).get(
                "primary_evidence_grade"
            ),
        },
        "family_checks": {
            "old_expected": EXPECTED_OLD_FAMILIES,
            "old_actual": [row["family"] for row in old_summary],
            "old_passed": [row["family"] for row in old_summary] == EXPECTED_OLD_FAMILIES,
            "new_expected": EXPECTED_NEW_FAMILIES,
            "new_actual": [row["family"] for row in new_summary],
            "new_passed": [row["family"] for row in new_summary] == EXPECTED_NEW_FAMILIES,
        },
        "old_hypotheses": old_summary,
        "new_hypotheses": new_summary,
        "direct_reports": {
            "large_low_output": _compact_large_low_output(large_low_output),
            "shell_churn": _compact_shell_churn(shell_churn),
            "repeated_files": _compact_repeated_files(repeated_files),
            "allowance": _compact_allowance(allowance),
        },
        "suggestion_goals": [
            row.get("goal") for row in suggestions.get("suggestions", []) if row.get("goal")
        ],
        "investigation_findings": {
            "token_waste": [finding.get("finding") for finding in token_waste.get("findings", [])],
            "workflow_churn": [
                finding.get("finding") for finding in workflow_churn.get("findings", [])
            ],
        },
        "privacy_checks": _privacy_checks(
            [
                old_hypotheses,
                new_hypotheses,
                large_low_output,
                shell_churn,
                repeated_files,
                allowance,
                suggestions,
                token_waste,
                workflow_churn,
            ],
        ),
        "artifacts": {
            "output_dir": str(output_dir),
            "summary_json_path": None,
            "summary_markdown_path": None,
        },
        "caveats": [
            "Compact dogfood artifacts summarize local aggregate reports only.",
            "Associated token totals are evidence of where usage occurred, not guaranteed recoverable savings.",
            "Allowance diagnostics are local evidence, not an official OpenAI ledger.",
        ],
    }
    return payload


def _compact_hypotheses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for hypothesis in payload.get("hypotheses", []):
        summary = hypothesis.get("evidence_summary") or {}
        compact.append(
            {
                "hypothesis": hypothesis.get("hypothesis"),
                "family": hypothesis.get("family"),
                "status": hypothesis.get("status"),
                "confidence": hypothesis.get("confidence"),
                "row_count": summary.get("row_count"),
                "total_tokens": summary.get("total_tokens"),
                "max_total_tokens": summary.get("max_total_tokens"),
                "candidate_count": summary.get("large_low_output_candidate_count")
                or summary.get("candidate_count")
                or summary.get("recommendation_count"),
                "candidate_explanations": summary.get("candidate_explanations"),
                "missing_access": hypothesis.get("i_am_missing_access_to"),
                "next_action": hypothesis.get("next_action"),
                "recommended_next_tools": _tool_names(hypothesis.get("recommended_next_tools")),
            }
        )
    return compact


def _compact_large_low_output(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": payload.get("row_count"),
        "total_candidates": payload.get("total_candidates"),
        "top": [
            {
                "total_tokens": row.get("total_tokens"),
                "uncached_input_tokens": row.get("uncached_input_tokens"),
                "output_tokens": row.get("output_tokens"),
                "cache_ratio": row.get("cache_ratio"),
                "context_window_percent": row.get("context_window_percent"),
                "candidate_explanation": row.get("candidate_explanation"),
                "explanation_reasons": row.get("explanation_reasons"),
            }
            for row in payload.get("rows", [])
        ],
    }


def _compact_shell_churn(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": payload.get("row_count"),
        "total_candidates": payload.get("total_candidates"),
        "top": [
            {
                "command_root": row.get("command_root"),
                "command_family": row.get("command_family"),
                "churn_kind": row.get("churn_kind"),
                "occurrences": row.get("occurrences"),
                "call_count": row.get("call_count"),
                "failure_count": row.get("failure_count"),
                "distinct_label_count": row.get("distinct_label_count"),
                "recommendation": row.get("recommendation"),
            }
            for row in payload.get("rows", [])
        ],
    }


def _compact_repeated_files(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": payload.get("row_count"),
        "total_candidates": payload.get("total_candidates"),
        "top": [
            {
                "path_basename": row.get("path_basename"),
                "path_extension": row.get("path_extension"),
                "candidate_kind": row.get("candidate_kind"),
                "occurrences": row.get("occurrences"),
                "call_count": row.get("call_count"),
                "total_tokens": row.get("total_tokens"),
                "operation_mix": row.get("operation_mix"),
                "recommendation": row.get("recommendation"),
            }
            for row in payload.get("rows", [])
        ],
    }


def _compact_allowance(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    readiness = summary.get("research_readiness") or {}
    return {
        "observation_count": summary.get("observation_count"),
        "weekly_observation_count": summary.get("weekly_observation_count"),
        "five_hour_observation_count": summary.get("five_hour_observation_count"),
        "candidate_change_count": summary.get("candidate_change_count"),
        "primary_evidence_grade": summary.get("primary_evidence_grade"),
        "ready_for_public_claim": readiness.get("ready_for_public_claim"),
        "reasons": readiness.get("reasons"),
    }


def _privacy_checks(source_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    raw_fragment_sources = [
        payload.get("schema")
        for payload in source_payloads
        if bool(payload.get("includes_raw_fragments"))
    ]
    raw_json = json.dumps(source_payloads, default=str)
    forbidden_markers = {
        "raw_command": "raw_command",
        "raw_tool_output": "raw_tool_output",
        "full_path": "full_path",
        "source_file": "source_file",
    }
    marker_hits = sorted(marker for marker in forbidden_markers if marker in raw_json)
    return {
        "source_payload_count": len(source_payloads),
        "raw_fragment_sources": raw_fragment_sources,
        "raw_fragment_check_passed": not raw_fragment_sources,
        "compact_summary_includes_indexed_content": False,
        "compact_summary_includes_raw_fragments": False,
        "forbidden_marker_hits": marker_hits,
        "forbidden_marker_check_passed": not marker_hits,
        "passed": not raw_fragment_sources and not marker_hits,
    }


def _tool_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            tool = item.get("tool") or item.get("name")
            if isinstance(tool, str):
                names.append(tool)
    return names


def render_agentic_dogfood_markdown(payload: dict[str, Any]) -> str:
    """Render a compact Markdown artifact from a dogfood payload."""

    lines = [
        "# Agentic Dogfood Summary",
        "",
        f"Generated: {payload.get('generated_at')}",
        f"Privacy mode: `{payload.get('privacy_mode')}`",
        f"Include archived: `{payload.get('filters', {}).get('include_archived')}`",
        "",
        "## Family Checks",
        "",
        f"- Old hypotheses: `{payload['family_checks']['old_passed']}`",
        f"- New hypotheses: `{payload['family_checks']['new_passed']}`",
        "",
        "## Old Hypotheses",
        "",
        *_hypothesis_lines(payload.get("old_hypotheses", [])),
        "",
        "## New Hypotheses",
        "",
        *_hypothesis_lines(payload.get("new_hypotheses", [])),
        "",
        "## Direct Evidence",
        "",
        f"- Large low-output candidates: {payload['summary'].get('large_low_output_candidates')}",
        f"- Shell churn candidates: {payload['summary'].get('shell_churn_candidates')}",
        f"- Repeated file candidates: {payload['summary'].get('repeated_file_candidates')}",
        (
            "- Allowance evidence grade: "
            f"{payload['summary'].get('allowance_primary_evidence_grade')}"
        ),
        "",
        "## Privacy Checks",
        "",
        f"- Passed: `{payload['privacy_checks'].get('passed')}`",
        f"- Forbidden marker hits: {payload['privacy_checks'].get('forbidden_marker_hits')}",
    ]
    return "\n".join(lines) + "\n"


def _hypothesis_lines(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"- **{row.get('family')}**: {row.get('status')} ({row.get('confidence')})"
        for row in rows
    ]
