import { queryOptions } from '@tanstack/react-query';

import type { ContextRuntime } from '../api/types';
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
  signal?: AbortSignal;
};

type OverviewQueryRequest = OverviewEndpointRequest & {
  sourceRevision: string;
};

const overviewQueryKeys = {
  bundle: (includeArchived: boolean, since: string, sourceRevision: string) =>
    ['overview', includeArchived ? 'all' : 'active', since, sourceRevision] as const,
};

export function overviewQueryOptions(request: OverviewQueryRequest) {
  return queryOptions({
    queryKey: overviewQueryKeys.bundle(
      request.includeArchived,
      request.since ?? '',
      request.sourceRevision,
    ),
    queryFn: ({ signal }) => loadOverviewEndpoints({ ...request, signal }),
    staleTime: 30_000,
  });
}

export async function loadOverviewEndpoints({
  runtime,
  includeArchived,
  since,
  signal,
}: OverviewEndpointRequest): Promise<OverviewEndpointBundle> {
  assertOverviewApiAvailable(runtime);
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
  return {
    summary: settledResource(summary),
    recommendations: settledResource(recommendations),
  };
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
