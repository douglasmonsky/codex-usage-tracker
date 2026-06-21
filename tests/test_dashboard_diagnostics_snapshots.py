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
    repo_root = Path(__file__).resolve().parents[1]
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
