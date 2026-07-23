import type { DashboardBootPayload } from './types';
import type { HistoryScope, LoadWindow } from '../data/dataScope';
import { assertLiveUsagePayloadAvailable, liveUsageHeaders } from '../data/httpTransportSupport';
import type { OverviewLoadedMetrics } from '../features/overview/overviewModel';

const measures = [
  'tokens',
  'uncached_tokens',
  'cached_tokens',
  'output_tokens',
  'reasoning_tokens',
  'estimated_cost',
  'estimated_credits',
] as const;

type QueryRow = Record<string, unknown>;

type QueryPayload = {
  schema: 'codex-usage-tracker.query.v2';
  rows: QueryRow[];
  next_cursor: string | null;
};

export type HomeUsageScope = {
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  loadLimit: number;
  since: string | null;
};

export async function loadHomeUsageMetrics(
  currentPayload: DashboardBootPayload | null,
  scope: HomeUsageScope,
  signal?: AbortSignal,
): Promise<OverviewLoadedMetrics> {
  assertLiveUsagePayloadAvailable(currentPayload);
  return scope.loadWindow === 'rows'
    ? loadRecentCallMetrics(currentPayload, scope, signal)
    : loadModelMetrics(currentPayload, scope, signal);
}

async function loadModelMetrics(
  currentPayload: DashboardBootPayload,
  scope: HomeUsageScope,
  signal?: AbortSignal,
): Promise<OverviewLoadedMetrics> {
  const rows: QueryRow[] = [];
  let cursor: string | null = null;
  do {
    const page = await queryV2(
      currentPayload,
      {
        entity: 'model',
        measures: [...measures, 'call_count'],
        filters: scope.since ? { since: scope.since } : {},
        history: scope.historyScope,
        order_by: 'tokens',
        order: 'desc',
        limit: 200,
        ...(cursor ? { cursor } : {}),
      },
      signal,
    );
    rows.push(...page.rows);
    cursor = page.next_cursor;
    if (page.rows.length === 0) break;
  } while (cursor);
  return aggregateRows(rows, true);
}

async function loadRecentCallMetrics(
  currentPayload: DashboardBootPayload,
  scope: HomeUsageScope,
  signal?: AbortSignal,
): Promise<OverviewLoadedMetrics> {
  const rows: QueryRow[] = [];
  const target = Math.max(1, scope.loadLimit);
  let cursor: string | null = null;
  while (rows.length < target) {
    const page = await queryV2(
      currentPayload,
      {
        entity: 'call',
        measures,
        filters: {},
        history: scope.historyScope,
        order_by: 'time',
        order: 'desc',
        limit: Math.min(200, target - rows.length),
        ...(cursor ? { cursor } : {}),
      },
      signal,
    );
    rows.push(...page.rows);
    cursor = page.next_cursor;
    if (!cursor || page.rows.length === 0) break;
  }
  return aggregateRows(rows, false);
}

async function queryV2(
  currentPayload: DashboardBootPayload,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<QueryPayload> {
  const headers = new Headers(liveUsageHeaders(currentPayload));
  headers.set('Content-Type', 'application/json');
  const response = await fetch('/api/v2/query', {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
    cache: 'no-store',
    signal,
  });
  if (!response.ok) {
    throw new Error(`Overview usage query failed with HTTP ${response.status}.`);
  }
  const payload = await response.json() as Partial<QueryPayload>;
  if (payload.schema !== 'codex-usage-tracker.query.v2' || !Array.isArray(payload.rows)) {
    throw new Error('Overview usage query returned an unsupported response.');
  }
  return {
    schema: payload.schema,
    rows: payload.rows,
    next_cursor: typeof payload.next_cursor === 'string' ? payload.next_cursor : null,
  };
}

function aggregateRows(rows: QueryRow[], grouped: boolean): OverviewLoadedMetrics {
  const totalTokens = sum(rows, 'tokens');
  const cachedInputTokens = sum(rows, 'cached_tokens');
  const uncachedInputTokens = sum(rows, 'uncached_tokens');
  const inputTokens = cachedInputTokens + uncachedInputTokens;
  return {
    basis: 'scope',
    hasInputTokens: inputTokens > 0,
    hasPricingCoverage: rows.some(row => number(row.estimated_cost_coverage) > 0),
    calls: grouped ? sum(rows, 'call_count') : rows.length,
    totalTokens,
    cachedInputTokens,
    uncachedInputTokens,
    outputTokens: sum(rows, 'output_tokens'),
    reasoningOutputTokens: sum(rows, 'reasoning_tokens'),
    cachePercent: inputTokens > 0 ? (cachedInputTokens / inputTokens) * 100 : 0,
    estimatedCostUsd: sum(rows, 'estimated_cost'),
    estimatedCredits: sum(rows, 'estimated_credits'),
  };
}

function sum(rows: QueryRow[], key: string): number {
  return rows.reduce((total, row) => total + number(row[key]), 0);
}

function number(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
