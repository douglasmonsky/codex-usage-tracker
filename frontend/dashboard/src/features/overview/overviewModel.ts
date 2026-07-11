import type { DashboardScopeSummary } from '../../api/dashboardDataScope';
import type { CallRow, DashboardModel } from '../../api/types';
import type {
  OverviewRecommendationRow,
  OverviewRecommendationsReport,
  OverviewSummaryReport,
} from '../../data/contracts/overview';
import type { OverviewEndpointBundle } from '../../data/overviewQueries';
import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type FlowVisualizationSpecV1,
  type VisualizationDataState,
  type VisualizationRecord,
} from '../../visualization';

export type OverviewFindingView = {
  id: string;
  title: string;
  why: string;
  nextAction: string;
  severity: 'high' | 'medium' | 'review';
  evidenceGrade: 'Strong' | 'Moderate' | 'Limited';
  supportCount: number;
  scope: string;
  freshness: string;
  recordId: string;
  legacyRank?: number;
};

export type OverviewLoadedMetrics = {
  basis: 'scope' | 'loaded';
  calls: number;
  totalTokens: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  cachePercent: number;
  estimatedCredits: number;
};

export type OverviewViewModel = {
  answer: {
    title: string;
    detail: string;
    action: string;
    tone: 'positive' | 'caution' | 'risk';
  };
  findings: OverviewFindingView[];
  metrics: OverviewLoadedMetrics;
  pulseSpec: CartesianVisualizationSpecV1;
  tokenFlowSpec: FlowVisualizationSpecV1;
};

export function buildOverviewViewModel(
  model: DashboardModel,
  endpoints: OverviewEndpointBundle | undefined,
  historyScope: 'active' | 'all',
): OverviewViewModel {
  const metrics = scopeMetrics(model.scopeSummary) ?? loadedMetrics(model.calls);
  const findings = endpointFindings(endpoints?.recommendations.data) ?? fallbackFindings(model);
  const topFinding = findings[0];
  return {
    answer: topFinding
      ? {
          title: `${topFinding.title} is the clearest current signal`,
          detail: `${topFinding.why} ${supportLabel(topFinding.supportCount)}`,
          action: topFinding.nextAction,
          tone: topFinding.severity === 'high' ? 'risk' : 'caution',
        }
      : {
          title: metrics.calls ? 'No rule-based usage issue stands out' : 'Load calls to establish a usage baseline',
          detail: metrics.calls
            ? `The current ${scopeLabel(historyScope)} has no ranked recommendation with direct aggregate evidence.`
            : 'The Overview needs aggregate calls before it can rank evidence or build token accounting.',
          action: metrics.calls ? 'Continue monitoring and investigate any workflow that feels unexpectedly expensive.' : 'Load recent calls or all history.',
          tone: 'positive',
        },
    findings,
    metrics,
    pulseSpec: usagePulseSpec(model, endpoints?.summary, historyScope),
    tokenFlowSpec: tokenAccountingSpec(model.calls, metrics, historyScope),
  };
}

function endpointFindings(report: OverviewRecommendationsReport | null | undefined): OverviewFindingView[] | null {
  if (!report) return null;
  const groups = new Map<string, OverviewRecommendationRow[]>();
  for (const row of report.rows) {
    const key = row.primaryRecommendation?.key;
    if (!key) continue;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups.entries()]
    .map(([key, rows]) => recommendationFinding(key, rows, report.includeArchived))
    .sort((left, right) => severityRank(right.severity) - severityRank(left.severity) || right.supportCount - left.supportCount)
    .slice(0, 6);
}

function recommendationFinding(
  key: string,
  rows: OverviewRecommendationRow[],
  includeArchived: boolean,
): OverviewFindingView {
  const top = [...rows].sort((left, right) => right.recommendationScore - left.recommendationScore)[0];
  const recommendation = top.primaryRecommendation!;
  const completeEvidence = rows.filter(row => row.recordId && row.eventTimestamp).length;
  return {
    id: key,
    title: recommendation.title,
    why: recommendation.why,
    nextAction: recommendation.action || top.recommendedAction,
    severity: recommendation.severity,
    evidenceGrade: completeEvidence >= 3 ? 'Strong' : completeEvidence ? 'Moderate' : 'Limited',
    supportCount: rows.length,
    scope: includeArchived ? 'All history' : 'Active history',
    freshness: latestTimestamp(rows.map(row => row.eventTimestamp)),
    recordId: top.recordId,
  };
}

function fallbackFindings(model: DashboardModel): OverviewFindingView[] {
  return model.findings.slice(0, 6).map(finding => ({
    id: `legacy-${finding.rank}`,
    title: finding.title,
    why: finding.summary,
    nextAction: 'Review the loaded aggregate evidence in Investigate.',
    severity: finding.severity === 'High' ? 'high' : finding.severity === 'Medium' ? 'medium' : 'review',
    evidenceGrade: 'Limited',
    supportCount: 1,
    scope: 'Loaded snapshot',
    freshness: latestTimestamp(model.calls.map(call => call.eventTimestamp)),
    recordId: '',
    legacyRank: finding.rank,
  }));
}

