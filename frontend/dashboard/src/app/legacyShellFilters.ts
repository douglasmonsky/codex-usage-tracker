import { buildThreads } from '../api/client';
import { buildFindings, buildModelCosts, buildReports } from '../api/modelInsights';
import { buildOverviewSeriesFromDailyValues } from '../api/overviewSeries';
import type { CallRow, DashboardModel, MetricCard } from '../api/types';

type HistoryScope = 'active' | 'all';

export type LegacyShellFilters = {
  model: string;
  effort: string;
  confidence: string;
  datePreset: string;
  dateStart: string;
  dateEnd: string;
  active: boolean;
};

const dayMs = 24 * 60 * 60 * 1000;

export function modelWithLegacyShellFilters(
  model: DashboardModel,
  historyScope: HistoryScope,
  locationSearch = window.location.search,
): DashboardModel {
  const filters = readLegacyShellFilters(locationSearch);
  if (!filters.active) return model;
  const calls = model.calls.filter(call => callMatchesLegacyShellFilters(call, filters));
  if (calls.length === model.calls.length) return model;
  return deriveDashboardModelFromCalls(model, calls, `${historyScope} filtered`);
}

export function readLegacyShellFilters(locationSearch: string): LegacyShellFilters {
  const params = new URLSearchParams(locationSearch);
  const model = params.get('model')?.trim() ?? '';
  const effort = params.get('effort')?.trim() ?? '';
  const confidence = (params.get('confidence') || params.get('pricing'))?.trim() ?? '';
  const datePreset = (params.get('date') || params.get('time'))?.trim() ?? '';
  const dateStart = params.get('from')?.trim() ?? '';
  const dateEnd = params.get('to')?.trim() ?? '';
  return {
    model,
    effort,
    confidence,
    datePreset,
    dateStart,
    dateEnd,
    active: Boolean(model || effort || confidence || datePreset || dateStart || dateEnd),
  };
}

function callMatchesLegacyShellFilters(call: CallRow, filters: LegacyShellFilters): boolean {
  if (filters.model && call.model !== filters.model) return false;
  if (filters.effort && call.effort !== filters.effort) return false;
  if (filters.confidence && !callMatchesLegacyConfidence(call, filters.confidence)) return false;
  if (!callMatchesLegacyDate(call, filters)) return false;
  return true;
}

function callMatchesLegacyConfidence(call: CallRow, confidence: string): boolean {
  if (confidence === 'official' || confidence === 'cost-exact') return Boolean(call.pricingModel && !call.pricingEstimated);
  if (confidence === 'estimated' || confidence === 'cost-estimated') return call.pricingEstimated;
  if (confidence === 'unpriced' || confidence === 'cost-unpriced') return !call.pricingModel;
  if (confidence === 'credit-exact') return call.usageCreditConfidence === 'exact';
  if (confidence === 'credit-estimated') return call.usageCreditConfidence === 'estimated';
  if (confidence === 'credit-override') return call.usageCreditConfidence === 'user_override';
  if (confidence === 'credit-missing') return call.usageCreditConfidence === 'missing' || call.usageCreditConfidence === 'unknown';
  return true;
}

function callMatchesLegacyDate(call: CallRow, filters: LegacyShellFilters): boolean {
  const range = legacyShellDateRange(filters);
  if (!range.active) return true;
  if (range.invalid) return false;
  const timestamp = Date.parse(call.rawTime || call.time);
  if (!Number.isFinite(timestamp)) return false;
  if (range.start !== null && timestamp < range.start) return false;
  if (range.endExclusive !== null && timestamp >= range.endExclusive) return false;
  return true;
}

function legacyShellDateRange(filters: LegacyShellFilters): {
  active: boolean;
  invalid: boolean;
  start: number | null;
  endExclusive: number | null;
} {
  if (filters.datePreset && filters.datePreset !== 'all' && filters.datePreset !== 'custom') {
    const range = legacyPresetDateRange(filters.datePreset);
    return range ? { active: true, invalid: false, ...range } : { active: false, invalid: false, start: null, endExclusive: null };
  }
  const start = parseLegacyDate(filters.dateStart);
  const end = parseLegacyDate(filters.dateEnd);
  if (start !== null && end !== null && start > end) {
    return { active: true, invalid: true, start, endExclusive: end + dayMs };
  }
  return {
    active: start !== null || end !== null,
    invalid: false,
    start,
    endExclusive: end === null ? null : end + dayMs,
  };
}

function legacyPresetDateRange(preset: string): { start: number; endExclusive: number } | null {
  const today = localDayStart(new Date());
  if (preset === 'today') return { start: today, endExclusive: today + dayMs };
  if (preset === 'last-7-days') return { start: today - 6 * dayMs, endExclusive: today + dayMs };
  if (preset === 'this-week') {
    const date = new Date(today);
    const day = date.getDay();
    const offset = day === 0 ? -6 : 1 - day;
    const start = today + offset * dayMs;
    return { start, endExclusive: start + 7 * dayMs };
  }
  if (preset === 'this-month') {
    const date = new Date(today);
    const start = new Date(date.getFullYear(), date.getMonth(), 1).getTime();
    const endExclusive = new Date(date.getFullYear(), date.getMonth() + 1, 1).getTime();
    return { start, endExclusive };
  }
  return null;
}

