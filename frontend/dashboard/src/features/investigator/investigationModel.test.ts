import { describe, expect, it } from 'vitest';

import type { AgenticInvestigationPayload } from '../../api/investigations';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { validateVisualizationSpec } from '../../visualization';
import { fallbackDiagnosticSnapshots } from '../diagnostics/diagnosticSnapshotFallbacks';
import { buildInvestigationWorkspace, buildWasteFingerprintSpec } from './investigationModel';

describe('investigation workspace model', () => {
  it('builds a feature-complete aggregate fallback and valid fingerprint matrix', () => {
    const workspace = buildInvestigationWorkspace(
      fixtureModel,
      undefined,
      fallbackDiagnosticSnapshots(fixtureModel),
    );
    const categories = new Set(workspace.findings.map(finding => finding.category));
    const spec = buildWasteFingerprintSpec(workspace.findings, 'active', 'fixture-revision');

    expect(workspace.live).toBe(false);
    for (const category of [
      'Cache/context',
      'Tool output',
      'File rediscovery',
      'File modifications',
      'Concentration',
      'Guided summary',
    ]) {
      expect(categories.has(category)).toBe(true);
    }
    expect(workspace.evidence.some(row => row.recordId.startsWith('fixture-call-'))).toBe(true);
    expect(validateVisualizationSpec(spec)).toEqual([]);
    expect(spec.state.kind).toBe('ready');
    expect(workspace.findings.find(finding => finding.title.startsWith('Long Thread:'))?.category)
      .toBe('Usage driver');

    const snapshotSpec = buildWasteFingerprintSpec(workspace.findings, 'active', '');
    expect(snapshotSpec.freshness.generatedAt).toBe('loaded-aggregate-snapshot');
    expect(validateVisualizationSpec(snapshotSpec)).toEqual([]);
  });

  it('preserves the shared agentic evidence envelope and deterministic actions', () => {
    const payload: AgenticInvestigationPayload = {
      schema: 'codex-usage-tracker-agentic-investigation-v1',
      content_mode: 'aggregate_investigation',
      includes_indexed_content: false,
      includes_raw_fragments: false,
      privacy_mode: 'normal',
      goal: 'token_waste',
      filters: {},
      summary: {
        finding_count: 1,
        top_finding: 'Repeated shell command churn',
        confidence: 'medium',
        source_reports: ['codex-usage-tracker-shell-churn-v1'],
      },
      findings: [{
        finding: 'Repeated shell command churn',
        evidence_count: 1,
        evidence_summary: { row_count: 1, total_occurrences: 9, total_tokens: 44_000 },
        evidence: [{
          record_id: 'call-shell-1',
          thread_name: 'thread-shell',
          command_family: 'rg',
          occurrences: 9,
          total_tokens: 44_000,
          candidate_explanation: 'repeated inspection sequence',
        }],
        confidence: 'medium',
        why_it_matters: 'Repeated probing adds avoidable context and tool output.',
        recommended_action: 'Use one scoped inspection task.',
        verify_with: ['usage_shell_churn', 'usage_thread_trace'],
        missing_access: 'Command intent is not known.',
        privacy_notes: 'No raw command output included.',
      }],
      recommended_next_tools: [],
      caveats: ['Local evidence only.'],
    };

    const workspace = buildInvestigationWorkspace(fixtureModel, payload, {});
    const finding = workspace.findings.find(row => row.title === 'Repeated shell command churn');

    expect(workspace.live).toBe(true);
    expect(workspace.sourceReports).toEqual(['codex-usage-tracker-shell-churn-v1']);
    expect(finding).toMatchObject({
      category: 'Shell churn',
      confidence: 'medium',
      action: 'Use one scoped inspection task.',
      evidenceCount: 1,
    });
    expect(finding?.evidence[0]).toMatchObject({
      recordId: 'call-shell-1',
      thread: 'thread-shell',
      pattern: 'rg',
      events: 9,
      tokens: 44_000,
    });
  });
});
