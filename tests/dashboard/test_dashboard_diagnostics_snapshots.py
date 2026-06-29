from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_snapshot_renderer_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard diagnostic snapshot renderer tests")
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_diagnostics_snapshots.js"
    )
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{
  window: {{}},
  console,
}};
vm.createContext(context);
vm.runInContext(code, context);
const factory = context.window.CodexUsageDashboardDiagnosticSnapshots;
function escapeHtml(value) {{
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}}
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_dashboard_commands_snapshot_renders_collapsible_children() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${value}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>call</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    commands: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      commands: [
        {
          root: 'git',
          total: 3,
          children: [
            { child: 'status', count: 2 },
            { child: 'diff', count: 1 },
          ],
        },
      ],
    },
  },
});
console.log(JSON.stringify({
  hasDetails: html.includes('<details class="diagnostics-command-children">'),
  hasShowSummary: html.includes('Show all 2 children'),
  hasHideSummary: html.includes('Hide 2 children'),
  hasToggleIcon: html.includes('diagnostics-command-toggle-icon'),
  hasFirstChild: html.includes('status') && html.includes('<b>2</b>'),
  hasSecondChild: html.includes('diff') && html.includes('<b>1</b>'),
  hasTopChildColumn: html.includes('Top child'),
}));
"""
    )

    assert payload["hasDetails"] is True
    assert payload["hasShowSummary"] is True
    assert payload["hasHideSummary"] is True
    assert payload["hasToggleIcon"] is True
    assert payload["hasFirstChild"] is True
    assert payload["hasSecondChild"] is True
    assert payload["hasTopChildColumn"] is False


def test_dashboard_concentration_snapshot_renders_reader_facing_labels() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    concentration: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      metrics: [
        { metric: 'top_1_source_log_share', dimension: 'source_log', top_n: 1, share: 0.5 },
        { metric: 'top_3_cwd_share', dimension: 'cwd', top_n: 3, share: 0.9 },
      ],
      largest_impact_rows: [
        {
          dimension: 'source_log',
          label: 'session:019e37d3',
          share: 0.5,
          largest_record_id: 'r1',
          largest_call_tokens: 1000,
        },
      ],
    },
  },
});
console.log(JSON.stringify({
  hasSourceMetricLabel: html.includes('Top 1 source/session share'),
  hasProjectMetricLabel: html.includes('Top 3 project/cwd share'),
  hasDimensionLabel: html.includes('Source/session'),
  hasSafeSourceLabel: html.includes('session:019e37d3'),
  leaksMetricId: html.includes('top_1_source_log_share'),
}));
"""
    )

    assert payload["hasSourceMetricLabel"] is True
    assert payload["hasProjectMetricLabel"] is True
    assert payload["hasDimensionLabel"] is True
    assert payload["hasSafeSourceLabel"] is True
    assert payload["leaksMetricId"] is False


