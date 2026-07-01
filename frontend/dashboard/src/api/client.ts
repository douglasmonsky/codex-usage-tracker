import { fixtureModel } from '../test-fixtures/dashboardFixture';
import type { CallRow, DashboardBootPayload, DashboardModel, MetricCard, ThreadRow, UsageRow } from './types';

declare global {
  interface Window {
    __CODEX_USAGE_BOOT__?: DashboardBootPayload;
  }
}

export function readBootPayload(): DashboardBootPayload | null {
  if (window.__CODEX_USAGE_BOOT__) {
    return window.__CODEX_USAGE_BOOT__;
  }
  const embedded = document.getElementById('usage-data');
  if (!embedded?.textContent) {
    return null;
  }
  try {
    return JSON.parse(embedded.textContent) as DashboardBootPayload;
  } catch {
    return null;
  }
}

export function modelFromBootPayload(payload: DashboardBootPayload | null): DashboardModel {
  if (!payload?.rows?.length) {
    return fixtureModel;
  }

  const calls = payload.rows.slice(0, 100).map(rowToCall);
  const totalTokens = sumRows(payload.rows, row => Number(row.total_tokens ?? 0));
  const estimatedCost = sumRows(payload.rows, row => Number(row.estimated_cost_usd ?? 0));
  const cachedTokens = sumRows(payload.rows, row => Number(row.cached_input_tokens ?? 0));
  const inputTokens = sumRows(payload.rows, row => Number(row.input_tokens ?? 0));
  const cachePct = inputTokens > 0 ? (cachedTokens / inputTokens) * 100 : 0;
  const totalCalls = payload.loaded_row_count ?? calls.length;
  const cards = buildCards({
    cachePct,
    cachedTokens,
    estimatedCost,
    historyScope: payload.history_scope ?? 'active',
    totalCalls,
    totalTokens,
  });

  return {
    ...fixtureModel,
    cards,
    calls,
    threads: buildThreads(calls),
    cacheSegments: [
      { label: 'Cache read', value: cachePct, color: '#2563eb' },
      { label: 'Uncached input', value: Math.max(100 - cachePct, 0), color: '#f59e0b' },
      { label: 'Output', value: 22, color: '#0f766e' },
    ],
  };
}

function buildCards(input: {
  cachePct: number;
  cachedTokens: number;
  estimatedCost: number;
  historyScope: string;
  totalCalls: number;
  totalTokens: number;
}): MetricCard[] {
  return [
    {
      label: 'Total Tokens',
      value: formatCompact(input.totalTokens),
      detail: `${formatNumber(input.totalCalls)} loaded calls`,
      trend: 'active snapshot',
      tone: 'blue',
    },
    {
      label: 'Estimated Cost',
      value: money(input.estimatedCost),
      detail: `${input.historyScope} scope`,
      trend: 'local estimate',
      tone: 'green',
    },
    {
      label: 'Cache Hit Rate',
      value: `${input.cachePct.toFixed(1)}%`,
      detail: `${formatCompact(input.cachedTokens)} cached input`,
      trend: input.cachePct >= 40 ? 'healthy cache reuse' : 'cache risk',
      tone: input.cachePct >= 40 ? 'purple' : 'orange',
    },
    {
      label: 'Total Calls',
      value: formatNumber(input.totalCalls),
      detail: 'visible aggregate rows',
      trend: 'privacy-safe',
      tone: 'blue',
    },
    {
      label: 'Usage Remaining',
      value: fixtureModel.cards[4]?.value ?? 'unknown',
      detail: 'from local allowance config',
      trend: 'not recomputed',
      tone: 'green',
    },
  ];
}

function rowToCall(row: UsageRow): CallRow {
  const input = Number(row.input_tokens ?? 0);
  const cached = Number(row.cached_input_tokens ?? 0);
  const cachedPct = input > 0 ? (cached / input) * 100 : Number(row.cache_hit_ratio ?? 0) * 100;
  const totalTokens = Number(row.total_tokens ?? input + Number(row.output_tokens ?? 0));
  return {
    time: formatShortDate(String(row.started_at ?? row.time ?? '')),
    thread: String(row.thread_name ?? row.thread ?? 'Untitled thread'),
    model: String(row.model ?? 'unknown'),
    effort: String(row.effort ?? 'blank'),
    input,
    output: Number(row.output_tokens ?? 0),
    cachedPct,
    cost: Number(row.estimated_cost_usd ?? 0),
    duration: formatDuration(Number(row.duration_seconds ?? 0)),
    fast: Number(row.duration_seconds ?? 0) > 0 && totalTokens / Math.max(Number(row.duration_seconds ?? 1), 1) > 4_000,
    tags: cachedPct < 25 ? ['uncached'] : cachedPct > 60 ? ['healthy-cache'] : [],
  };
}

function buildThreads(calls: CallRow[]): ThreadRow[] {
  const grouped = new Map<string, CallRow[]>();
  for (const call of calls) {
    grouped.set(call.thread, [...(grouped.get(call.thread) ?? []), call]);
  }

  return [...grouped.entries()]
    .map(([name, rows]) => {
      const turns = rows.length;
      const totalTokens = rows.reduce((sum, row) => sum + row.input + row.output, 0);
      const cost = rows.reduce((sum, row) => sum + row.cost, 0);
      const cachePct = rows.reduce((sum, row) => sum + row.cachedPct, 0) / Math.max(turns, 1);
      const coldResumeRisk = cachePct < 25 ? 'High' : cachePct < 45 ? 'Medium' : 'Low';
      return {
        name,
        turns,
        totalTokens,
        cost,
        cachePct,
        costPerCall: cost / Math.max(turns, 1),
        coldResumeRisk,
        productivity: Math.max(20, Math.min(92, Math.round(cachePct + 30 - turns / 4))),
      } satisfies ThreadRow;
    })
    .sort((left, right) => right.cost - left.cost)
    .slice(0, 20);
}

function sumRows(rows: UsageRow[], selector: (row: UsageRow) => number): number {
  return rows.reduce((total, row) => total + selector(row), 0);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds.toFixed(0)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function formatShortDate(raw: string): string {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return raw || '-';
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}
