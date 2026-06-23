from __future__ import annotations

import json
from pathlib import Path

import pytest
from store_dashboard_helpers import (
    _extract_js_function,
    _make_codex_home,
    _write_pricing,
)

from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.store import (
    EVENT_COLUMNS,
    connect,
    export_usage_csv,
    refresh_usage_index,
)


def test_dashboard_and_csv_are_aggregate_only(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    dashboard_path = tmp_path / "dashboard.html"
    csv_path = tmp_path / "usage.csv"
    all_csv_path = tmp_path / "usage-all.csv"

    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)
    exported = export_usage_csv(output_path=csv_path, db_path=db_path)
    exported_with_zero_limit = export_usage_csv(output_path=all_csv_path, db_path=db_path, limit=0)

    dashboard = dashboard_path.read_text(encoding="utf-8")
    asset_dir = tmp_path / "codex-usage-tracker-assets"
    dashboard_js = (asset_dir / "dashboard.js").read_text(encoding="utf-8")
    dashboard_format_js = (asset_dir / "dashboard_format.js").read_text(encoding="utf-8")
    dashboard_data_js = (asset_dir / "dashboard_data.js").read_text(encoding="utf-8")
    dashboard_analysis_js = (asset_dir / "dashboard_analysis.js").read_text(encoding="utf-8")
    dashboard_cells_js = (asset_dir / "dashboard_cells.js").read_text(encoding="utf-8")
    dashboard_details_js = (asset_dir / "dashboard_details.js").read_text(encoding="utf-8")
    dashboard_insights_js = (asset_dir / "dashboard_insights.js").read_text(encoding="utf-8")
    dashboard_tables_js = (asset_dir / "dashboard_tables.js").read_text(encoding="utf-8")
    dashboard_filters_js = (asset_dir / "dashboard_filters.js").read_text(encoding="utf-8")
    dashboard_payload_cache_js = (asset_dir / "dashboard_payload_cache.js").read_text(
        encoding="utf-8"
    )
    dashboard_i18n_js = (asset_dir / "dashboard_i18n.js").read_text(encoding="utf-8")
    dashboard_tooltips_js = (asset_dir / "dashboard_tooltips.js").read_text(encoding="utf-8")
    dashboard_status_js = (asset_dir / "dashboard_status.js").read_text(encoding="utf-8")
    dashboard_actions_js = (asset_dir / "dashboard_actions.js").read_text(encoding="utf-8")
    dashboard_live_js = (asset_dir / "dashboard_live.js").read_text(encoding="utf-8")
    dashboard_events_js = (asset_dir / "dashboard_events.js").read_text(encoding="utf-8")
    dashboard_diagnostics_js = (asset_dir / "dashboard_diagnostics.js").read_text(
        encoding="utf-8"
    )
    dashboard_diagnostics_facts_js = (
        asset_dir / "dashboard_diagnostics_facts.js"
    ).read_text(encoding="utf-8")
    dashboard_diagnostics_snapshots_js = (
        asset_dir / "dashboard_diagnostics_snapshots.js"
    ).read_text(encoding="utf-8")
    dashboard_call_diagnostics_js = (
        asset_dir / "dashboard_call_diagnostics.js"
    ).read_text(encoding="utf-8")
    dashboard_call_js = (asset_dir / "dashboard_call_investigator.js").read_text(
        encoding="utf-8"
    )
    dashboard_state_js = (asset_dir / "dashboard_state.js").read_text(encoding="utf-8")
    dashboard_stylesheets = [
        "dashboard.css",
        "dashboard_call.css",
        "dashboard_insights.css",
        "dashboard_layout.css",
        "dashboard_tables.css",
        "dashboard_detail.css",
        "dashboard_responsive.css",
    ]
    dashboard_css = "\n".join(
        (asset_dir / stylesheet).read_text(encoding="utf-8")
        for stylesheet in dashboard_stylesheets
    )
    render_calls_js = _extract_js_function(dashboard_tables_js, "renderCalls")
    dashboard_surface = "\n".join([
        dashboard,
        dashboard_format_js,
        dashboard_data_js,
        dashboard_analysis_js,
        dashboard_cells_js,
        dashboard_details_js,
        dashboard_insights_js,
        dashboard_tables_js,
        dashboard_filters_js,
        dashboard_payload_cache_js,
        dashboard_i18n_js,
        dashboard_tooltips_js,
        dashboard_status_js,
        dashboard_actions_js,
        dashboard_live_js,
        dashboard_events_js,
        dashboard_diagnostics_js,
        dashboard_diagnostics_facts_js,
        dashboard_diagnostics_snapshots_js,
        dashboard_call_diagnostics_js,
        dashboard_call_js,
        dashboard_js,
        dashboard_state_js,
        dashboard_css,
    ])
    csv_text = csv_path.read_text(encoding="utf-8")
    assert exported == 4
    assert exported_with_zero_limit == 4
    assert "SECRET RAW PROMPT" not in dashboard
    assert "SECRET RAW PROMPT" not in dashboard_js
    assert "SECRET RAW PROMPT" not in dashboard_analysis_js
    assert "SECRET RAW PROMPT" not in dashboard_cells_js
    assert "SECRET RAW PROMPT" not in dashboard_details_js
    assert "SECRET RAW PROMPT" not in dashboard_insights_js
    assert "SECRET RAW PROMPT" not in dashboard_tables_js
    assert "SECRET RAW PROMPT" not in dashboard_filters_js
    assert "SECRET RAW PROMPT" not in dashboard_payload_cache_js
    assert "SECRET RAW PROMPT" not in dashboard_i18n_js
    assert "SECRET RAW PROMPT" not in dashboard_tooltips_js
    assert "SECRET RAW PROMPT" not in dashboard_status_js
    assert "SECRET RAW PROMPT" not in dashboard_actions_js
    assert "SECRET RAW PROMPT" not in dashboard_live_js
    assert "SECRET RAW PROMPT" not in dashboard_events_js
    assert "SECRET RAW PROMPT" not in dashboard_diagnostics_js
    assert "SECRET RAW PROMPT" not in dashboard_diagnostics_facts_js
    assert "SECRET RAW PROMPT" not in dashboard_diagnostics_snapshots_js
    assert "SECRET RAW PROMPT" not in dashboard_call_diagnostics_js
    assert "SECRET RAW PROMPT" not in dashboard_call_js
    assert "SECRET RAW PROMPT" not in dashboard_css
    assert "SECRET RAW PROMPT" not in csv_text
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_analysis_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_cells_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_details_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_insights_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_tables_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_filters_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_payload_cache_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_i18n_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_tooltips_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_status_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_actions_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_live_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_events_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_diagnostics_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_diagnostics_facts_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_diagnostics_snapshots_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_call_diagnostics_js
    assert "COMPACTED REPLACEMENT SUMMARY" not in dashboard_call_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_analysis_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_cells_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_details_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_insights_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_tables_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_filters_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_payload_cache_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_i18n_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_tooltips_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_status_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_actions_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_live_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_events_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_diagnostics_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_diagnostics_facts_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_diagnostics_snapshots_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_call_diagnostics_js
    assert "EVENT MSG COMPACTION SUMMARY" not in dashboard_call_js
    for stylesheet in dashboard_stylesheets:
        assert f'href="codex-usage-tracker-assets/{stylesheet}?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_format.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_data.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_analysis.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_cells.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_details.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_insights.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_tables.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_filters.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_state.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_payload_cache.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_i18n.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_tooltips.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_status.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_actions.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_live.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_events.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_diagnostics_snapshots.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_diagnostics_facts.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_diagnostics.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_call_diagnostics.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard_call_investigator.js?v=' in dashboard
    assert 'src="codex-usage-tracker-assets/dashboard.js?v=' in dashboard
    assert "CodexUsageDashboardFormat" in dashboard_format_js
    assert "CodexUsageDashboardData" in dashboard_data_js
    assert "CodexUsageDashboardAnalysis" in dashboard_analysis_js
    assert "CodexUsageDashboardCells" in dashboard_cells_js
    assert "CodexUsageDashboardDetails" in dashboard_details_js
    assert "CodexUsageDashboardInsights" in dashboard_insights_js
    assert "CodexUsageDashboardTables" in dashboard_tables_js
    assert "CodexUsageDashboardFilters" in dashboard_filters_js
    assert "CodexUsageDashboardState" in dashboard_state_js
    assert "CodexUsageDashboardPayloadCache" in dashboard_payload_cache_js
    assert "CodexUsageDashboardI18n" in dashboard_i18n_js
    assert "CodexUsageDashboardTooltips" in dashboard_tooltips_js
    assert "CodexUsageDashboardStatus" in dashboard_status_js
    assert "CodexUsageDashboardActions" in dashboard_actions_js
    assert "CodexUsageDashboardLive" in dashboard_live_js
    assert "CodexUsageDashboardEvents" in dashboard_events_js
    assert "CodexUsageDashboardDiagnosticSnapshots" in dashboard_diagnostics_snapshots_js
    assert "CodexUsageDashboardDiagnosticFacts" in dashboard_diagnostics_facts_js
    assert "CodexUsageDashboardDiagnostics" in dashboard_diagnostics_js
    assert "CodexUsageCallDiagnostics" in dashboard_call_diagnostics_js
    assert "CodexUsageCallInvestigator" in dashboard_call_js
    assert "copyViewLink" in dashboard
    assert "exportVisible" in dashboard
    assert "Copy link" in dashboard
    assert "Export CSV" in dashboard
    assert "currentDashboardState" in dashboard_actions_js
    assert "copyCurrentViewLink" in dashboard_actions_js
    assert "exportCurrentRows" in dashboard_actions_js
    assert "last call" in dashboard_surface.lower()
    assert "metric.session_cumulative" in dashboard_surface.lower()

    from codex_usage_tracker.i18n import translations_for
    en_trans = translations_for("en")
    assert "session cumulative" in en_trans["metric.session_cumulative"].lower()
    assert "Estimated Cost" in dashboard
    assert "estimated_cost_usd" in dashboard
    assert "pricing_snapshot" in dashboard
    assert "rates_fingerprint" in dashboard
    assert "Uncached Input" in dashboard
    assert "uncachedTokens" in dashboard
    assert "Codex Credits" in dashboard
    assert "Usage observed" in dashboard
    assert "Price Coverage" not in dashboard
    assert "priceCoverage" not in dashboard_surface
    assert "usageCredits" in dashboard
    assert "allowanceImpact" in dashboard
    assert "allowanceReconcile" in dashboard
    assert "observed_usage" in dashboard
    assert "observedUsageText" in dashboard_status_js
    assert "Read from the latest local Codex token-count log" in dashboard
    assert "not a live account query" in dashboard
    assert "usage_impact" not in dashboard_surface
    assert "UsageImpact" not in dashboard_surface
    assert "usage_credits" in dashboard
    assert "parser_diagnostics" in dashboard
    assert "parserDiagnostics" in dashboard_js
    assert "privacyMode" in dashboard
    assert "projectMetadataPrivacy" in dashboard_js
    assert "datePreset" in dashboard
    assert "dateStart" in dashboard
    assert "dateEnd" in dashboard
    assert "dateRangeStatus" in dashboard
    assert "Today" in dashboard
    assert "This week" in dashboard
    assert "Last 7 days" in dashboard
    assert "This month" in dashboard
    assert "Custom range" in dashboard
    assert "currentDateRange" in dashboard_js
    assert "rowMatchesDateRange" in dashboard_js
    assert "syncDatePresetInputs" in dashboard_js
    assert "datePreset: clean(params.get('date'))" in dashboard_state_js
    assert "dateStart: clean(params.get('from'))" in dashboard_state_js
    assert "dateEnd: clean(params.get('to'))" in dashboard_state_js
    assert "api_token" in dashboard
    assert "context_api_enabled" in dashboard
    assert "X-Codex-Usage-Token" in dashboard_surface
    assert "contextApiEnabled" in dashboard_js
    assert "recommended_action" in dashboard
    assert "flag_explanations" in dashboard
    assert "action_recommendations" in dashboard
    assert "action_thresholds" in dashboard
    assert "detail.why_flagged" in dashboard_details_js
    assert "detail.thread_lifecycle" in dashboard_details_js
    assert "detail.largest_cumulative_jump" in dashboard_details_js
    assert "project_name" in dashboard
    assert "detail.project_tags" in dashboard_details_js
    assert "detail.git_branch" in dashboard_details_js
    assert "usage_credit_confidence" in dashboard
    assert "allowance.credit_rates" in dashboard_status_js
    assert "getAllowanceConfigured() ? t('state.allowance_configured')" not in dashboard_status_js
    assert "insight.codex_allowance_usage" in dashboard_insights_js
    assert "Highest Codex credits" in dashboard
    assert "Estimated Tokens" not in dashboard
    assert "Unpriced Tokens" not in dashboard
    assert "insightsView" in dashboard
    assert "callsView" in dashboard
    assert "threadsView" in dashboard
    assert "diagnosticsView" in dashboard
    assert "diagnosticsPanel" in dashboard
    assert "/api/diagnostics/facts" in dashboard_diagnostics_js
    assert "/api/diagnostics/tools" in dashboard_diagnostics_js
    assert "/api/diagnostics/compactions" in dashboard_diagnostics_js
    assert "/api/diagnostics/fact-calls" in dashboard_diagnostics_js
    assert "/api/diagnostics/refresh" in dashboard_diagnostics_js
    assert "dashboard_diagnostics_snapshots.js" in dashboard
    assert "dashboard_diagnostics_facts.js" in dashboard
    assert "/api/diagnostics/overview" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/tool-output/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/commands/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/git-interactions/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/file-reads/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/file-modifications/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/read-productivity/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/concentration/refresh" in dashboard_diagnostics_snapshots_js
    assert "/api/diagnostics/usage-drain/refresh" in dashboard_diagnostics_snapshots_js
    assert "Refresh diagnostics" in dashboard_diagnostics_snapshots_js
    assert "data-diagnostics-refresh" in dashboard_diagnostics_js
    assert "data-diagnostics-section-refresh" in dashboard_diagnostics_js
    assert "data-diagnostics-section-refresh" in dashboard_diagnostics_snapshots_js
    assert "refreshDiagnosticSnapshot" in dashboard_diagnostics_js
    assert "Live API required for diagnostics refresh" in dashboard_diagnostics_js
    assert "Overview" in dashboard_diagnostics_snapshots_js
    assert "Tool Output" in dashboard_diagnostics_snapshots_js
    assert "Git Interactions" in dashboard_diagnostics_snapshots_js
    assert "File Reads" in dashboard_diagnostics_snapshots_js
    assert "File Modifications" in dashboard_diagnostics_snapshots_js
    assert "Read Productivity" in dashboard_diagnostics_snapshots_js
    assert "Concentration" in dashboard_diagnostics_snapshots_js
    assert "Usage Drain" in dashboard_diagnostics_snapshots_js
    assert "Cumulative estimated cost by thread" in dashboard_diagnostics_snapshots_js
    assert "Weekly usage over time" in dashboard_diagnostics_snapshots_js
    assert "Projected weekly credits over time" in dashboard_diagnostics_snapshots_js
    assert "Credit-to-visible-delta R2" in dashboard_diagnostics_snapshots_js
    assert "Associated token totals" in dashboard_diagnostics_js
    assert "Raw context remains on-demand" in dashboard_diagnostics_js
    assert "rowInvestigatorLink" in dashboard_diagnostics_js
    assert "diagnostics-drilldown-row" in dashboard_diagnostics_facts_js
    assert 'td colspan="11"' in dashboard_diagnostics_facts_js
    assert "associated_cached_input_tokens" in dashboard_diagnostics_facts_js
    assert "row.cached_input_tokens" in dashboard_diagnostics_facts_js
    assert "Occurrences: count of matching diagnostic fact events" in dashboard_diagnostics_facts_js
    assert "Associated total tokens for those calls" in dashboard_diagnostics_facts_js
    assert "Average cache ratio across associated calls" in dashboard_diagnostics_facts_js
    assert "data-diagnostics-fact-sort-key" in dashboard_diagnostics_facts_js
    assert "data-diagnostics-fact-sort-active" in dashboard_diagnostics_facts_js
    assert "sortFactRows" in dashboard_diagnostics_js
    assert "diagnosticFactHeader" in dashboard_diagnostics_facts_js
    assert "diagnostics-facts-table" in dashboard_surface
    assert "diagnostics-fact-cell" in dashboard_surface
    assert "diagnostics-snapshot-grid" in dashboard_css
    assert "diagnostics-toolbar" in dashboard_css
    assert "diagnostics-mini-table" in dashboard_css
    assert "diagnostics-line-chart" in dashboard_css
    assert "diagnostics-facts-table th:first-child" in dashboard_css
    assert "td.diagnostics-fact-cell" in dashboard_css
    assert "captureScrollAnchor" in dashboard_diagnostics_js
    assert "restoreScrollAnchor" in dashboard_diagnostics_js
    assert "data-diagnostics-call-load-more" in dashboard_diagnostics_js
    assert "offset: String(offset)" in dashboard_diagnostics_js
    assert "mergeFactCallPayload" in dashboard_diagnostics_js
    assert "data-diagnostics-call-sort-key" in dashboard_diagnostics_js
    assert "data-diagnostics-call-sort-active" in dashboard_diagnostics_facts_js
    assert "sortFactCalls" in dashboard_diagnostics_js
    assert "defaultFactCallSortDirection" in dashboard_diagnostics_js
    assert "sort: sortState.sort" in dashboard_diagnostics_js
    assert "direction: sortState.direction" in dashboard_diagnostics_js
    assert "diagnostics-expand-button" in dashboard_surface
    assert "selectedFactKey === key" in dashboard_diagnostics_js
    assert "if (rowsNeedHydration())" in dashboard_js
    assert "hydrateDashboardRows();" in dashboard_js
    assert "refreshDashboardIfStale();" in dashboard_js
    assert "Needs Attention" in dashboard
    assert "Investigation Presets" in dashboard
    assert "presetDefinitions" in dashboard_insights_js
    assert "renderInsightPanel" in dashboard_insights_js
    assert "attentionScore" in dashboard_analysis_js
    assert "thread-row" in dashboard_surface
    assert "thread-call-table" in dashboard_surface
    assert "--calls-table-min-width" in dashboard_css
    assert "min-width: var(--calls-table-min-width)" in dashboard_css
    assert "tr:hover { background" not in dashboard_css
    assert "cachedTokenCell" in dashboard_cells_js
    assert "uncachedTokenCell" in dashboard_cells_js
    assert "outputTokenCell" in dashboard_cells_js
    assert "reasoningTokenCell" in dashboard_cells_js
    assert "signalPuckAbbreviation" in dashboard_cells_js
    assert "signal-puck" in dashboard_css
    assert "data-thread-call-sort-key" in dashboard_tables_js
    assert "threadCallSortKey = 'time'" in dashboard_js
    assert "threadCallSortDirection = 'desc'" in dashboard_js
    assert "state.view !== 'calls'" in dashboard_state_js
    assert "state.sort !== 'time'" in dashboard_state_js
    assert "detail.thread_attachment" in dashboard_details_js
    assert "detail.subagent_type" in dashboard_details_js
    assert "source.auto_review" in dashboard_cells_js
    assert "button.load_context" in dashboard_surface
    assert "button.open_investigator" in dashboard_details_js
    assert "Click a call row for deep diagnostics." in dashboard_surface
    assert "data-open-investigator-record" not in render_calls_js
    assert "rowInvestigatorLink(row" in render_calls_js
    assert "target=\"_blank\"" in dashboard_actions_js
    assert "rel=\"noopener\"" in dashboard_actions_js
    assert "a.row-investigator-link" in dashboard_events_js
    assert "/api/open-investigator" in dashboard_actions_js
    assert "openInvestigatorUrl(rowLink.href)" in dashboard_events_js
    assert "window.location.href = url" not in dashboard_surface
    assert "window.open(url, '_blank')" in dashboard_actions_js
    assert dashboard_actions_js.index("/api/open-investigator") < dashboard_actions_js.index(
        "window.open(url, '_blank')"
    )
    assert "opened.opener = null" in dashboard_actions_js
    assert "selectRow(row);" not in render_calls_js
    assert "dashboard.view.call" in dashboard_js
    assert "renderCallInvestigator" in dashboard_js
    assert "fetchCallRecord" in dashboard_js
    assert "fetchCallRecord" in dashboard_call_js
    assert "/api/call?" in dashboard_js
    assert "supplementalRowsByRecordId" in dashboard_js
    assert 'body[data-active-view="call"] .detail-section' in dashboard_css
    assert 'body[data-active-view="call"] .table-tools' in dashboard_css
    assert ".call-diagnostic-section.exact" in dashboard_css
    assert "creditsText(usageCreditValue(row))" in dashboard_call_js
    assert "const contextPayloadState = new Map()" in dashboard_call_js
    assert "renderInvestigationReadout" in dashboard_call_diagnostics_js
    assert "contextStateRecord(row)" in dashboard_call_js
    assert "defaultContextRequest" in dashboard_call_js
    assert "mode: 'quick'" in dashboard_call_js
    assert "mode: 'full'" in dashboard_call_js
    assert "includeToolOutput: true" in dashboard_call_js
    assert "maxChars: 0" in dashboard_call_js
    assert "maxEntries: defaultContextEntries" in dashboard_call_js
    assert "data-context-toggle-tool-output" in dashboard_call_js
    assert "data-context-full-analysis" in dashboard_call_js
    assert "button.hide_tool_output" in dashboard_call_js
    assert "data-context-autoload-toggle" not in dashboard_call_js
    assert "renderCacheVerdict" in dashboard_call_diagnostics_js
    assert "data-context-scroll" not in dashboard_call_js
    assert ".readout-grid" in dashboard_css
    assert ".cache-verdict" in dashboard_css
    assert ".context-inline-action" in dashboard_css
    assert ".initiator-puck" in dashboard_css
    assert ".initiator-unknown" in dashboard_css
    assert ".initiator-cell" in dashboard_css
    assert "table.initiated" in dashboard_tables_js
    assert "callInitiatorCell" in dashboard_cells_js
    assert "sortLabelText(sortKey)" in dashboard_js
    assert "callInitiatorPuck" in dashboard_cells_js
    assert "row.call_initiator" in dashboard_js
    assert "data-open-investigator-record" in dashboard_details_js
    assert "data-call-nav-record" in dashboard_events_js
    assert "call.cache_accounting_delta" in dashboard_call_js
    assert "call.hidden_estimate" in dashboard_call_js
    assert "call.serialized_upper_bound" in dashboard_call_js
    assert "call.remaining_after_serialized" in dashboard_call_js
    assert "renderSerializedEvidenceBreakdown" in dashboard_call_js
    assert "serialized_evidence" in dashboard_call_js
    assert ".serialized-breakdown" in dashboard_css
    assert "captureContextUiState" in dashboard_call_js
    assert "restoreContextUiState" in dashboard_call_js
    assert "bindContextUiState" in dashboard_call_js
    assert "data-context-entry-key" in dashboard_call_js
    assert "button.show_tool_output" in dashboard_call_js
    assert "data-context-entry-load-output" in dashboard_call_js
    assert "button.full_serialized_analysis" in dashboard_call_js
    assert ".grid > section:not(.detail-section)" in dashboard_css
    assert "overflow: visible" in dashboard_css
    assert "table-layout: fixed" in dashboard_css
    assert "position: sticky" in dashboard_css
    assert ".grid > section:first-child > table > thead" in dashboard_css
    assert "${callInitiatorPuck(row)}" in dashboard_details_js
    assert "<span>${escapeHtml(initiator.source)}</span>" not in dashboard_details_js
    assert "tooltipAttributes(label)" in dashboard_call_diagnostics_js
    assert "tooltipAttributes(badge)" in dashboard_call_diagnostics_js
    assert "data-context-load-older" in dashboard_call_js
    assert "data-context-no-budget" not in dashboard_call_js
    assert "renderContextTokenUsage" in dashboard_call_js
    assert "renderContextCompaction" in dashboard_call_js
    assert "renderThreadAnchors" not in dashboard_call_js
    assert "payload.call_anchors" not in dashboard_call_js
    assert "payload.thread_anchors" not in dashboard_call_js
    assert "context-entry-collapsed" in dashboard_call_js
    assert "call.readout.evidence_analyzed" in dashboard_call_diagnostics_js
    assert "call.delta.cache_drop" in dashboard_call_diagnostics_js
    assert "call.next_step.warm" in dashboard_call_diagnostics_js
    assert "total_entries" in dashboard_call_js
    assert ".context-anchor-panel" not in dashboard_css
    assert ".context-entry-summary" in dashboard_css
    assert "data-context-compaction-history" in dashboard_call_js
    assert "context-token-breakdown" in dashboard_css
    assert "context-compaction" in dashboard_css
    assert "tool_output_omitted" in dashboard_call_js
    assert "parent_thread_name" in dashboard
    assert "thread_attachment_label" in dashboard
    assert "thread_attachment_relation" in dashboard
    assert "explicit parent thread" in dashboard_surface
    assert "thread.spawned_from" in dashboard_tables_js
    assert "thread.spawned_threads" in dashboard_tables_js

    from codex_usage_tracker.i18n import translations_for
    en_trans = translations_for("en")
    assert en_trans["detail.why_flagged"] == "Why flagged"
    assert en_trans["detail.thread_lifecycle"] == "Thread lifecycle"
    assert en_trans["detail.largest_cumulative_jump"] == "Largest cumulative jump"
    assert en_trans["detail.project_tags"] == "Project tags"
    assert en_trans["detail.git_branch"] == "Git branch"
    assert "Credit rates:" in en_trans["allowance.credit_rates"]
    assert en_trans["insight.codex_allowance_usage"] == "Codex allowance usage"
    assert en_trans["detail.thread_attachment"] == "Thread attachment"
    assert en_trans["detail.subagent_type"] == "Subagent type"
    assert en_trans["source.auto_review"] == "Auto-review"
    assert en_trans["button.show_turn_evidence"] == "Show turn log evidence"
    assert en_trans["button.open_investigator"] == "Open investigator"
    assert en_trans["call.open_hint"] == "Click a call row for deep diagnostics."
    assert en_trans["call.serialized_upper_bound"] == "Serialized local upper bound"
    assert en_trans["call.serialized_bucket_detail"] == "{count} fields · {chars} chars"
    assert en_trans["dashboard.view.call"] == "Call Investigator"
    assert en_trans["button.show_tool_output"] == "Show tool output"
    assert en_trans["button.hide_tool_output"] == "Hide tool output"
    assert en_trans["button.full_serialized_analysis"] == "Run full serialized analysis"
    assert en_trans["button.hide_details"] == "Hide details"
    assert en_trans["table.initiated"] == "Initiated"
    assert en_trans["source.user_initiated"] == "User initiated"
    assert en_trans["source.codex_initiated"] == "Codex initiated"
    assert "spawned from" in en_trans["thread.spawned_from"]
    assert "spawned threads" in en_trans["thread.spawned_threads"]
    assert en_trans["detail.thread_timeline"] == "Thread timeline"
    assert en_trans["detail.raw_identifiers"] == "Raw aggregate identifiers"
    assert en_trans["metric.codex_credits"] == "Codex credits"
    assert en_trans["metric.usage_observed"] == "Usage observed"
    assert "local Codex token-count log" in en_trans["allowance.observed_source_hint"]
    assert "not a live account query" in en_trans["allowance.observed_source_hint"]
    assert en_trans["detail.allowance_impact"] == "Allowance impact"
    assert en_trans["detail.credit_model"] == "Credit model"
    assert "Live refresh every" in en_trans["live.every"]
    assert "Refreshing local usage index" in en_trans["live.refreshing_index"]
    assert "Aggregate only" not in dashboard
    assert "Call Details" in dashboard
    assert "Dashboard guide" in dashboard
    assert "github.com/douglasmonsky/codex-usage-tracker/blob/main/docs/dashboard-guide.md" not in dashboard
    assert "codex-usage-tracker-guide/dashboard-guide.html" in dashboard
    assert (tmp_path / "codex-usage-tracker-guide" / "dashboard-guide.html").exists()
    dashboard_guide = (tmp_path / "codex-usage-tracker-guide" / "dashboard-guide.html").read_text(
        encoding="utf-8"
    )
    assert "call anchors" not in dashboard_guide.lower()
    assert "nearest visible message" not in dashboard_guide
    assert (tmp_path / "codex-usage-tracker-guide" / "assets" / "dashboard-calls.png").exists()
    assert (asset_dir / "dashboard.js").exists()
    assert (asset_dir / "dashboard_call_investigator.js").exists()
    assert (asset_dir / "dashboard_format.js").exists()
    assert (asset_dir / "dashboard_data.js").exists()
    assert (asset_dir / "dashboard_analysis.js").exists()
    assert (asset_dir / "dashboard_cells.js").exists()
    assert (asset_dir / "dashboard_details.js").exists()
    assert (asset_dir / "dashboard_insights.js").exists()
    assert (asset_dir / "dashboard_tables.js").exists()
    assert (asset_dir / "dashboard_diagnostics_snapshots.js").exists()
    assert (asset_dir / "dashboard_filters.js").exists()
    assert (asset_dir / "dashboard_state.js").exists()
    assert (asset_dir / "dashboard_payload_cache.js").exists()
    assert (asset_dir / "dashboard_i18n.js").exists()
    assert (asset_dir / "dashboard_tooltips.js").exists()
    assert (asset_dir / "dashboard_status.js").exists()
    assert (asset_dir / "dashboard_actions.js").exists()
    assert (asset_dir / "dashboard_live.js").exists()
    assert (asset_dir / "dashboard_events.js").exists()
    assert (asset_dir / "dashboard_diagnostics.js").exists()
    assert (asset_dir / "dashboard_call_diagnostics.js").exists()
    for stylesheet in dashboard_stylesheets:
        assert (asset_dir / stylesheet).exists()
    assert "detail-section" in dashboard
    assert "detailToggle" in dashboard
    assert "body[data-detail-panel=\"expanded\"] .grid" in dashboard_css
    assert "applyDetailPanelState()" in dashboard_js
    assert "time-cell" in dashboard_surface
    assert "formatTimestamp" in dashboard_js
    assert "formatDuration" in dashboard_js
    assert 'data-sort-key="duration"' in dashboard
    assert 'data-sort-key="gap"' in dashboard
    assert '<option value="duration" data-i18n="option.longest_duration">Longest duration</option>' in dashboard
    assert '<option value="gap" data-i18n="option.longest_gap">Longest gap</option>' in dashboard
    assert "scrollbar-gutter: stable" in dashboard_css
    assert "overflow-y: scroll" in dashboard_css
    assert "pricingSource.fetched_at" in dashboard_status_js
    assert "pricingSnapshotWarning" in dashboard_status_js
    assert "formatTimestamp(nextPayload.refreshed_at)" in dashboard_live_js
    assert "threadModelSummary" in dashboard_analysis_js
    assert "model-pill" in dashboard_surface
    assert "Back to top" in dashboard
    assert "updateToTopVisibility" in dashboard_js
    assert "live.every" in dashboard_surface
    assert "live.refreshing_index" in dashboard_live_js
    assert "loadLimit" in dashboard
    assert "pager" in dashboard
    assert "loadMoreRows" in dashboard
    assert "visibleSlice(rows)" in dashboard_tables_js
    assert "updateLoadMoreControl(page, 'table.threads')" in dashboard_tables_js
    assert "data-thread-load-more" in dashboard_tables_js
    assert "data-fast-tooltip" in dashboard_surface
    assert "scheduleFastTooltip(target)" in dashboard_js
    assert "focusPendingTarget" in dashboard_js
    assert "queueFocusTarget(insight.target)" in dashboard_js
    assert "selected-row" in dashboard_tables_js
    assert "selected-row" in dashboard_css
    assert "costUsageCell" in dashboard_cells_js
    assert "Codex credits" in dashboard
    assert "All calls" in dashboard
    assert "/api/usage" in dashboard_live_js
    assert "detail-card primary" in dashboard_details_js
    assert "detail.thread_timeline" in dashboard_details_js
    assert "detail.raw_identifiers" in dashboard_details_js
    assert "metric.codex_credits" in dashboard_details_js
    assert "detail.allowance_impact" in dashboard_details_js
    assert "detail.credit_model" in dashboard_details_js
    assert 'data-sort-key="time"' in dashboard
    assert 'data-sort-key="thread"' in dashboard
    assert 'data-sort-key="reasoning"' in dashboard
    assert 'data-sort-header="signals"' not in dashboard
    assert '<option value="signals"' not in dashboard
    assert '<option value="time" selected data-i18n="option.newest_calls">Newest calls</option>' in dashboard
    assert '<option value="initiator" data-i18n="table.initiated">Initiated</option>' in dashboard
    assert '<option value="usage" data-i18n="option.highest_codex_credits">Highest Codex credits</option>' in dashboard
    assert 'id="insightsView" type="button" aria-pressed="false"' in dashboard
    assert 'id="callsView" type="button" aria-pressed="true"' in dashboard
    assert 'id="diagnosticsView" type="button" aria-pressed="false"' in dashboard

    pricing_path.write_text(
        json.dumps(
            {
                "_source": {
                    "name": "Synthetic pricing",
                    "fetched_at": "2026-06-05T12:00:00Z",
                },
                "models": {
                    "gpt-5.5": {
                        "input_per_million": 3.0,
                        "cached_input_per_million": 0.75,
                        "output_per_million": 12.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    generate_dashboard(db_path=db_path, output_path=dashboard_path, pricing_path=pricing_path)
    updated_dashboard = dashboard_path.read_text(encoding="utf-8")
    assert "Pricing snapshot changed since the previous dashboard render" in updated_dashboard


def test_dashboard_payload_contract_includes_analysis_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, pricing_path=pricing_path)
    row = payload["rows"][0]

    assert {
        "rows",
        "pricing_configured",
        "allowance_configured",
        "loaded_row_count",
        "total_available_rows",
        "parser_diagnostics",
        "parser_adapter",
        "action_thresholds",
        "project_metadata_privacy",
    } <= set(payload)
    assert {
        "record_id",
        "session_id",
        "event_timestamp",
        "cwd",
        "total_tokens",
        "cache_ratio",
        "pricing_model",
        "usage_credits",
        "call_started_at",
        "call_duration_seconds",
        "previous_call_event_timestamp",
        "previous_call_delta_seconds",
        "recommended_action",
        "call_initiator",
        "call_initiator_reason",
        "call_initiator_confidence",
        "project_name",
        "project_key",
        "thread_attachment_label",
    } <= set(row)


def test_dashboard_payload_includes_latest_observed_usage_snapshot(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, include_rows=False)

    observed = payload["observed_usage"]
    assert isinstance(observed, dict)
    assert observed["available"] is True
    assert observed["source"] == "token_count.rate_limits"
    assert observed["limit_id"] == "codex"
    assert observed["windows"] == [
        {
            "key": "primary",
            "label": "5h",
            "used_percent": 3.0,
            "window_minutes": 300,
            "resets_at": 1781562696,
        },
        {
            "key": "secondary",
            "label": "Weekly",
            "used_percent": 29.0,
            "window_minutes": 10080,
            "resets_at": 1781887793,
        },
    ]


def test_dashboard_payload_uses_persisted_call_origin_without_source_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    poison_source = tmp_path / "poison-source.jsonl"
    poison_source.write_text("{this is not valid json}\n" * 1000, encoding="utf-8")
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_events
            SET source_file = ?
            WHERE call_initiator = 'user'
            """,
            (str(poison_source),),
        )

    original_open = Path.open

    def fail_source_open(self: Path, *args: object, **kwargs: object) -> object:
        if self == poison_source:
            raise AssertionError("dashboard_payload must not read source JSONL")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_source_open)

    payload = dashboard_payload(db_path=db_path)
    rows = payload["rows"]
    by_initiator = {row["call_initiator"]: row for row in rows}

    assert by_initiator["user"]["call_initiator_reason"] == "user_message"
    assert by_initiator["user"]["call_initiator_confidence"] == "high"


def test_dashboard_payload_and_csv_privacy_mode_redact_project_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage-redacted.csv"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, privacy_mode="strict")
    exported = export_usage_csv(
        output_path=csv_path,
        db_path=db_path,
        privacy_mode="redacted",
    )
    csv_text = csv_path.read_text(encoding="utf-8")
    csv_header = csv_text.splitlines()[0].split(",")
    first_row = payload["rows"][0]

    assert exported == 4
    assert payload["privacy_mode"] == "strict"
    assert payload["project_metadata_privacy"]["cwd_redacted"] is True
    assert first_row["cwd"].startswith("[redacted cwd:")
    assert first_row["project_name"].startswith("Project ")
    assert first_row["project_relative_cwd"] is None
    assert first_row["git_branch"] is None
    assert first_row["git_remote_label"] is None
    assert "/tmp/codex-usage-tracker" not in json.dumps(payload)
    assert "/tmp/codex-usage-tracker" not in csv_text
    assert "[redacted cwd:" in csv_text
    assert csv_header == EVENT_COLUMNS


def test_dashboard_guide_link_can_use_docs_url_override(tmp_path: Path, monkeypatch) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    monkeypatch.setenv("CODEX_USAGE_TRACKER_DOCS_URL", "https://example.test/guide")

    dashboard_path = tmp_path / "dashboard.html"
    generate_dashboard(db_path=db_path, output_path=dashboard_path)

    dashboard = dashboard_path.read_text(encoding="utf-8")
    assert 'href="https://example.test/guide"' in dashboard
    assert not (tmp_path / "codex-usage-tracker-guide").exists()
    assert (tmp_path / "codex-usage-tracker-assets" / "dashboard.js").exists()
