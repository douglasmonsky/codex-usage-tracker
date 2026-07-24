"""Repeatable local dogfood harness for agentic MCP investigation reports."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance_intelligence import build_allowance_diagnostics_report
from codex_usage_tracker.allowance_intelligence.materialization import (
    sync_refresh_allowance_intelligence,
)
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
from codex_usage_tracker.reports.agentic_dogfood_markdown import (
    render_agentic_dogfood_markdown,
)
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_agentic_investigation_report,
    build_hypothesis_test_report,
    build_investigation_suggestions_report,
    build_large_low_output_report,
    build_recommendations_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
)
from codex_usage_tracker.store.api import refresh_usage_index as _refresh_usage_index

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
    run_hypotheses: bool = False,
    run_deep_investigations: bool = False,
    write_markdown: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the repeatable agentic MCP dogfood battery and write compact artifacts."""

    privacy_mode = validate_privacy_mode(privacy_mode)
    normalized_limit = max(1, evidence_limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_stages: list[dict[str, Any]] = []
    report_cache: dict[str, dict[str, Any]] = {}

    def record_stage(stage: dict[str, Any]) -> None:
        progress_stages.append(stage)
        if progress_callback is not None:
            progress_callback(stage)

    refresh_payload: dict[str, Any] | None = None
    if refresh:
        refresh_result = _refresh_usage_index(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=include_archived,
            aggregate_only=False,
            derived_fact_sync=sync_refresh_allowance_intelligence,
        )
        refresh_payload = refresh_result_payload(
            refresh_result,
            schema="codex-usage-tracker-refresh-v1",
        )
    record_stage(_dogfood_stage("refresh", 10, completed=True, skipped=not refresh))

    if run_hypotheses:
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
    else:
        old_hypotheses = _lightweight_hypothesis_payload(
            OLD_AGENTIC_HYPOTHESES,
            EXPECTED_OLD_FAMILIES,
            question="Re-test prior usage-efficiency hypotheses against current local aggregate data.",
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=normalized_limit,
            privacy_mode=privacy_mode,
        )
        new_hypotheses = _lightweight_hypothesis_payload(
            NEW_AGENTIC_HYPOTHESES,
            EXPECTED_NEW_FAMILIES,
            question=(
                "Test newer MCP investigation hypotheses around repeated files, shell churn, "
                "local evidence, and allowance readiness."
            ),
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            evidence_limit=normalized_limit,
            privacy_mode=privacy_mode,
        )
    record_stage(_dogfood_stage("old_hypotheses", 25, completed=True, skipped=not run_hypotheses))
    record_stage(_dogfood_stage("new_hypotheses", 40, completed=True, skipped=not run_hypotheses))

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
    report_cache["repeated_files"] = repeated_files
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
        source_limit=max(200, normalized_limit * 100),
        privacy_mode=privacy_mode,
    ).payload
    report_cache["recommendations"] = recommendations
    record_stage(_dogfood_stage("direct_reports", 60, completed=True))
    action_brief = build_action_brief_report(
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
        privacy_mode=privacy_mode,
        precomputed_reports=report_cache,
    ).payload
    report_cache["action_brief"] = action_brief
    record_stage(
        _dogfood_stage("action_brief", 70, completed=True, cache_keys=sorted(report_cache))
    )
    allowance = build_allowance_diagnostics_report(
        db_path=db_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        include_archived=include_archived,
        limit=50,
        privacy_mode=privacy_mode,
    ).payload
    record_stage(_dogfood_stage("allowance", 78, completed=True))
    suggestions = build_investigation_suggestions_report(
        goal=None,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=10,
        privacy_mode=privacy_mode,
    ).payload
    record_stage(_dogfood_stage("suggestions", 84, completed=True))
    if run_deep_investigations:
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
    else:
        token_waste = _lightweight_investigation_from_action_brief(
            action_brief,
            goal="token_waste",
            families=None,
        )
        workflow_churn = _lightweight_investigation_from_action_brief(
            action_brief,
            goal="workflow_churn",
            families={"repeated_file_rediscovery", "shell_churn"},
        )
    record_stage(
        _dogfood_stage(
            "investigation_findings",
            92,
            completed=True,
            skipped=not run_deep_investigations,
            source="deep_investigations" if run_deep_investigations else "reused_action_brief",
        )
    )

    payload = _compact_dogfood_payload(
        refresh=refresh_payload,
        output_dir=output_dir,
        progress_stages=progress_stages,
        report_cache=report_cache,
        run_hypotheses=run_hypotheses,
        run_deep_investigations=run_deep_investigations,
        old_hypotheses=old_hypotheses,
        new_hypotheses=new_hypotheses,
        large_low_output=large_low_output,
        shell_churn=shell_churn,
        repeated_files=repeated_files,
        action_brief=action_brief,
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
    if progress_callback is not None:
        progress_callback(_dogfood_stage("write_artifacts", 100, completed=True))
    return payload


def _compact_dogfood_payload(
    *,
    refresh: dict[str, Any] | None,
    output_dir: Path,
    progress_stages: list[dict[str, Any]],
    report_cache: dict[str, dict[str, Any]],
    run_hypotheses: bool,
    run_deep_investigations: bool,
    old_hypotheses: dict[str, Any],
    new_hypotheses: dict[str, Any],
    large_low_output: dict[str, Any],
    shell_churn: dict[str, Any],
    repeated_files: dict[str, Any],
    action_brief: dict[str, Any],
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
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
        "progress": {
            "mode": "synchronous_staged",
            "percent_complete": 100,
            "stages": [*progress_stages, _dogfood_stage("write_artifacts", 100, completed=True)],
            "polling_note": (
                "This synchronous CLI/MCP payload reports completed stages after return. "
                "Live percent updates require an async job endpoint."
            ),
        },
        "cache": {
            "scope": "single_run_shared_reports",
            "cache_keys": sorted(report_cache),
            "hypotheses": run_hypotheses,
            "deep_investigations": run_deep_investigations,
        },
        "summary": _dogfood_summary(
            old_summary=old_summary,
            new_summary=new_summary,
            large_low_output=large_low_output,
            shell_churn=shell_churn,
            repeated_files=repeated_files,
            action_brief=action_brief,
            allowance=allowance,
        ),
        "family_checks": _family_checks(old_summary, new_summary),
        "old_hypotheses": old_summary,
        "new_hypotheses": new_summary,
        "direct_reports": {
            "large_low_output": _compact_large_low_output(large_low_output),
            "shell_churn": _compact_shell_churn(shell_churn),
            "repeated_files": _compact_repeated_files(repeated_files),
            "action_brief": _compact_action_brief(action_brief),
            "allowance": _compact_allowance(allowance),
        },
        "suggestion_goals": _non_null_values(suggestions.get("suggestions", []), "goal"),
        "investigation_findings": {
            "token_waste": _values(token_waste.get("findings", []), "finding"),
            "workflow_churn": _values(workflow_churn.get("findings", []), "finding"),
        },
        "privacy_checks": _privacy_checks(
            [
                old_hypotheses,
                new_hypotheses,
                large_low_output,
                shell_churn,
                repeated_files,
                action_brief,
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


def _dogfood_summary(
    *,
    old_summary: list[dict[str, Any]],
    new_summary: list[dict[str, Any]],
    large_low_output: dict[str, Any],
    shell_churn: dict[str, Any],
    repeated_files: dict[str, Any],
    action_brief: dict[str, Any],
    allowance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "old_hypothesis_count": len(old_summary),
        "new_hypothesis_count": len(new_summary),
        "large_low_output_candidates": large_low_output.get("total_candidates"),
        "shell_churn_candidates": shell_churn.get("total_candidates"),
        "repeated_file_candidates": repeated_files.get("total_candidates"),
        "action_brief_actions": len(action_brief.get("actions") or []),
        "allowance_primary_evidence_grade": (allowance.get("summary") or {}).get(
            "primary_evidence_grade"
        ),
    }


def _family_checks(
    old_summary: list[dict[str, Any]], new_summary: list[dict[str, Any]]
) -> dict[str, Any]:
    old_actual = [row["family"] for row in old_summary]
    new_actual = [row["family"] for row in new_summary]
    return {
        "old_expected": EXPECTED_OLD_FAMILIES,
        "old_actual": old_actual,
        "old_passed": old_actual == EXPECTED_OLD_FAMILIES,
        "new_expected": EXPECTED_NEW_FAMILIES,
        "new_actual": new_actual,
        "new_passed": new_actual == EXPECTED_NEW_FAMILIES,
    }


def _non_null_values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row[field] for row in rows if row.get(field) is not None]


def _values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row.get(field) for row in rows]


def _dogfood_stage(
    stage: str,
    percent: int,
    *,
    completed: bool,
    skipped: bool = False,
    source: str | None = None,
    cache_keys: list[str] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "stage": stage,
        "percent": percent,
        "status": "skipped" if skipped else "completed" if completed else "pending",
    }
    if source is not None:
        row["source"] = source
    if cache_keys is not None:
        row["cache_keys"] = cache_keys
    return row


def _lightweight_hypothesis_payload(
    hypotheses: list[str],
    families: list[str],
    *,
    question: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for hypothesis, family in zip(hypotheses, families, strict=True):
        rows.append(
            {
                "hypothesis": hypothesis,
                "family": family,
                "status": "skipped_quick_mode",
                "confidence": "not_evaluated",
                "row_count": None,
                "total_tokens": None,
                "max_total_tokens": None,
                "candidate_count": None,
                "evidence_summary": {},
                "evidence": [],
                "counter_evidence": [],
                "i_would_like_to_be_able_to": (
                    "Keep the agentic dogfood flow fast enough to run on large local datasets."
                ),
                "i_will_accomplish_this_using": (
                    "Family-routing checks plus shared reports instead of full evidence scans."
                ),
                "i_am_missing_access_to": (
                    "Full hypothesis evidence because quick dogfood mode intentionally skipped it."
                ),
                "next_action": (
                    "Run `codex-usage-tracker dogfood-agentic --hypotheses` "
                    "to evaluate this hypothesis battery."
                ),
                "recommended_next_tools": [],
                "missing_access": (
                    "Quick dogfood mode skipped expensive hypothesis evidence scans."
                ),
            }
        )
    return {
        "schema": "codex-usage-tracker-hypothesis-test-v1",
        "content_mode": "aggregate_hypothesis_routing_quick_check",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "question": question,
        "filters": {
            "since": since,
            "until": until,
            "thread": thread,
            "include_archived": include_archived,
            "evidence_limit": evidence_limit,
        },
        "summary": {
            "hypothesis_count": len(rows),
            "status_counts": {"skipped_quick_mode": len(rows)} if rows else {},
            "top_status": rows[0]["status"] if rows else None,
        },
        "hypotheses": rows,
        "recommended_next_tools": [],
        "caveats": [
            "Quick dogfood mode checks hypothesis routing and family coverage only; use --hypotheses for full evidence evaluation."
        ],
    }


def _lightweight_investigation_from_action_brief(
    action_brief: dict[str, Any],
    *,
    goal: str,
    families: set[str] | None,
) -> dict[str, Any]:
    actions = [
        action
        for action in action_brief.get("actions", [])
        if families is None or str(action.get("family")) in families
    ]
    findings = [
        {
            "finding": action.get("finding"),
            "confidence": action.get("confidence"),
            "evidence_count": action.get("evidence_count"),
            "recommended_action": action.get("recommended_workflow_change"),
            "verify_with": action.get("recommended_next_tools"),
            "source_action_family": action.get("family"),
        }
        for action in actions
    ]
    return {
        "schema": "codex-usage-tracker-agentic-investigation-v1",
        "content_mode": "aggregate_investigation_reused_action_brief",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": action_brief.get("privacy_mode"),
        "goal": goal,
        "summary": {
            "finding_count": len(findings),
            "top_finding": findings[0]["finding"] if findings else None,
            "source_reports": ["codex-usage-tracker-action-brief-v1"],
        },
        "findings": findings,
        "recommended_next_tools": action_brief.get("recommended_next_tools", []),
        "caveats": [
            "Reused action brief findings to keep dogfood bounded; run with deep investigations for full investigation payloads."
        ],
    }


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


def _compact_action_brief(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal": payload.get("goal"),
        "action_count": (payload.get("summary") or {}).get("action_count"),
        "top_action_family": (payload.get("summary") or {}).get("top_action_family"),
        "actions": [
            {
                "family": row.get("family"),
                "finding": row.get("finding"),
                "confidence": row.get("confidence"),
                "evidence_count": row.get("evidence_count"),
                "recommended_next_tools": row.get("recommended_next_tools"),
            }
            for row in payload.get("actions", [])
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