function loadedMetrics(calls: CallRow[]): OverviewLoadedMetrics {
  const totals = calls.reduce(
    (sum, call) => ({
      totalTokens: sum.totalTokens + call.totalTokens,
      cachedInputTokens: sum.cachedInputTokens + call.cachedInput,
      uncachedInputTokens: sum.uncachedInputTokens + call.uncachedInput,
      outputTokens: sum.outputTokens + call.output,
      reasoningOutputTokens: sum.reasoningOutputTokens + call.reasoningOutput,
      estimatedCredits: sum.estimatedCredits + call.credits,
    }),
    { totalTokens: 0, cachedInputTokens: 0, uncachedInputTokens: 0, outputTokens: 0, reasoningOutputTokens: 0, estimatedCredits: 0 },
  );
  const inputTokens = totals.cachedInputTokens + totals.uncachedInputTokens;
  return {
    basis: 'loaded',
    calls: calls.length,
    ...totals,
    cachePercent: inputTokens > 0 ? (totals.cachedInputTokens / inputTokens) * 100 : 0,
  };
}

function scopeMetrics(summary: DashboardScopeSummary | undefined): OverviewLoadedMetrics | null {
  if (!summary) return null;
  return {
    basis: 'scope',
    calls: summary.visibleCalls,
    totalTokens: summary.totalTokens,
    cachedInputTokens: summary.cachedInputTokens,
    uncachedInputTokens: summary.uncachedInputTokens,
    outputTokens: summary.outputTokens,
    reasoningOutputTokens: summary.reasoningOutputTokens,
    cachePercent: summary.inputTokens > 0 ? (summary.cachedInputTokens / summary.inputTokens) * 100 : 0,
    estimatedCredits: summary.usageCredits,
  };
}

function usagePulseSpec(
  model: DashboardModel,
  summary: { data: OverviewSummaryReport | null; error: string | null } | undefined,
  historyScope: 'active' | 'all',
): CartesianVisualizationSpecV1 {
  const summaryRows = summary?.data?.rows
    .map(row => ({
      id: row.groupKey,
      day: row.groupKey,
      inputTokens: row.inputTokens,
      cachedTokens: row.cachedInputTokens,
      outputTokens: row.outputTokens,
      calls: row.modelCalls,
    }))
    .sort((left, right) => left.day.localeCompare(right.day));
  const rows = summaryRows?.length ? summaryRows : loadedPulseRows(model);
  const state: VisualizationDataState = rows.length
    ? summary?.error
      ? { kind: 'partial', message: 'Focused summary unavailable; showing loaded call rows.', availableRows: rows.length }
      : { kind: 'ready' }
    : { kind: 'empty', message: 'No dated aggregate usage is available in this scope.' };
  const latest = latestTimestamp(summary?.data?.rows.map(row => row.latestEvent) ?? model.calls.map(call => call.eventTimestamp));
  const pulseMark = rows.length <= 3 ? 'bar' : 'line';
  return {
    schema: visualizationSpecSchema,
    id: 'overview-usage-pulse',
    title: 'Recent token movement',
    description: 'Daily input, cached reuse, and output volume in the selected history scope.',
    state,
    scope: { label: scopeLabel(historyScope), rowCount: rows.length, historyScope },
    freshness: { generatedAt: latest || new Date().toISOString() },
    caveats: [summary?.error ?? 'Daily aggregates describe local records; they do not represent OpenAI billing.'],
    accessibility: { summary: usagePulseSummary(rows) },
    table: {
      caption: 'Daily token movement',
      columns: [
        { field: 'day', label: 'Day', type: 'time' },
        { field: 'inputTokens', label: 'Input', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'cachedTokens', label: 'Cached', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'outputTokens', label: 'Output', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'calls', label: 'Calls', type: 'number', unit: 'count', align: 'right' },
      ],
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'day' },
      zoom: { axis: 'x', startPercent: rows.length > 30 ? ((rows.length - 30) / rows.length) * 100 : 0, endPercent: 100 },
    },
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'day', label: 'Day', type: 'category' },
      y: { field: 'inputTokens', label: 'Tokens', type: 'number', unit: 'tokens', min: 0 },
    },
    series: [
      { id: 'input', label: 'Input', mark: pulseMark, xField: 'day', yField: 'inputTokens', color: '#2f6fed' },
      { id: 'cached', label: 'Cached', mark: pulseMark, xField: 'day', yField: 'cachedTokens', color: '#16866b' },
      { id: 'output', label: 'Output', mark: pulseMark, xField: 'day', yField: 'outputTokens', color: '#7651c9' },
    ],
  };
}

