import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';

import type { ContextRuntime } from '../api/types';
import {
  dashboardQueryDefinition,
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQuerySource,
} from './dashboardQueryRegistry';
import {
  decodeExploreCalls,
  decodeExploreThreads,
  type ExploreCallsPage,
  type ExploreThreadsPage,
} from './contracts/explore';

type ExploreSortDirection = 'asc' | 'desc';

export type CallsApiSort =
  | 'time'
  | 'tokens'
  | 'input'
  | 'cached'
  | 'uncached'
  | 'output'
  | 'reasoning'
  | 'cache'
  | 'model'
  | 'effort'
  | 'thread'
  | 'initiator'
  | 'duration'
  | 'gap'
  | 'cost';

export type ThreadsApiSort = 'tokens' | 'time' | 'calls' | 'cache' | 'thread';

export type CallsQueryFilters = {
  query?: string;
  model?: string;
  effort?: string;
  since?: string;
  until?: string;
  pricingStatus?: string;
  creditConfidence?: string;
};

type ExploreBaseRequest = {
  runtime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
  pageSize?: number;
};

export type CallsQueryRequest = ExploreBaseRequest & {
  filters: CallsQueryFilters;
  sort: CallsApiSort;
  direction: ExploreSortDirection;
};

export type ThreadsQueryRequest = ExploreBaseRequest & {
  query?: string;
  sort: ThreadsApiSort;
  direction: ExploreSortDirection;
};

export type ThreadCallsQueryRequest = ExploreBaseRequest & {
  threadKey: string;
  sort?: CallsApiSort;
  direction?: ExploreSortDirection;
  since?: string;
  until?: string;
};

export type ThreadCallContextQueryRequest = ThreadCallsQueryRequest & {
  selectedRecordId: string;
  selectedEventTimestamp: string;
};

const callsPageSize = 500;
const threadsPageSize = 250;
const threadCallsPageSize = 100;
const callsQuery = dashboardQueryDefinition('calls');
const threadsQuery = dashboardQueryDefinition('threads');
const threadCallsQuery = dashboardQueryDefinition('thread-calls');

const exploreQueryKeys = {
  calls: (request: CallsQueryRequest) => dashboardQueryKey(
    callsQuery,
    exploreQuerySource(request),
    exploreQueryScope(request, request.filters.since),
    request.filters,
    request.sort,
    request.direction,
    request.pageSize ?? callsPageSize,
  ),
  threads: (request: ThreadsQueryRequest) => dashboardQueryKey(
    threadsQuery,
    exploreQuerySource(request),
    exploreQueryScope(request),
    request.query ?? '',
    request.sort,
    request.direction,
    request.pageSize ?? threadsPageSize,
  ),
  threadCalls: (request: ThreadCallsQueryRequest) => dashboardQueryKey(
    threadCallsQuery,
    exploreQuerySource(request),
    exploreQueryScope(request),
    request.threadKey,
    request.sort ?? 'time',
    request.direction ?? 'desc',
    request.since ?? null,
    request.until ?? null,
    request.pageSize ?? threadCallsPageSize,
  ),
  threadCallContext: (request: ThreadCallContextQueryRequest) => dashboardQueryKey(
    threadCallsQuery,
    exploreQuerySource(request),
    exploreQueryScope(request),
    'context',
    request.threadKey,
    request.selectedRecordId,
    request.selectedEventTimestamp,
    request.pageSize ?? threadCallsPageSize,
  ),
};

export function callsInfiniteQueryOptions(request: CallsQueryRequest) {
  const pageSize = request.pageSize ?? callsPageSize;
  return infiniteQueryOptions({
    queryKey: exploreQueryKeys.calls(request),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadCallsPage(request, pageParam, pageSize, signal),
    getNextPageParam: (lastPage: ExploreCallsPage) => lastPage.nextOffset ?? undefined,
    ...dashboardQueryOptions(callsQuery.dataClass),
  });
}

export function threadsInfiniteQueryOptions(request: ThreadsQueryRequest) {
  const pageSize = request.pageSize ?? threadsPageSize;
  return infiniteQueryOptions({
    queryKey: exploreQueryKeys.threads(request),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadThreadsPage(request, pageParam, pageSize, signal),
    getNextPageParam: (lastPage: ExploreThreadsPage) => lastPage.nextOffset ?? undefined,
    ...dashboardQueryOptions(threadsQuery.dataClass),
  });
}

export function threadCallsInfiniteQueryOptions(request: ThreadCallsQueryRequest) {
  const pageSize = request.pageSize ?? threadCallsPageSize;
  return infiniteQueryOptions({
    queryKey: exploreQueryKeys.threadCalls(request),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadThreadCalls(request, pageParam, pageSize, signal),
    getNextPageParam: (lastPage: ExploreCallsPage) => lastPage.nextOffset ?? undefined,
    ...dashboardQueryOptions(threadCallsQuery.dataClass),
  });
}

export function threadCallsQueryOptions(request: ThreadCallsQueryRequest) {
  return queryOptions({
    queryKey: exploreQueryKeys.threadCalls(request),
    queryFn: ({ signal }) => loadThreadCalls(request, 0, request.pageSize, signal),
    ...dashboardQueryOptions(threadCallsQuery.dataClass),
  });
}

