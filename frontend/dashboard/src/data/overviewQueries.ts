import { queryOptions } from '@tanstack/react-query';

import type { ContextRuntime } from '../api/types';
import {
  persistentOverviewEndpointCache,
  type OverviewEndpointCache,
  type OverviewEndpointCacheIdentity,
} from './overviewEndpointCache';
import {
  decodeOverviewRecommendations,
  decodeOverviewSummary,
  type OverviewRecommendationsReport,
  type OverviewSummaryReport,
} from './contracts/overview';

type OverviewEndpointResource<T> = {
  data: T | null;
  error: string | null;
};

export type OverviewEndpointBundle = {
  summary: OverviewEndpointResource<OverviewSummaryReport>;
  recommendations: OverviewEndpointResource<OverviewRecommendationsReport>;
};

type OverviewEndpointRequest = {
  runtime: ContextRuntime;
  includeArchived: boolean;
  since?: string;
  sourceRevision?: string;
  cache?: OverviewEndpointCache;
  signal?: AbortSignal;
};

type OverviewQueryRequest = OverviewEndpointRequest & {
  sourceRevision: string;
};

const overviewQueryKeys = {
  recommendations: (includeArchived: boolean, since: string, sourceRevision: string) =>
    ['overview', 'recommendations', includeArchived ? 'all' : 'active', since, sourceRevision] as const,
  summary: (includeArchived: boolean, since: string, sourceRevision: string) =>
    ['overview', 'summary', includeArchived ? 'all' : 'active', since, sourceRevision] as const,
};

export function overviewSummaryQueryOptions(request: OverviewQueryRequest) {
  return queryOptions({
    queryKey: overviewQueryKeys.summary(
      request.includeArchived,
      request.since ?? '',
      request.sourceRevision,
    ),
    queryFn: ({ signal }) => loadOverviewSummaryEndpoint({ ...request, signal }),
    staleTime: 30_000,
  });
}

export function overviewRecommendationsQueryOptions(request: OverviewQueryRequest) {
  return queryOptions({
    queryKey: overviewQueryKeys.recommendations(
      request.includeArchived,
      request.since ?? '',
      request.sourceRevision,
    ),
    queryFn: ({ signal }) => loadOverviewRecommendationsEndpoint({ ...request, signal }),
    staleTime: 30_000,
  });
}

async function loadOverviewSummaryEndpoint({
  runtime,
  includeArchived,
  since,
  sourceRevision,
  cache = persistentOverviewEndpointCache,
  signal,
}: OverviewEndpointRequest): Promise<OverviewSummaryReport> {
  assertOverviewApiAvailable(runtime);
  const cacheIdentity = overviewCacheIdentity(includeArchived, since, sourceRevision);
  const cached = cacheIdentity ? cache.read(cacheIdentity) : null;
  if (cached?.summary.data && !cached.summary.error) return cached.summary.data;
  const data = await loadSummary(runtime, includeArchived, since, signal);
  if (cacheIdentity) {
    cache.write(cacheIdentity, {
      ...(cache.read(cacheIdentity) ?? emptyOverviewBundle()),
      summary: { data, error: null },
    });
  }
  return data;
}

async function loadOverviewRecommendationsEndpoint({
  runtime,
  includeArchived,
  since,
  sourceRevision,
  cache = persistentOverviewEndpointCache,
  signal,
}: OverviewEndpointRequest): Promise<OverviewRecommendationsReport> {
  assertOverviewApiAvailable(runtime);
  const cacheIdentity = overviewCacheIdentity(includeArchived, since, sourceRevision);
  const cached = cacheIdentity ? cache.read(cacheIdentity) : null;
  if (cached?.recommendations.data && !cached.recommendations.error) {
    return cached.recommendations.data;
  }
  const data = await loadRecommendations(runtime, includeArchived, since, signal);
  if (cacheIdentity) {
    cache.write(cacheIdentity, {
      ...(cache.read(cacheIdentity) ?? emptyOverviewBundle()),
      recommendations: { data, error: null },
    });
  }
  return data;
}

export async function loadOverviewEndpoints({
  runtime,
  includeArchived,
  since,
  sourceRevision,
  cache = persistentOverviewEndpointCache,
  signal,
}: OverviewEndpointRequest): Promise<OverviewEndpointBundle> {
  assertOverviewApiAvailable(runtime);
  const cacheIdentity = overviewCacheIdentity(includeArchived, since, sourceRevision);
  const cachedBundle = cacheIdentity ? cache.read(cacheIdentity) : null;
  if (cachedBundle) return cachedBundle;
  const [summary, recommendations] = await Promise.allSettled([
    loadSummary(runtime, includeArchived, since, signal),
    loadRecommendations(runtime, includeArchived, since, signal),
  ]);
  if (summary.status === 'rejected' && recommendations.status === 'rejected') {
    throw new AggregateError(
      [summary.reason, recommendations.reason],
      'Overview summary and recommendations are unavailable.',
    );
  }
  const bundle = {
    summary: settledResource(summary),
    recommendations: settledResource(recommendations),
  };
  if (cacheIdentity && !bundle.summary.error && !bundle.recommendations.error) {
    cache.write(cacheIdentity, bundle);
  }
  return bundle;
}

function overviewCacheIdentity(
  includeArchived: boolean,
  since: string | undefined,
  sourceRevision: string | undefined,
): OverviewEndpointCacheIdentity | null {
  if (!sourceRevision) return null;
  return { includeArchived, since: since ?? '', sourceRevision };
}

async function loadSummary(
  runtime: ContextRuntime,
  includeArchived: boolean,
  since?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    group_by: 'date',
    limit: '0',
    include_archived: String(includeArchived),
  });
  if (since) params.set('since', since);
  return decodeOverviewSummary(await requestJson(`/api/summary?${params}`, runtime, signal));
}

async function loadRecommendations(
  runtime: ContextRuntime,
  includeArchived: boolean,
  since?: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    include_archived: String(includeArchived),
    limit: '25',
  });
  if (since) params.set('since', since);
  return decodeOverviewRecommendations(
    await requestJson(`/api/recommendations?${params}`, runtime, signal),
  );
}

async function requestJson(path: string, runtime: ContextRuntime, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    signal,
  });
  if (!response.ok) throw new Error(`Overview endpoint failed with HTTP ${response.status}.`);
  return response.json();
}

function settledResource<T>(result: PromiseSettledResult<T>): OverviewEndpointResource<T> {
  if (result.status === 'fulfilled') return { data: result.value, error: null };
  return {
    data: null,
    error: result.reason instanceof Error ? result.reason.message : 'Endpoint unavailable.',
  };
}

function assertOverviewApiAvailable(runtime: ContextRuntime): void {
  if (runtime.fileMode || !runtime.apiToken) {
    throw new Error('Focused Overview endpoints require the localhost dashboard server.');
  }
}

function emptyOverviewBundle(): OverviewEndpointBundle {
  return {
    summary: { data: null, error: null },
    recommendations: { data: null, error: null },
  };
}