def test_dashboard_git_interactions_snapshot_renders_safe_labels() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    gitInteractions: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: {
        git_shell_calls: 2,
        git_command_calls: 1,
        github_cli_calls: 1,
        interactions_with_original_token_count: 2,
        interactions_missing_original_token_count: 0,
        original_token_sum: 55,
      },
      interactions: [
        {
          root: 'git',
          operation: 'status',
          category: 'read_only',
          mutability: 'read_only',
          calls: 1,
          original_token_sum: 42,
        },
        {
          root: 'gh',
          operation: 'pr',
          category: 'pull_request',
          mutability: 'github_remote',
          calls: 1,
          original_token_sum: 13,
        },
      ],
      categories: [
        { category: 'read_only', count: 1 },
        { category: 'pull_request', count: 1 },
      ],
    },
  },
});
console.log(JSON.stringify({
  hasHeading: html.includes('Git Interactions'),
  hasStatus: html.includes('status'),
  hasPr: html.includes('Pull Request'),
  hasOriginalTokens: html.includes('55'),
  leaksRawCommand: html.includes('git status --short') || html.includes('SECRET'),
}));
"""
    )

    assert payload["hasHeading"] is True
    assert payload["hasStatus"] is True
    assert payload["hasPr"] is True
    assert payload["hasOriginalTokens"] is True
    assert payload["leaksRawCommand"] is False


def test_dashboard_file_modifications_snapshot_renders_safe_labels() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    fileModifications: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: {
        modification_events: 2,
        modified_path_events: 3,
        unique_paths_modified: 2,
        largest_event_path_count: 2,
      },
      top_paths: [
        { path_label: 'app.py', path_hash: 'abcdef123456', modification_events: 2 },
        { path_label: 'notes.md', path_hash: '123456abcdef', modification_events: 1 },
      ],
      by_extension: [
        { extension: '.py', count: 2 },
        { extension: '.md', count: 1 },
      ],
    },
  },
});
console.log(JSON.stringify({
  hasHeading: html.includes('File Modifications'),
  hasSummary: html.includes('Modified path events') && html.includes('3'),
  hasPathLabel: html.includes('app.py'),
  hasExtension: html.includes('.md'),
  leaksRawPath: html.includes('/tmp/private') || html.includes('src/app.py') || html.includes('SECRET'),
}));
"""
    )

    assert payload["hasHeading"] is True
    assert payload["hasSummary"] is True
    assert payload["hasPathLabel"] is True
    assert payload["hasExtension"] is True
    assert payload["leaksRawPath"] is False


def test_dashboard_stale_snapshot_panels_render_reload_buttons() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    overview: {
      status: 'missing',
      snapshot: {
        history_scope: 'active',
      },
    },
    toolOutput: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: { function_calls: 1 },
      functions: [],
    },
  },
  sectionRefreshStatuses: {
    overview: 'refreshing',
  },
});
console.log(JSON.stringify({
  hasOverviewReload: html.includes('data-diagnostics-section-refresh="overview"'),
  overviewReloads: html.includes('Reloading...'),
  hasCommandsReload: html.includes('data-diagnostics-section-refresh="commands"'),
  hasToolOutputReload: html.includes('data-diagnostics-section-refresh="toolOutput"'),
  readyBadgeStillVisible: html.includes('<span>stored</span>'),
}));
"""
    )

    assert payload["hasOverviewReload"] is True
    assert payload["overviewReloads"] is True
    assert payload["hasCommandsReload"] is True
    assert payload["hasToolOutputReload"] is False
    assert payload["readyBadgeStillVisible"] is True


def test_dashboard_usage_drain_charts_render_as_featured_first() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    overview: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      overview: { usage_rows: 2 },
    },
    usageDrain: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: { usage_rows: 2, estimated_cost_usd: 0.1 },
      time_series: {
        visible_usage: {
          points: [
            { timestamp: '2026-06-12T00:00:00Z', weekly_used_percent: 25 },
            { timestamp: '2026-06-13T00:00:00Z', weekly_used_percent: 40 },
            { timestamp: '2026-06-19T00:00:00Z', weekly_used_percent: 10 },
            { timestamp: '2026-06-20T00:00:00Z', weekly_used_percent: 30 },
          ],
        },
        weekly_credit_projection: {
          points: [
            {
              label: 'Reset Jun 12',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 40,
              observed_standard_usage_credits: 12000,
              projected_weekly_credits: 30000,
              ci_low: 25000,
              ci_high: 35000,
            },
            {
              label: 'Reset Jun 19',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 50,
              observed_standard_usage_credits: 20000,
              projected_weekly_credits: 40000,
              ci_low: 36000,
              ci_high: 44000,
            },
          ],
        },
      },
      thread_cost_curves: { threads: [] },
      model_highlights: {},
    },
  },
});
console.log(JSON.stringify({
  hasFeaturedBlock: html.includes('data-diagnostics-featured="usage-drain"'),
  featuredBeforeGrid: html.indexOf('data-diagnostics-featured="usage-drain"') < html.indexOf('diagnostics-snapshot-grid'),
  projectionBeforeWeekly: html.indexOf('Projected weekly credits over time') < html.indexOf('Weekly usage over time'),
  projectionBeforeOverview: html.indexOf('Projected weekly credits over time') < html.indexOf('Overview'),
  weeklyChartTitleCount: (html.match(/<strong>Weekly usage over time<\\/strong>/g) || []).length,
  weeklyRemainingPolylineCount: (html.match(/stroke="#059669"/g) || []).length,
  projectedChartTitleCount: (html.match(/<strong>Projected weekly credits over time<\\/strong>/g) || []).length,
  hasCiColumn: html.includes('95% CI'),
  hasFormattedCiRange: html.includes('25,000 - 35,000') && html.includes('36,000 - 44,000'),
  labelsRemainingAllowance: html.includes('Usage remaining') && html.includes('Weekly remaining'),
  labelsVisibleUsage: html.includes('Visible usage'),
  preservesMoneyCents: html.includes('$0.10'),
}));
"""
    )

    assert payload["hasFeaturedBlock"] is True
    assert payload["featuredBeforeGrid"] is True
    assert payload["projectionBeforeWeekly"] is True
    assert payload["projectionBeforeOverview"] is True
    assert payload["weeklyChartTitleCount"] == 1
    assert payload["weeklyRemainingPolylineCount"] == 2
    assert payload["projectedChartTitleCount"] == 1
    assert payload["hasCiColumn"] is True
    assert payload["hasFormattedCiRange"] is True
    assert payload["labelsRemainingAllowance"] is True
    assert payload["labelsVisibleUsage"] is False
    assert payload["preservesMoneyCents"] is True


