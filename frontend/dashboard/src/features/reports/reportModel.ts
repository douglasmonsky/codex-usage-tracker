import type { BarDatum, CallRow, DashboardModel, ReportSummary, Series } from '../../api/types';

export type ReportView = ReportSummary & { key?: string };

export type ReportDetails = {
  eyebrow: string;
  finding: string;
  method: string;
  caveat: string;
  selection: string;
  chartLabel: string;
};

export function reportKey(report: ReportView | undefined): string {
  if (report?.key) return report.key;
  const text = reportText(report);
  if (text.includes('fast')) return 'fast-mode-proxy';
  if (text.includes('cost') || text.includes('thread')) return 'cost-curves';
  if (text.includes('remaining')) return 'usage-remaining';
  if (text.includes('allowance')) return 'allowance-change';
  if (text.includes('weekly')) return 'weekly-credits';
  if (text.includes('drain')) return 'usage-drain-model';
  return text.replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'report';
}

export function reportFromUrl(reports: ReportView[]): ReportView | undefined {
  const id = new URLSearchParams(window.location.search).get('report')?.trim();
  return id ? reports.find(report => reportKey(report) === id || report.title === id) : undefined;
}

export function syncReportUrl(report: ReportView): void {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'reports');
  url.searchParams.set('report', reportKey(report));
  window.history.replaceState(null, '', url);
}

export function reportEvidenceCalls(report: ReportView | undefined, calls: CallRow[]): CallRow[] {
  const text = reportText(report);
  const rows = [...calls];
  if (text.includes('fast')) {
    return rows
      .filter(call => call.fast || call.effort.toLowerCase() === 'low')
      .sort((left, right) => left.durationSeconds - right.durationSeconds || callCredits(right) - callCredits(left))
      .slice(0, 8);
  }
  if (text.includes('cost') || text.includes('thread')) {
    return rows.sort((left, right) => right.cost - left.cost || right.totalTokens - left.totalTokens).slice(0, 8);
  }
  return rows.sort((left, right) => callCredits(right) - callCredits(left) || right.totalTokens - left.totalTokens).slice(0, 8);
}

export function reportDetails(report: ReportView | undefined, calls: CallRow[]): ReportDetails {
  const text = reportText(report);
  if (text.includes('fast')) {
    return {
      eyebrow: 'Speed proxy',
      finding: `${calls.length} loaded calls are fast-tagged or low effort. Duration is a proxy, not a quality score.`,
      method: 'Filter fast-tagged and low-effort calls, then order by shortest duration and credit impact.',
      caveat: 'Aggregate timing cannot distinguish model latency from tool, network, or queue time.',
      selection: 'Fast/low-effort candidates · shortest duration first · top 8',
      chartLabel: 'Calls',
    };
  }
  if (text.includes('cost') || text.includes('thread')) {
    return {
      eyebrow: 'Cost concentration',
      finding: `${calls.length} highest-cost loaded calls anchor this report. Estimates use the local pricing model.`,
      method: 'Rank aggregate calls by estimated cost, breaking ties with total token volume.',
      caveat: 'Estimated local cost may differ from billing and excludes costs not represented in loaded rows.',
      selection: 'Highest estimated cost · token volume tie-break · top 8',
      chartLabel: 'USD',
    };
  }
  return {
    eyebrow: 'Usage trajectory',
    finding: `${calls.length} highest credit-impact loaded calls support the selected usage report.`,
    method: 'Rank aggregate calls by estimated Codex credit impact and compare the selected time series.',
    caveat: 'Allowance and credit projections are local observations, not universal account limits.',
    selection: 'Highest credit impact · token volume tie-break · top 8',
    chartLabel: text.includes('remaining') || text.includes('allowance') ? 'Percent' : 'Credits',
  };
}

export function reportLineSeries(report: ReportView | undefined, model: DashboardModel): Series[] {
  const text = reportText(report);
  if (text.includes('remaining') || text.includes('allowance')) return model.usageRemainingSeries;
  if (text.includes('drain')) return model.actualVsPredictedSeries;
  return model.weeklyCreditSeries;
}

export function reportBarData(report: ReportView | undefined, model: DashboardModel, calls: CallRow[]): BarDatum[] | null {
  const text = reportText(report);
  if (text.includes('cost') || text.includes('thread')) {
    return model.threads.slice(0, 10).map(thread => ({ label: thread.name, value: thread.cost }));
  }
  if (!text.includes('fast')) return null;
  const durations = calls.map(call => call.durationSeconds).filter(value => Number.isFinite(value) && value >= 0);
  return [
    { label: 'Under 5s', value: durations.filter(value => value < 5).length },
    { label: '5-15s', value: durations.filter(value => value >= 5 && value < 15).length },
    { label: '15-30s', value: durations.filter(value => value >= 15 && value < 30).length },
    { label: '30s+', value: durations.filter(value => value >= 30).length },
  ];
}

export function callCredits(call: CallRow): number {
  return call.credits > 0 ? call.credits : call.cost * 25;
}

function reportText(report: ReportView | undefined): string {
  return (report?.title ?? '').toLowerCase();
}
