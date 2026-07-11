import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';

import type { ContextRuntime } from '../api/types';
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
  | 'gap';

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
};

const callsPageSize = 500;
const threadsPageSize = 250;

const exploreQueryKeys = {
  calls: (request: CallsQueryRequest) => [
    'explore',
    'calls',
    request.includeArchived ? 'all' : 'active',
    request.filters,
    request.sort,
    request.direction,
    request.pageSize ?? callsPageSize,
    request.sourceRevision,
  ] as const,
  threads: (request: ThreadsQueryRequest) => [
    'explore',
    'threads',
    request.includeArchived ? 'all' : 'active',
    request.query ?? '',
    request.sort,
    request.direction,
    request.pageSize ?? threadsPageSize,
    request.sourceRevision,
  ] as const,
  threadCalls: (request: ThreadCallsQueryRequest) => [
    'explore',
    'thread-calls',
    request.includeArchived ? 'all' : 'active',
    request.threadKey,
    request.sort ?? 'time',
    request.direction ?? 'desc',
    request.sourceRevision,
  ] as const,
};

export function callsInfiniteQueryOptions(request: CallsQueryRequest) {
  const pageSize = request.pageSize ?? callsPageSize;
  return infiniteQueryOptions({
    queryKey: exploreQueryKeys.calls(request),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadCallsPage(request, pageParam, pageSize, signal),
    getNextPageParam: (lastPage: ExploreCallsPage) => lastPage.nextOffset ?? undefined,
    staleTime: 30_000,
  });
}

export function threadsInfiniteQueryOptions(request: ThreadsQueryRequest) {
  const pageSize = request.pageSize ?? threadsPageSize;
  return infiniteQueryOptions({
    queryKey: exploreQueryKeys.threads(request),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadThreadsPage(request, pageParam, pageSize, signal),
    getNextPageParam: (lastPage: ExploreThreadsPage) => lastPage.nextOffset ?? undefined,
    staleTime: 30_000,
  });
}

export function threadCallsQueryOptions(request: ThreadCallsQueryRequest) {
  return queryOptions({
    queryKey: exploreQueryKeys.threadCalls(request),
    queryFn: ({ signal }) => loadThreadCalls(request, signal),
    staleTime: 30_000,
  });
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
  signal?: AbortSignal,
): Promise<ExploreCallsPage> {
  assertExploreApiAvailable(request.runtime);
  const params = commonParams(
    request.includeArchived,
    0,
    0,
    request.sort ?? 'time',
    request.direction ?? 'desc',
  );
  params.set('thread_key', request.threadKey);
  return decodeExploreCalls(await requestJson(`/api/thread-calls?${params}`, request.runtime, signal));
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