def test_dashboard_weekly_projection_keeps_non_latest_plan_points() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    usageDrain: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: { usage_rows: 4 },
      time_series: {
        weekly_credit_projection: {
          points: [
            {
              label: 'Reset Jun 07',
              start_event_timestamp: '2026-06-01T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'plus',
              observed_usage_delta_percent: 40,
              observed_standard_usage_credits: 4000,
              projected_weekly_credits: 10000,
              ci_low: 9000,
              ci_high: 11000,
            },
            {
              label: 'Reset Jun 10',
              start_event_timestamp: '2026-06-03T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'plus',
              observed_usage_delta_percent: 50,
              observed_standard_usage_credits: 6000,
              projected_weekly_credits: 12000,
              ci_low: 10000,
              ci_high: 14000,
            },
            {
              label: 'Reset Jun 12',
              start_event_timestamp: '2026-06-05T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 60,
              observed_standard_usage_credits: 24000,
              projected_weekly_credits: 40000,
              ci_low: 36000,
              ci_high: 44000,
            },
            {
              label: 'Reset Jun 19',
              start_event_timestamp: '2026-06-12T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 70,
              observed_standard_usage_credits: 35000,
              projected_weekly_credits: 50000,
              ci_low: 45000,
              ci_high: 55000,
            },
            {
              label: 'Reset Jun 24',
              start_event_timestamp: '2026-06-18T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 45,
              observed_standard_usage_credits: 21000,
              projected_weekly_credits: 46667,
              ci_low: 42000,
              ci_high: 50000,
            },
            {
              label: 'Reset Jun 28',
              start_event_timestamp: '2026-06-22T00:00:00Z',
              confidence: 'medium',
              rate_limit_plan_type: 'plus',
              observed_usage_delta_percent: 30,
              observed_standard_usage_credits: 3300,
              projected_weekly_credits: 11000,
              ci_low: 9500,
              ci_high: 12500,
            },
            {
              label: 'Reset Unknown',
              start_event_timestamp: '2026-06-25T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: null,
              observed_usage_delta_percent: 20,
              observed_standard_usage_credits: 8000,
              projected_weekly_credits: 40000,
              ci_low: 35000,
              ci_high: 45000,
            },
          ],
        },
      },
      thread_cost_curves: { threads: [] },
      model_highlights: {},
    },
  },
});
console.log(JSON.stringify({
  hasMixedPlanSubtitle: html.includes('2 plan types shown; trend requires 3+ medium/high windows per plan'),
  hasPlusLegend: html.includes('>Plus</span>'),
  hasProLegend: html.includes('>Pro</span>'),
  hasPlusTableRows: html.includes('<td>Plus</td>'),
  hasProTableRows: html.includes('<td>Pro</td>'),
  hasUnknownLegend: html.includes('>Unknown</span>'),
  hasUnknownTableRows: html.includes('<td>Unknown</td>') || html.includes('Reset Unknown'),
  markerCount: (html.match(/<circle /g) || []).length,
  resetLabelCount: (html.match(/Reset Jun/g) || []).length,
  hasCompactAxisLabel: html.includes('>Jun 07</text>'),
  hasResetAxisLabel: html.includes('>Reset Jun 07</text>'),
  trendLabel: html.includes('Trend per plan'),
  hasInlineTrendStyle: html.includes('style="stroke:'),
  hidesOlderPlan: !html.includes('Reset Jun 07') || !html.includes('Reset Jun 10'),
}));
"""
    )

    assert payload["hasMixedPlanSubtitle"] is True
    assert payload["hasPlusLegend"] is True
    assert payload["hasProLegend"] is True
    assert payload["hasPlusTableRows"] is True
    assert payload["hasProTableRows"] is True
    assert payload["hasUnknownLegend"] is False
    assert payload["hasUnknownTableRows"] is False
    assert payload["markerCount"] == 6
    assert payload["resetLabelCount"] >= 6
    assert payload["hasCompactAxisLabel"] is True
    assert payload["hasResetAxisLabel"] is False
    assert payload["trendLabel"] is True
    assert payload["hasInlineTrendStyle"] is False
    assert payload["hidesOlderPlan"] is False


def test_dashboard_weekly_projection_omits_sparse_plan_trend() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    usageDrain: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: { usage_rows: 3 },
      time_series: {
        weekly_credit_projection: {
          points: [
            {
              label: 'Reset Jun 07',
              start_event_timestamp: '2026-06-01T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'plus',
              observed_usage_delta_percent: 40,
              observed_standard_usage_credits: 4000,
              projected_weekly_credits: 10000,
              ci_low: 9000,
              ci_high: 11000,
            },
            {
              label: 'Reset Jun 14',
              start_event_timestamp: '2026-06-08T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'plus',
              observed_usage_delta_percent: 50,
              observed_standard_usage_credits: 6000,
              projected_weekly_credits: 12000,
              ci_low: 10000,
              ci_high: 14000,
            },
            {
              label: 'Reset Jun 21',
              start_event_timestamp: '2026-06-15T00:00:00Z',
              confidence: 'high',
              rate_limit_plan_type: 'pro',
              observed_usage_delta_percent: 60,
              observed_standard_usage_credits: 24000,
              projected_weekly_credits: 40000,
              ci_low: 36000,
              ci_high: 44000,
            },
          ],
        },
      },
      thread_cost_curves: { threads: [] },
      model_highlights: {},
    },
  },
});
console.log(JSON.stringify({
  trendLineCount: (html.match(/diagnostics-trend-line/g) || []).length,
  trendLabel: html.includes('Trend per plan'),
  markerCount: (html.match(/<circle /g) || []).length,
  hasSparseSubtitle: html.includes('trend requires 3+ medium/high windows per plan'),
}));
"""
    )

    assert payload["trendLineCount"] == 0
    assert payload["trendLabel"] is False
    assert payload["markerCount"] == 3
    assert payload["hasSparseSubtitle"] is True


