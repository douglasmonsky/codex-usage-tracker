"""Explicit MCP work-proof contracts for each tool's JSON response shape."""

from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.models import (
    WorkProofContract,
    WorkProofKind,
)


def _measured(
    kind: WorkProofKind,
    processed_field: str,
    applicability_field: str | None = None,
) -> WorkProofContract:
    return WorkProofContract(kind, 1, applicability_field, processed_field)


CONSTANT_STATUS = WorkProofContract("constant", 0, None, None)

# Paths are relative to the JSON value returned by the handler. Compatibility
# tools that also render Markdown use their explicit ``response_format="json"``
# representation because that is the machine-verifiable form.
WORK_PROOFS: dict[str, WorkProofContract] = {
    # Stable core envelopes.
    "usage_status": CONSTANT_STATUS,
    "usage_refresh": _measured(
        "sources",
        "result.refresh.scanned_files",
        "result.planner.changed_source_files",
    ),
    "usage_analyze": _measured("evidence", "result.schema"),
    "usage_query": _measured("rows", "result.rows", "result.total_matched"),
    "usage_evidence": _measured("evidence", "result.records"),
    "usage_allowance": _measured("evidence", "result.schema"),
    "usage_job_status": _measured("job", "result.job_id"),
    # Compatibility discovery and dashboard payloads.
    "subagent_usage": _measured("rows", "summary.calls"),
    "refresh_usage_index": _measured("sources", "scanned_files"),
    "usage_refresh_start": _measured("job", "job_id"),
    "usage_refresh_status": _measured("job", "job_id"),
    "usage_doctor": CONSTANT_STATUS,
    "usage_summary": _measured("rows", "rows", "row_count"),
    "usage_dedupe_diagnostics": CONSTANT_STATUS,
    "usage_calls": _measured("rows", "rows", "total_matched_rows"),
    "usage_call_detail": _measured("evidence", "record"),
    "usage_threads": _measured("rows", "rows", "total_matched_rows"),
    "usage_report_pack": _measured("evidence", "evidence"),
    "usage_dashboard_recommendations": _measured("rows", "rows", "row_count"),
    # Allowance compatibility payloads.
    "usage_allowance_history": _measured("rows", "rows", "row_count"),
    "usage_allowance_diagnostics": _measured(
        "evidence",
        "windows",
        "summary.observation_count",
    ),
    "usage_allowance_export": _measured(
        "evidence",
        "windows",
        "summary.observation_count",
    ),
    "usage_allowance_status": CONSTANT_STATUS,
    "usage_allowance_series": _measured("rows", "points", "points"),
    "usage_allowance_evidence": _measured("evidence", "rows", "rows"),
    "usage_allowance_analysis": _measured("job", "status"),
    "usage_allowance_analysis_status": _measured("job", "job_id"),
    # Persisted Compression Lab work.
    "usage_compression_start": _measured("job", "run_id"),
    "usage_compression_status": _measured("job", "run_id"),
    "usage_compression_profile": _measured("evidence", "profile"),
    "usage_compression_candidates": _measured(
        "rows",
        "candidates",
        "pagination.total",
    ),
    "usage_compression_candidate_detail": _measured("evidence", "candidate"),
    "usage_compression_simulate": _measured(
        "evidence",
        "simulation.candidates",
        "simulation.candidate_count",
    ),
    # Aggregate and local-index compatibility reports.
    "usage_recommendations": _measured("rows", "rows", "row_count"),
    "session_usage": _measured("rows", "rows", "row_count"),
    "usage_call_context": _measured("evidence", "record_id"),
    "most_expensive_usage_calls": _measured("rows", "rows", "row_count"),
    "usage_pricing_coverage": _measured("rows", "rows", "model_count"),
    "usage_source_coverage": _measured("sources", "rows", "source_file_count"),
    "usage_content_search": _measured("rows", "rows", "total_matched_rows"),
    "usage_thread_trace": _measured("rows", "calls", "total_matched_calls"),
    "usage_repetition_scan": _measured("rows", "patterns", "total_patterns"),
    "usage_command_loop_scan": _measured("rows", "patterns", "total_patterns"),
    "usage_file_churn_scan": _measured("rows", "patterns", "total_patterns"),
    "usage_repeated_file_rediscovery": _measured(
        "rows",
        "rows",
        "total_candidates",
    ),
    "usage_shell_churn": _measured("rows", "rows", "total_candidates"),
    "usage_large_low_output_calls": _measured(
        "rows",
        "rows",
        "total_candidates",
    ),
    "usage_suggest_investigations": _measured(
        "evidence",
        "suggestions",
        "summary.total_suggestions",
    ),
    "usage_investigate": _measured(
        "evidence",
        "findings",
        "summary.finding_count",
    ),
    "usage_action_brief": _measured(
        "evidence",
        "actions",
        "summary.action_count",
    ),
    "usage_test_hypotheses": _measured(
        "evidence",
        "hypotheses",
        "summary.hypothesis_count",
    ),
    "usage_context_bloat_scan": _measured("rows", "patterns", "total_patterns"),
    "usage_investigation_walk": _measured(
        "evidence",
        "branches",
        "summary.branch_count",
    ),
    "usage_local_evidence_export": _measured(
        "evidence",
        "branches",
        "summary.export_branch_count",
    ),
    # Local file and configuration operations prove their concrete output.
    "generate_usage_dashboard": _measured("evidence", "dashboard_path"),
    "export_usage_csv": _measured("rows", "rows"),
    "init_usage_pricing_config": _measured("evidence", "pricing_path"),
    "update_usage_pricing_config": _measured("rows", "model_count"),
    "init_usage_allowance_config": _measured("evidence", "allowance_path"),
    # Dogfood and visualization developer tools.
    "usage_dogfood_start": _measured("job", "job_id"),
    "usage_dogfood_status": _measured("job", "job_id"),
    "usage_dogfood_result": _measured("evidence", "schema"),
    "usage_visualization_suggest": _measured(
        "evidence",
        "suggestions",
        "summary.suggestion_count",
    ),
    "usage_visualization_render": _measured(
        "evidence",
        "evidence.rows",
        "evidence.row_count",
    ),
}