function tokenAccountingSpec(
  calls: CallRow[],
  metrics: OverviewLoadedMetrics,
  historyScope: 'active' | 'all',
): FlowVisualizationSpecV1 {
  const scopeMetricsAvailable = metrics.basis === 'scope';
  const accountingLabel = scopeMetricsAvailable ? 'Scope accounting' : 'Loaded accounting';
  const callsLabel = scopeMetricsAvailable ? 'calls in selected scope' : 'loaded calls';
  const generated = metrics.outputTokens + metrics.reasoningOutputTokens;
  const input = metrics.cachedInputTokens + metrics.uncachedInputTokens;
  const links = [
    { id: 'account-input', source: 'account', target: 'input', value: input, evidenceKey: 'reported:input' },
    { id: 'account-generated', source: 'account', target: 'generated', value: generated, evidenceKey: 'reported:generated' },
    { id: 'input-cached', source: 'input', target: 'cached', value: metrics.cachedInputTokens, evidenceKey: 'reported:cached-input' },
    { id: 'input-uncached', source: 'input', target: 'uncached', value: metrics.uncachedInputTokens, evidenceKey: 'derived:uncached-input' },
    { id: 'generated-visible', source: 'generated', target: 'output', value: metrics.outputTokens, evidenceKey: 'reported:output' },
    { id: 'generated-reasoning', source: 'generated', target: 'reasoning', value: metrics.reasoningOutputTokens, evidenceKey: 'reported:reasoning-output' },
  ].filter(link => link.value > 0);
  return {
    schema: visualizationSpecSchema,
    id: 'overview-token-accounting',
    title: scopeMetricsAvailable ? 'Token accounting in scope' : 'Loaded token accounting',
    description: scopeMetricsAvailable
      ? 'The four reported token categories across the complete selected data scope.'
      : 'The four reported token categories across calls currently loaded in the dashboard.',
    state: links.length ? { kind: 'ready' } : { kind: 'empty', message: 'No token accounting is available in this scope.' },
    scope: { label: `${metrics.calls.toLocaleString()} ${callsLabel}`, rowCount: metrics.calls, historyScope },
    freshness: { generatedAt: latestTimestamp(calls.map(call => call.eventTimestamp)) || new Date().toISOString() },
    caveats: ['Categories mirror reported fields and may overlap; flow widths are accounting, not causality or billed cost.'],
    accessibility: { summary: tokenAccountingSummary(metrics) },
    table: {
      caption: `${accountingLabel} categories`,
      columns: [
        { field: 'source', label: 'From', type: 'text' },
        { field: 'target', label: 'To', type: 'text' },
        { field: 'value', label: 'Tokens', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'evidenceKey', label: 'Basis', type: 'text' },
      ],
      defaultSort: { field: 'value', direction: 'desc' },
    },
    interactions: { selection: { keyField: 'id' } },
    kind: 'flow',
    encoding: { sourceLabel: 'Category', targetLabel: 'Reported type', valueLabel: 'Tokens', valueUnit: 'tokens' },
    data: {
      nodes: [
        { id: 'account', label: accountingLabel, color: '#2f6fed' },
        { id: 'input', label: 'Input accounting', color: '#2f6fed' },
        { id: 'generated', label: 'Generated accounting', color: '#7651c9' },
        { id: 'cached', label: 'Cached input', color: '#16866b' },
        { id: 'uncached', label: 'Uncached input', color: '#9a5900' },
        { id: 'output', label: 'Output', color: '#16866b' },
        { id: 'reasoning', label: 'Reasoning output', color: '#7651c9' },
      ],
      links,
    },
  };
}

function loadedPulseRows(model: DashboardModel): VisualizationRecord[] {
  const buckets = new Map<string, { inputTokens: number; cachedTokens: number; outputTokens: number; calls: number }>();
  for (const call of model.calls) {
    const timestamp = Date.parse(call.eventTimestamp);
    if (!Number.isFinite(timestamp)) continue;
    const day = new Date(timestamp).toISOString().slice(0, 10);
    const bucket = buckets.get(day) ?? { inputTokens: 0, cachedTokens: 0, outputTokens: 0, calls: 0 };
    bucket.inputTokens += call.input;
    bucket.cachedTokens += call.cachedInput;
    bucket.outputTokens += call.output;
    bucket.calls += 1;
    buckets.set(day, bucket);
  }
  return [...buckets.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([day, values]) => ({ id: day, day, ...values }));
}

function usagePulseSummary(rows: VisualizationRecord[]): string {
  if (!rows.length) return 'No daily token movement is available.';
  return `${rows.length} daily buckets are available, with the visible window favoring the most recent ${Math.min(rows.length, 30)}.`;
}

function tokenAccountingSummary(metrics: OverviewLoadedMetrics): string {
  if (!metrics.calls) return 'No calls are available for token accounting.';
  const callsLabel = metrics.basis === 'scope' ? 'calls in the selected scope' : 'loaded calls';
  return `${metrics.calls} ${callsLabel} include ${Math.round(metrics.cachePercent)} percent cached input reuse.`;
}

function supportLabel(count: number): string {
  return count === 1 ? 'One ranked call supports this pattern.' : `${count} ranked calls support this pattern.`;
}

function scopeLabel(scope: 'active' | 'all'): string {
  return scope === 'all' ? 'all-history scope' : 'active-history scope';
}

function latestTimestamp(values: string[]): string {
  return values.filter(Boolean).sort((left, right) => Date.parse(right) - Date.parse(left))[0] ?? '';
}

function severityRank(severity: OverviewFindingView['severity']): number {
  return severity === 'high' ? 3 : severity === 'medium' ? 2 : 1;
}