def test_dashboard_weekly_projection_scales_many_windows() -> None:
    payload = _run_snapshot_renderer_script(
        """
const renderer = factory.create({
  escapeHtml,
  formatTimestamp: value => value,
  number: new Intl.NumberFormat('en-US'),
  pct: value => `${Math.round(Number(value || 0) * 100)}%`,
  renderState: message => `<div>${escapeHtml(message)}</div>`,
  rowInvestigatorLink: () => '<a>1,000</a>',
  tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
});
const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const points = Array.from({ length: 50 }, (_, index) => {
  const reset = new Date(Date.UTC(2026, 0, 5 + (index * 7)));
  const day = String(reset.getUTCDate()).padStart(2, '0');
  const month = monthNames[reset.getUTCMonth()];
  const projected = 34000 + Math.round(Math.sin(index / 4) * 3000) + (index * 50);
  return {
    label: `Reset ${month} ${day}`,
    start_event_timestamp: reset.toISOString(),
    confidence: 'high',
    rate_limit_plan_type: 'pro',
    observed_usage_delta_percent: 35,
    observed_standard_usage_credits: projected * 0.35,
    projected_weekly_credits: projected,
    ci_low: projected - 4000,
    ci_high: projected + 4000,
  };
});
const html = renderer.renderPanels({
  loading: false,
  payloads: {
    usageDrain: {
      status: 'ready',
      refreshed: false,
      snapshot: {
        computed_at: '2026-06-20T00:00:00Z',
        history_scope: 'active',
        source_logs_scanned: 1,
      },
      summary: { usage_rows: 50 },
      time_series: {
        weekly_credit_projection: { points },
      },
      thread_cost_curves: { threads: [] },
      model_highlights: {},
    },
  },
});
console.log(JSON.stringify({
  hasXwideChart: html.includes('diagnostics-line-chart-xwide'),
  hasXwideTitle: html.includes('diagnostics-chart-title-xwide'),
  hasXwideLegend: html.includes('diagnostics-chart-legend-xwide'),
  hasXwideViewBox: html.includes('viewBox="0 0 2200 300"'),
  markerCount: (html.match(/<circle /g) || []).length,
  axisLabelCount: (html.match(/>[A-Z][a-z]{2} \\d{2}<\\/text>/g) || []).length,
  hasResetAxisLabel: html.includes('>Reset Jan 05</text>'),
  trendLabel: html.includes('Trend per plan'),
}));
"""
    )

    assert payload["hasXwideChart"] is True
    assert payload["hasXwideTitle"] is True
    assert payload["hasXwideLegend"] is True
    assert payload["hasXwideViewBox"] is True
    assert payload["markerCount"] == 50
    assert payload["axisLabelCount"] <= 14
    assert payload["hasResetAxisLabel"] is False
    assert payload["trendLabel"] is True


