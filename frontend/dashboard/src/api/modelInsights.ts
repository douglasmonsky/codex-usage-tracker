import type { BarDatum, CallRow, Finding, ReportSummary } from './types';

const modelCostPalette = ['#2563eb', '#1d4ed8', '#059669', '#f59e0b', '#94a3b8'];

export function buildModelCosts(calls: CallRow[]): BarDatum[] {
  const byModel = new Map<string, number>();
  calls.forEach(call => {
    const label = call.model || 'unknown';
    byModel.set(label, (byModel.get(label) ?? 0) + call.cost);
  });
  const entries = [...byModel.entries()].sort((left, right) => {
    const costDelta = right[1] - left[1];
    return costDelta || left[0].localeCompare(right[0]);
  });
  const topEntries = entries.length > 5
    ? [...entries.slice(0, 4), ['other', entries.slice(4).reduce((sum, entry) => sum + entry[1], 0)] as [string, number]]
    : entries;
  return topEntries.map(([label, value], index) => ({
    label,
    value,
    color: modelCostPalette[index] ?? '#94a3b8',
  }));
}

export function buildFindings(calls: CallRow[]): Finding[] {
  if (!calls.length) return [];
  const totalImpact = Math.max(calls.reduce((sum, call) => sum + impactScore(call), 0), 1);
  return [
    longThreadFinding(calls, totalImpact),
    cacheMissFinding(calls, totalImpact),
    highEffortFinding(calls, totalImpact),
    outputVolumeFinding(calls, totalImpact),
  ]
    .filter((finding): finding is Finding => Boolean(finding))
    .sort((left, right) => right.credits - left.credits)
    .map((finding, index) => ({ ...finding, rank: index + 1 }));
}

export function buildReports(calls: CallRow[]): ReportSummary[] {
  if (!calls.length) return [];
  const reports: ReportSummary[] = [
    {
      title: 'Cost Curves',
      status: 'Ready',
      owner: 'Threads',
      description: 'Estimated cost concentration by loaded aggregate thread.',
    },
    {
      title: 'Usage Drain Model',
      status: 'Ready',
      owner: 'Reports',
      description: 'Highest estimated credit-impact calls from loaded aggregate rows.',
    },
  ];
  if (calls.some(call => call.fastProxyCandidate || call.effort.toLowerCase() === 'low')) {
    reports.push({
      title: 'Fast Mode Proxy',
      status: 'Ready',
      owner: 'Calls',
      description: 'Low-effort and fast-call candidates inferred from aggregate rows.',
    });
  }
  return reports;
}

function longThreadFinding(calls: CallRow[], totalImpact: number): Finding | null {
  const byThread = new Map<string, CallRow[]>();
  calls.forEach(call => byThread.set(call.thread, [...(byThread.get(call.thread) ?? []), call]));
  const [thread, rows] = [...byThread.entries()].sort((left, right) => {
    const tokenDelta = sumCalls(right[1], call => call.totalTokens) - sumCalls(left[1], call => call.totalTokens);
    return tokenDelta || right[1].length - left[1].length;
  })[0] ?? [];
  if (!thread || !rows?.length || rows.length < 2) return null;
  const impact = sumCalls(rows, impactScore);
  return {
    rank: 0,
    title: `Long Thread: ${thread}`,
    severity: impact / totalImpact >= 0.25 || rows.length >= 8 ? 'High' : 'Medium',
    credits: Math.round(impact),
    share: impact / totalImpact * 100,
    summary: `${rows.length.toLocaleString()} loaded calls and ${sumCalls(rows, call => call.totalTokens).toLocaleString()} tokens in this thread.`,
  };
}

function cacheMissFinding(calls: CallRow[], totalImpact: number): Finding | null {
  const rows = calls.filter(call => call.signal === 'cache-risk' || call.cachedPct < 35 || call.uncachedInput > 50_000);
  if (!rows.length) return null;
  const impact = sumCalls(rows, impactScore);
  return {
    rank: 0,
    title: 'Cache Misses (Large Inputs)',
    severity: rows.some(call => call.cachedPct < 20 || call.uncachedInput > 50_000) ? 'High' : 'Medium',
    credits: Math.round(impact),
    share: impact / totalImpact * 100,
    summary: `${rows.length.toLocaleString()} loaded calls show low cache reuse or large uncached input.`,
  };
}

function highEffortFinding(calls: CallRow[], totalImpact: number): Finding | null {
  const rows = calls.filter(call => call.effort.toLowerCase() === 'high' || call.reasoningOutput > 0);
  if (!rows.length) return null;
  const impact = sumCalls(rows, impactScore);
  return {
    rank: 0,
    title: 'High Model Effort',
    severity: impact / totalImpact >= 0.25 ? 'High' : 'Medium',
    credits: Math.round(impact),
    share: impact / totalImpact * 100,
    summary: `${rows.length.toLocaleString()} loaded calls use high effort or report reasoning output.`,
  };
}

function outputVolumeFinding(calls: CallRow[], totalImpact: number): Finding | null {
  const threshold = Math.max(25_000, percentile(calls.map(call => call.output), 0.75));
  const rows = calls.filter(call => call.output >= threshold || call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)));
  if (!rows.length) return null;
  const impact = sumCalls(rows, impactScore);
  return {
    rank: 0,
    title: 'Tool Output Volume',
    severity: rows.some(call => call.output > 50_000) ? 'High' : 'Medium',
    credits: Math.round(impact),
    share: impact / totalImpact * 100,
    summary: `${rows.length.toLocaleString()} loaded calls have high output volume or file-heavy/subagent tags.`,
  };
}

function impactScore(call: CallRow): number {
  return call.credits > 0 ? call.credits : call.cost * 25;
}

function sumCalls(calls: CallRow[], selector: (call: CallRow) => number): number {
  return calls.reduce((sum, call) => sum + selector(call), 0);
}

function percentile(values: number[], ratio: number): number {
  const sorted = values.filter(value => Number.isFinite(value)).sort((left, right) => left - right);
  if (!sorted.length) return 0;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * ratio)))] ?? 0;
}