export function threadCallContextQueryOptions(request: ThreadCallContextQueryRequest) {
  return queryOptions({
    queryKey: exploreQueryKeys.threadCallContext(request),
    queryFn: ({ signal }) => loadThreadCallContext(request, signal),
    ...dashboardQueryOptions(threadCallsQuery.dataClass),
  });
}

function exploreQuerySource(request: ExploreBaseRequest) {
  return dashboardQuerySource({
    sourceKey: request.sourceKey ?? (request.runtime.fileMode ? 'static-file' : 'local-api'),
    sourceRevision: request.sourceRevision,
  });
}

function exploreQueryScope(request: ExploreBaseRequest, since?: string) {
  return {
    historyScope: request.includeArchived ? 'all' as const : 'active' as const,
    since: since ?? null,
  };
}

export async function loadCallsPage(
  request: CallsQueryRequest,
  offset = 0,
  limit = request.pageSize ?? callsPageSize,
  signal?: AbortSignal,
): Promise<ExploreCallsPage> {
  assertExploreApiAvailable(request.runtime);
  const params = commonParams(request.includeArchived, limit, offset, request.sort, request.direction);
  append(params, 'q', request.filters.query);
  append(params, 'model', request.filters.model);
  append(params, 'effort', request.filters.effort);
  append(params, 'since', request.filters.since);
  append(params, 'until', request.filters.until);
  append(params, 'pricing_status', request.filters.pricingStatus);
  append(params, 'credit_confidence', request.filters.creditConfidence);
  return decodeExploreCalls(await requestJson(`/api/calls?${params}`, request.runtime, signal));
}

export async function loadThreadsPage(
  request: ThreadsQueryRequest,
  offset = 0,
  limit = request.pageSize ?? threadsPageSize,
  signal?: AbortSignal,
): Promise<ExploreThreadsPage> {
  assertExploreApiAvailable(request.runtime);
  const params = commonParams(request.includeArchived, limit, offset, request.sort, request.direction);
  append(params, 'q', request.query);
  return decodeExploreThreads(await requestJson(`/api/threads?${params}`, request.runtime, signal));
}

export async function loadThreadCalls(
  request: ThreadCallsQueryRequest,
  offset = 0,
  limit = request.pageSize ?? threadCallsPageSize,
  signal?: AbortSignal,
): Promise<ExploreCallsPage> {
  assertExploreApiAvailable(request.runtime);
  const params = commonParams(
    request.includeArchived,
    limit,
    offset,
    request.sort ?? 'time',
    request.direction ?? 'desc',
  );
  params.set('thread_key', request.threadKey);
  append(params, 'since', request.since);
  append(params, 'until', request.until);
  return decodeExploreCalls(await requestJson(`/api/thread-calls?${params}`, request.runtime, signal));
}

export async function loadThreadCallContext(
  request: ThreadCallContextQueryRequest,
  signal?: AbortSignal,
): Promise<ExploreCallsPage> {
  const pageSize = request.pageSize ?? threadCallsPageSize;
  if (!request.selectedEventTimestamp) {
    return loadThreadCalls(request, 0, pageSize, signal);
  }
  const sideLimit = Math.floor(pageSize / 2) + 1;
  const [newer, older] = await Promise.all([
    loadThreadCalls(
      { ...request, since: request.selectedEventTimestamp, until: undefined, sort: 'time', direction: 'asc' },
      0,
      sideLimit,
      signal,
    ),
    loadThreadCalls(
      { ...request, since: undefined, until: request.selectedEventTimestamp, sort: 'time', direction: 'desc' },
      0,
      sideLimit,
      signal,
    ),
  ]);
  const rowsById = new Map([...newer.rows, ...older.rows].map(row => [row.id, row]));
  const rows = [...rowsById.values()]
    .sort((left, right) => callTimestamp(right.eventTimestamp) - callTimestamp(left.eventTimestamp) || left.id.localeCompare(right.id))
    .slice(0, pageSize);
  return {
    schema: older.schema,
    threadKey: request.threadKey,
    rows,
    rowCount: rows.length,
    totalMatchedRows: Math.max(rows.length, newer.totalMatchedRows + older.totalMatchedRows - 1),
    limit: pageSize,
    offset: 0,
    hasMore: false,
    nextOffset: null,
    rawContextIncluded: false,
  };
}

function callTimestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function commonParams(
  includeArchived: boolean,
  limit: number,
  offset: number,
  sort: string,
  direction: ExploreSortDirection,
): URLSearchParams {
  return new URLSearchParams({
    include_archived: String(includeArchived),
    limit: String(limit),
    offset: String(offset),
    sort,
    direction,
  });
}

function append(params: URLSearchParams, key: string, value?: string): void {
  if (value && value !== 'all') params.set(key, value);
}

async function requestJson(path: string, runtime: ContextRuntime, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    signal,
  });
  if (!response.ok) throw new Error(`Explore endpoint failed with HTTP ${response.status}.`);
  return response.json();
}

function assertExploreApiAvailable(runtime: ContextRuntime): void {
  if (runtime.fileMode || !runtime.apiToken) {
    throw new Error('Focused Explore endpoints require the localhost dashboard server.');
  }
}