def test_dashboard_weekly_projection_uses_time_spacing() -> None:
    payload = _run_snapshot_renderer_script(
        """
        const renderer = factory.create({
          escapeHtml,
          formatTimestamp: value => value,
          number: new Intl.NumberFormat('en-US'),
          pct: value => `${Math.round(Number(value || 0) * 100)}%`,
          renderState: message => `<div>${escapeHtml(message)}</div>`,
          rowInvestigatorLink: () => '<a>1,000</a>',
          tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
        });
        const points = [
          {
            label: 'Reset Jan 01',
            start_event_timestamp: '2026-01-01T00:00:00Z',
            confidence: 'high',
            rate_limit_plan_type: 'pro',
            observed_usage_delta_percent: 35,
            observed_standard_usage_credits: 12000,
            projected_weekly_credits: 34000,
            ci_low: 30000,
            ci_high: 38000,
          },
          {
            label: 'Reset Jan 02',
            start_event_timestamp: '2026-01-02T00:00:00Z',
            confidence: 'high',
            rate_limit_plan_type: 'pro',
            observed_usage_delta_percent: 35,
            observed_standard_usage_credits: 12600,
            projected_weekly_credits: 36000,
            ci_low: 32000,
            ci_high: 40000,
          },
          {
            label: 'Reset Jan 08',
            start_event_timestamp: '2026-01-08T00:00:00Z',
            confidence: 'high',
            rate_limit_plan_type: 'pro',
            observed_usage_delta_percent: 35,
            observed_standard_usage_credits: 14000,
            projected_weekly_credits: 40000,
            ci_low: 36000,
            ci_high: 44000,
          },
        ];
        const html = renderer.renderPanels({
          loading: false,
          payloads: {
            usageDrain: {
              status: 'ready',
              refreshed: false,
              snapshot: {
                computed_at: '2026-06-20T00:00:00Z',
                history_scope: 'active',
                source_logs_scanned: 1,
              },
              summary: { usage_rows: 3 },
              time_series: {
                weekly_credit_projection: { points },
              },
              thread_cost_curves: { threads: [] },
              model_highlights: {},
            },
          },
        });
        const circleXs = Array.from(html.matchAll(/<circle cx="([0-9.]+)"/g))
          .map(match => Number(match[1]));
        const firstGap = circleXs[1] - circleXs[0];
        const secondGap = circleXs[2] - circleXs[1];
        console.log(JSON.stringify({
          circleXs,
          firstGap,
          secondGap,
          usesUnevenTimeSpacing: secondGap > firstGap * 3,
        }));
        """
    )

    assert len(payload["circleXs"]) == 3
    assert payload["firstGap"] > 0
    assert payload["secondGap"] > payload["firstGap"] * 3
    assert payload["usesUnevenTimeSpacing"] is True


