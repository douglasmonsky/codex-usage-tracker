import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { buildOverviewSeriesFromDailyValues } from '../../api/overviewSeries';
import type { CallRow, ContextRuntime, DashboardModel, HeatmapRow, MetricCard, Series, ThreadRow } from '../../api/types';
import { threadCallsQueryOptions, threadsInfiniteQueryOptions } from '../../data/exploreQueries';
import { overviewSummaryQueryOptions } from '../../data/overviewQueries';
import { formatCompact, formatNumber, pct } from '../shared/format';
import { threadSummaryToRow, type ExploreThreadRow } from '../threads/threadSummaryAdapter';

type CacheContextEvidenceRequest = {
  model: DashboardModel;
  runtime: ContextRuntime;
  includeArchived: boolean;
  scopeSince?: string | null;
  selectedThreadName: string | null;
  sourceRevision: string;
  enabled: boolean;
};

export type CacheContextEvidence = {
  cacheSeries: Series[];
  cards: MetricCard[];
  heatmap: HeatmapRow[];
  selectedCalls: CallRow[];
  selectedThread: ThreadRow | null;
  threads: ThreadRow[];
  totalThreads: number;
  usingFocusedEndpoints: boolean;
  progress: {
    active: boolean;
    completed: number;
    total: number;
    error: string | null;
    updating: boolean;
  };
};

export function useCacheContextEvidence(request: CacheContextEvidenceRequest): CacheContextEvidence {
  const focused = request.enabled && !request.runtime.fileMode && Boolean(request.runtime.apiToken);
  const summaryQuery = useQuery({
    ...overviewSummaryQueryOptions({
      runtime: request.runtime,
      includeArchived: request.includeArchived,
      since: request.scopeSince ?? undefined,
      sourceRevision: request.sourceRevision,
    }),
    enabled: focused,
    placeholderData: previous => previous,
  });
  const threadsQuery = useInfiniteQuery({
    ...threadsInfiniteQueryOptions({
      runtime: request.runtime,
      includeArchived: request.includeArchived,
      sourceRevision: request.sourceRevision,
      sort: 'tokens',
      direction: 'desc',
      pageSize: 250,
    }),
    enabled: focused,
    placeholderData: previous => previous,
  });
  const loadedThreadsByName = useMemo(
    () => new Map(request.model.threads.map(thread => [thread.name, thread])),
    [request.model.threads],
  );
  const focusedThreads = useMemo(
    () => threadsQuery.data?.pages.flatMap(page => page.rows.map(summary =>
      threadSummaryToRow(summary, loadedThreadsByName.get(summary.threadLabel) ?? loadedThreadsByName.get(summary.threadKey)),
    )) ?? [],
    [loadedThreadsByName, threadsQuery.data],
  );
  const usingFocusedEndpoints = focused && Boolean(threadsQuery.data);
  const threads = usingFocusedEndpoints ? focusedThreads : request.model.threads;
  const selectedThread = threads.find(thread => thread.name === request.selectedThreadName) ?? threads[0] ?? null;
  const localSelectedCalls = useMemo(
    () => cacheThreadCalls(request.model.calls, selectedThread),
    [request.model.calls, selectedThread],
  );
  const selectedThreadKey = (selectedThread as ExploreThreadRow | null)?.threadKey
    || localSelectedCalls[0]?.threadKey
    || selectedThread?.name
    || '';
  const selectedCallsQuery = useQuery({
    ...threadCallsQueryOptions({
      runtime: request.runtime,
      includeArchived: request.includeArchived,
      sourceRevision: request.sourceRevision,
      threadKey: selectedThreadKey,
    }),
    enabled: focused && Boolean(selectedThreadKey),
    placeholderData: previous => previous,
  });
  const summary = summaryQuery.data;
  const selectedCallsRequired = Boolean(selectedThreadKey);
  const completedModules = Number(Boolean(summary))
    + Number(Boolean(threadsQuery.data))
    + Number(!selectedCallsRequired || Boolean(selectedCallsQuery.data));
  const totalModules = selectedCallsRequired ? 3 : 2;
  const queryError = summaryQuery.error ?? threadsQuery.error ?? selectedCallsQuery.error;
  return {
    cacheSeries: summary ? cacheSeriesFromSummary(summary.rows) : request.model.cacheSeries,
    cards: summary ? cacheCardsFromSummary(summary.rows) : request.model.cards.slice(2, 5),
    heatmap: usingFocusedEndpoints
      ? threads.map(thread => ({ thread: thread.name, values: [thread.cachePct], labels: ['All time'] }))
      : request.model.cacheHeatmap,
    selectedCalls: selectedCallsQuery.data?.rows ?? localSelectedCalls,
    selectedThread,
    threads,
    totalThreads: threadsQuery.data?.pages[0]?.totalMatchedRows ?? threads.length,
    usingFocusedEndpoints,
    progress: {
      active: focused && (summaryQuery.isFetching || threadsQuery.isFetching || selectedCallsQuery.isFetching),
      completed: Math.min(completedModules, totalModules),
      total: totalModules,
      error: queryError ? queryErrorMessage(queryError) : null,
      updating: completedModules > 0,
    },
  };
}

function queryErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function cacheSeriesFromSummary(rows: Array<{
  groupKey: string;
  latestEvent: string;
  inputTokens: number;
  cachedInputTokens: number;
  outputTokens: number;
}>): Series[] {
  return buildOverviewSeriesFromDailyValues(rows.map(row => ({
    timestamp: Date.parse(row.groupKey) || Date.parse(row.latestEvent),
    input: row.inputTokens,
    cached: row.cachedInputTokens,
    output: row.outputTokens,
    cost: 0,
  }))).cacheSeries;
}

function cacheCardsFromSummary(rows: Array<{
  modelCalls: number;
  inputTokens: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  totalTokens: number;
}>): MetricCard[] {
  const totals = rows.reduce((result, row) => ({
    calls: result.calls + row.modelCalls,
    input: result.input + row.inputTokens,
    cached: result.cached + row.cachedInputTokens,
    uncached: result.uncached + row.uncachedInputTokens,
    tokens: result.tokens + row.totalTokens,
  }), { calls: 0, input: 0, cached: 0, uncached: 0, tokens: 0 });
  const cachePct = totals.input > 0 ? (totals.cached / totals.input) * 100 : 0;
  return [
    { label: 'Total Calls', value: formatNumber(totals.calls), trend: 'complete selected scope', detail: 'server-side aggregate', tone: 'blue' },
    { label: 'Cache Reuse', value: pct(cachePct), trend: cachePct >= 80 ? 'healthy cache reuse' : 'review cache reuse', detail: `${formatCompact(totals.cached)} cached input`, tone: cachePct >= 80 ? 'green' : 'orange' },
    { label: 'Uncached Input', value: formatCompact(totals.uncached), trend: `${formatCompact(totals.tokens)} total tokens`, detail: 'complete selected scope', tone: 'purple' },
  ];
}

function cacheThreadCalls(calls: CallRow[], thread: ThreadRow | null): CallRow[] {
  if (!thread) return [];
  return calls
    .filter(call => threadLabelsMatch(call.thread, thread.name))
    .sort((left, right) => Date.parse(right.rawTime || right.time) - Date.parse(left.rawTime || left.time));
}

function threadLabelsMatch(callThread: string, threadName: string): boolean {
  const callLabel = callThread.trim();
  const summaryLabel = threadName.trim();
  return callLabel === summaryLabel || callLabel.startsWith(summaryLabel) || summaryLabel.startsWith(callLabel);
}
