import { fixtureModel } from '../test-fixtures/dashboardFixture';
import type { CallRow, ContextRuntime, DashboardBootPayload, DashboardModel, MetricCard, ThreadRow, UsageRow } from './types';

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
    return {
      ...fixtureModel,
      contextRuntime: contextRuntimeFromBootPayload(payload),
    };
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
    contextRuntime: contextRuntimeFromBootPayload(payload),
    cards,
    calls,
    threads: buildThreads(calls),
    cacheSegments: [
      { label: 'Cache read', value: cachePct, color: '#2563eb' },
      { label: 'Uncached input', value: Math.max(100 - cachePct, 0), color: '#7c3aed' },
    ],
  };
}

function contextRuntimeFromBootPayload(payload: DashboardBootPayload | null): ContextRuntime {
  return {
    apiToken: String(payload?.api_token ?? ''),
    contextApiEnabled: Boolean(payload?.context_api_enabled),
    fileMode: window.location.protocol === 'file:',
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
      detail: `${input.historyScope} history scope`,
      trend: 'loaded aggregate rows',
      tone: 'blue',
    },
    {
      label: 'Estimated Cost',
      value: money(input.estimatedCost),
      detail: 'local pricing config',
      trend: 'privacy-safe estimate',
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

function rowToCall(row: UsageRow, index: number): CallRow {
  const rawTime = String(row.started_at ?? row.call_started_at ?? row.time ?? row.event_timestamp ?? row.turn_timestamp ?? '');
  const input = Number(row.input_tokens ?? 0);
  const output = Number(row.output_tokens ?? 0);
  const reasoningOutput = Number(row.reasoning_output_tokens ?? 0);
  const cached = Number(row.cached_input_tokens ?? 0);
  const cacheRatio = Number(row.cache_hit_ratio ?? row.cache_ratio ?? 0);
  const cachedPct = input > 0 ? (cached / input) * 100 : cacheRatio * 100;
  const totalTokens = Number(row.total_tokens ?? input + output);
  const durationSeconds = Number(row.duration_seconds ?? row.call_duration_seconds ?? 0);
  const uncachedInput = Number(row.uncached_input_tokens ?? Math.max(input - cached, 0));
  const id = String(row.record_id ?? row.id ?? `${rawTime || 'row'}-${index}`);
  const signal = String(row.primary_signal ?? '').trim();

  return {
    id,
    rawTime,
    time: formatShortDate(rawTime),
    thread: getThreadLabel(row),
    model: String(row.model ?? 'unknown'),
    effort: String(row.effort ?? 'blank'),
    input,
    output,
    reasoningOutput,
    totalTokens,
    uncachedInput,
    cachedPct,
    cost: Number(row.estimated_cost_usd ?? 0),
    credits: Number(row.usage_credits ?? 0),
    duration: formatDuration(durationSeconds),
    durationSeconds,
    fast: durationSeconds > 0 && totalTokens / Math.max(durationSeconds, 1) > 4_000,
    usageCreditConfidence: String(row.usage_credit_confidence ?? 'unknown'),
    pricingEstimated: Boolean(row.pricing_estimated),
    signal: signal || (cachedPct < 25 ? 'cache-risk' : 'aggregate'),
    recommendation: String(row.recommended_action ?? ''),
    tags: cachedPct < 25 ? ['uncached'] : cachedPct > 60 ? ['healthy-cache'] : [],
  };
}

function getThreadLabel(row: UsageRow): string {
  const direct = row.thread_name ?? row.thread ?? row.resolved_parent_thread_name ?? row.parent_thread_name;
  if (direct && String(direct).trim()) {
    return String(direct);
  }

  const project = row.project_name ?? row.project_relative_cwd;
  const sessionSuffix = row.session_id ? row.session_id.slice(-6) : '';
  if (project && sessionSuffix) {
    return `${project} ${sessionSuffix}`;
  }

  return row.thread_attachment_label ? String(row.thread_attachment_label) : 'Untitled thread';
}

function buildThreads(calls: CallRow[]): ThreadRow[] {
  const grouped = new Map<string, CallRow[]>();
  for (const call of calls) {
    grouped.set(call.thread, [...(grouped.get(call.thread) ?? []), call]);
  }

  return [...grouped.entries()]
    .map(([name, rows]) => {
      const turns = rows.length;
      const totalTokens = rows.reduce((sum, row) => sum + row.totalTokens, 0);
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
        productivity: Math.max(20, Math.round(cachePct - cost / Math.max(turns, 1) * 4)),
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