def test_dashboard_weekly_projection_suppresses_overlapping_reset_labels() -> None:
    payload = _run_snapshot_renderer_script(
        """
        const renderer = factory.create({
          escapeHtml,
          formatTimestamp: value => value,
          number: new Intl.NumberFormat('en-US'),
          pct: value => `${Math.round(Number(value || 0) * 100)}%`,
          renderState: message => `<div>${escapeHtml(message)}</div>`,
          rowInvestigatorLink: () => '<a>1,000</a>',
          tokenText: value => new Intl.NumberFormat('en-US').format(Number(value || 0)),
        });
        const resetDates = [
          ['2026-06-07', 'Reset Jun 07'],
          ['2026-06-11', 'Reset Jun 11'],
          ['2026-06-12', 'Reset Jun 12'],
          ['2026-06-19', 'Reset Jun 19'],
          ['2026-06-24', 'Reset Jun 24'],
          ['2026-07-01', 'Reset Jul 01'],
          ['2026-07-06', 'Reset Jul 06'],
        ];
        const points = resetDates.map(([date, label], index) => ({
          label,
          week_key: `pro:codex:${date}`,
          confidence: 'high',
          rate_limit_plan_type: 'pro',
          observed_usage_delta_percent: 35,
          observed_standard_usage_credits: 12000 + index,
          projected_weekly_credits: 34000 + (index * 1000),
          ci_low: 30000 + (index * 1000),
          ci_high: 38000 + (index * 1000),
        }));
        const html = renderer.renderPanels({
          loading: false,
          payloads: {
            usageDrain: {
              status: 'ready',
              refreshed: false,
              snapshot: {
                computed_at: '2026-06-20T00:00:00Z',
                history_scope: 'active',
                source_logs_scanned: 1,
              },
              summary: { usage_rows: points.length },
              time_series: {
                weekly_credit_projection: { points },
              },
              thread_cost_curves: { threads: [] },
              model_highlights: {},
            },
          },
        });
        const labels = Array.from(html.matchAll(/<text [^>]*>([^<]+)<\\/text>/g))
          .map(match => match[1])
          .filter(text => /Jun|Jul/.test(text));
        console.log(JSON.stringify({
          labels,
          markerCount: (html.match(/<circle /g) || []).length,
          hasJun11: labels.includes('Jun 11'),
          hasJun12: labels.includes('Jun 12'),
        }));
        """
    )

    assert payload["markerCount"] == 7
    assert len(payload["labels"]) < payload["markerCount"]
    assert not (payload["hasJun11"] and payload["hasJun12"])
