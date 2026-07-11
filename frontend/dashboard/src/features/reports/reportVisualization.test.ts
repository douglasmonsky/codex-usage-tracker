import { describe, expect, it } from 'vitest';

import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { validateVisualizationSpec } from '../../visualization';
import { reportEvidenceCalls } from './reportModel';
import { buildReportVisualizationSpec } from './reportVisualization';

const metadata = {
  generatedAt: '2026-07-11T12:00:00Z',
  historyScope: 'active' as const,
  source: 'fixture aggregates',
  sourceRevision: 'fixture-v1',
};

describe('report visualization contract', () => {
  it('builds valid report-specific semantic specs for every fixture report', () => {
    for (const report of fixtureModel.reports) {
      const calls = reportEvidenceCalls(report, fixtureModel.calls);
      const spec = buildReportVisualizationSpec(report, fixtureModel, calls, metadata);

      expect(validateVisualizationSpec(spec), report.title).toEqual([]);
      expect(spec.title).not.toBe(report.title);
      expect(spec.scope.historyScope).toBe('active');
      expect(spec.caveats?.join(' ')).toContain('Call Investigator');
    }
  });

  it('uses the right units and marks for cost, speed, and usage reports', () => {
    const byTitle = (title: string) => {
      const report = fixtureModel.reports.find(candidate => candidate.title === title);
      return buildReportVisualizationSpec(
        report,
        fixtureModel,
        reportEvidenceCalls(report, fixtureModel.calls),
        metadata,
      );
    };

    expect(byTitle('Cost Curves').axes.y.unit).toBe('usd');
    expect(byTitle('Cost Curves').series[0]?.mark).toBe('bar');
    expect(byTitle('Fast Mode Proxy').axes.y.unit).toBe('count');
    expect(byTitle('Fast Mode Proxy').series[0]?.mark).toBe('bar');
    expect(byTitle('Weekly Credits').axes.y.unit).toBe('credits');
    expect(byTitle('Weekly Credits').series[0]?.mark).toBe('line');
    expect(byTitle('Weekly Credits').series[0]?.label).toBe('Pro observed');
  });
});