function parseLegacyDate(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date.getTime();
}

function localDayStart(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

function deriveDashboardModelFromCalls(model: DashboardModel, calls: CallRow[], historyScope = 'filtered'): DashboardModel {
  const totalTokens = calls.reduce((sum, call) => sum + call.totalTokens, 0);
  const estimatedCost = calls.reduce((sum, call) => sum + call.cost, 0);
  const cachedTokens = calls.reduce((sum, call) => sum + call.cachedInput, 0);
  const uncachedTokens = calls.reduce((sum, call) => sum + call.uncachedInput, 0);
  const outputTokens = calls.reduce((sum, call) => sum + call.output, 0);
  const reasoningOutputTokens = calls.reduce((sum, call) => sum + call.reasoningOutput, 0);
  const inputTokens = calls.reduce((sum, call) => sum + call.input, 0);
  const cachePct = inputTokens > 0 ? (cachedTokens / inputTokens) * 100 : 0;
  const usageRemainingCard = model.cards.find(card => card.label === 'Usage Remaining') ?? {
    label: 'Usage Remaining',
    value: 'Unknown',
    detail: 'not available in filtered view',
    trend: 'not available in payload',
    tone: 'orange' as const,
  };
  return {
    ...model,
    cards: filteredCards({
      cachePct,
      cachedTokens,
      estimatedCost,
      historyScope,
      totalCalls: calls.length,
      totalTokens,
      tokenBreakdown: {
        cachedInput: cachedTokens,
        uncachedInput: uncachedTokens,
        output: outputTokens,
        reasoningOutput: reasoningOutputTokens,
      },
      usageRemainingCard,
    }),
    ...overviewSeriesFromCalls(calls),
    calls,
    threads: buildThreads(calls),
    findings: buildFindings(calls),
    modelCosts: buildModelCosts(calls),
    reports: buildReports(calls),
    cacheSegments: [
      { label: 'Cache read', value: cachePct, color: '#2563eb' },
      { label: 'Uncached input', value: Math.max(100 - cachePct, 0), color: '#7c3aed' },
    ],
  };
}

function filteredCards({
  cachePct,
  cachedTokens,
  estimatedCost,
  historyScope,
  totalCalls,
  totalTokens,
  tokenBreakdown,
  usageRemainingCard,
}: {
  cachePct: number;
  cachedTokens: number;
  estimatedCost: number;
  historyScope: string;
  totalCalls: number;
  totalTokens: number;
  tokenBreakdown: {
    cachedInput: number;
    uncachedInput: number;
    output: number;
    reasoningOutput: number;
  };
  usageRemainingCard: MetricCard;
}): MetricCard[] {
  return [
    {
      label: 'Total Tokens',
      value: compact(totalTokens),
      detail: `${historyScope} history scope`,
      trend: 'filtered aggregate rows',
      tone: 'blue',
      breakdown: [
        { label: 'Cached', value: compact(tokenBreakdown.cachedInput) },
        { label: 'Uncached', value: compact(tokenBreakdown.uncachedInput) },
        { label: 'Output', value: compact(tokenBreakdown.output) },
        { label: 'Reasoning', value: compact(tokenBreakdown.reasoningOutput) },
      ],
    },
    {
      label: 'Estimated Cost',
      value: money(estimatedCost),
      detail: 'local pricing config',
      trend: 'privacy-safe estimate',
      tone: 'green',
    },
    {
      label: 'Cache Hit Rate',
      value: `${cachePct.toFixed(1)}%`,
      detail: `${compact(cachedTokens)} cached input`,
      trend: cachePct >= 40 ? 'healthy cache reuse' : 'cache risk',
      tone: cachePct >= 40 ? 'purple' : 'orange',
    },
    {
      label: 'Total Calls',
      value: wholeNumber(totalCalls),
      detail: 'loaded calls matching filters',
      trend: 'legacy shell filters',
      tone: 'blue',
    },
    usageRemainingCard,
  ];
}

function overviewSeriesFromCalls(calls: CallRow[]): Pick<DashboardModel, 'tokenSeries' | 'costSeries' | 'cacheSeries'> {
  return buildOverviewSeriesFromDailyValues(
    calls.map(call => ({
      timestamp: Date.parse(call.rawTime || call.time),
      cached: call.cachedInput,
      cost: call.cost,
      input: call.input,
      output: call.output,
    })),
  );
}

function compact(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}

function wholeNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    currency: 'USD',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: 'currency',
  }).format(value);
}
