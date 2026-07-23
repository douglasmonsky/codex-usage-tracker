"""Stable CLI and MCP catalogs shared by release-contract tests."""

CANONICAL_PACKAGE_DESCRIPTION = (
    "Local, evidence-backed Codex usage analyst with MCP tools and an Evidence Console."
)

CANONICAL_DATA_POSTURE = (
    "Normal refresh indexes aggregate counters and the existing bounded local "
    "content/event index; aggregate-only commands retain the older posture; "
    "shareable outputs follow existing behavior."
)

FORBIDDEN_DASHBOARD_DEPENDENCIES = {"three", "@types/three"}
FORBIDDEN_CONSTELLATION_PATHS = {
    "frontend/dashboard/src/features/overview/usageConstellationModel.ts",
    "frontend/dashboard/src/features/overview/usageConstellationModel.test.ts",
    "frontend/dashboard/src/visualization/three",
    "tests/playwright/dashboard-constellation.spec.mjs",
}
MAX_INITIAL_DASHBOARD_JS_KIB = 67

CORE_MCP_TOOL_NAMES = (
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)

DEVELOPER_MCP_TOOL_NAMES = {
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_visualization_suggest",
    "usage_visualization_render",
}

STABLE_CLI_COMMANDS = {
    "setup",
    "status",
    "doctor",
    "refresh",
    "analyze",
    "query",
    "open",
    "export",
    "config",
    "service",
    "admin",
}

MCP_TOOL_NAMES = {
    "subagent_usage",
    "refresh_usage_index",
    "usage_refresh_start",
    "usage_refresh_status",
    "usage_doctor",
    "usage_summary",
    "usage_query",
    "usage_status",
    "usage_dedupe_diagnostics",
    "usage_calls",
    "usage_call_detail",
    "usage_threads",
    "usage_report_pack",
    "usage_dashboard_recommendations",
    "usage_allowance_history",
    "usage_allowance_diagnostics",
    "usage_allowance_export",
    "usage_allowance_status",
    "usage_allowance_series",
    "usage_allowance_evidence",
    "usage_allowance_analysis",
    "usage_allowance_analysis_status",
    "usage_compression_start",
    "usage_compression_status",
    "usage_compression_profile",
    "usage_compression_candidates",
    "usage_compression_candidate_detail",
    "usage_compression_simulate",
    "usage_recommendations",
    "session_usage",
    "usage_call_context",
    "most_expensive_usage_calls",
    "usage_pricing_coverage",
    "usage_source_coverage",
    "usage_content_search",
    "usage_thread_trace",
    "usage_repetition_scan",
    "usage_command_loop_scan",
    "usage_file_churn_scan",
    "usage_repeated_file_rediscovery",
    "usage_shell_churn",
    "usage_large_low_output_calls",
    "usage_suggest_investigations",
    "usage_investigate",
    "usage_action_brief",
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_test_hypotheses",
    "usage_context_bloat_scan",
    "usage_investigation_walk",
    "usage_local_evidence_export",
    "generate_usage_dashboard",
    "export_usage_csv",
    "init_usage_pricing_config",
    "update_usage_pricing_config",
    "init_usage_allowance_config",
} | {"usage_visualization_suggest", "usage_visualization_render"}

ADVANCED_MCP_TOOL_NAMES = {
    "usage_dedupe_diagnostics",
    "usage_allowance_export",
    "usage_call_context",
    "usage_content_search",
    "usage_thread_trace",
    "usage_local_evidence_export",
    "export_usage_csv",
}

FULL_MCP_TOOL_NAMES = (MCP_TOOL_NAMES - DEVELOPER_MCP_TOOL_NAMES) | set(CORE_MCP_TOOL_NAMES)
ALL_MCP_TOOL_NAMES = MCP_TOOL_NAMES | set(CORE_MCP_TOOL_NAMES)

MCP_PROFILE_TOOL_COUNTS = {
    "core": len(CORE_MCP_TOOL_NAMES),
    "full": len(FULL_MCP_TOOL_NAMES),
    "developer": len(ALL_MCP_TOOL_NAMES),
}

RELEASE_022_SCHEMA_IDS = {
    "codex-usage-tracker-dashboard-target-v2",
    "codex-usage-tracker.accounting-context.v1",
    "codex-usage-tracker.analysis-job.v1",
    "codex-usage-tracker.analysis.v2",
    "codex-usage-tracker.evidence-result.v1",
    "codex-usage-tracker.evidence.v1",
    "codex-usage-tracker.finding.v1",
    "codex-usage-tracker.freshness.v1",
    "codex-usage-tracker.mcp-envelope.v1",
    "codex-usage-tracker.message.v1",
    "codex-usage-tracker.next-action.v1",
    "codex-usage-tracker.query.v2",
    "codex-usage-tracker.recommendation.v1",
    "codex-usage-tracker.scope.v1",
}
