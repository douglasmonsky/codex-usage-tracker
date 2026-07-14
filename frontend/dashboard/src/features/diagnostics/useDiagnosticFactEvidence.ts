import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import {
  diagnosticFactSourceDefinitions,
  type DiagnosticFactCallsResult,
  type DiagnosticFactRow,
  type DiagnosticFactSourceKey,
} from '../../api/diagnostics';
import type { ContextRuntime } from '../../api/types';
import {
  dashboardModuleProgress,
  deriveDashboardModuleState,
} from '../../data/dashboardQueryRegistry';
import {
  diagnosticFactCallsQueryOptions,
  diagnosticFactSourceQueryOptions,
} from '../../data/diagnosticsQueries';
import { mergeFactCallResults } from './diagnosticFactCalls';
import type { FactCallSortState, FactSortState } from './diagnosticFactSorting';
import type { FactCallsState, FactLoadState } from './diagnosticFactStates';

type DiagnosticFactSourceStateMap = Partial<Record<DiagnosticFactSourceKey, FactLoadState>>;
export type DiagnosticFactSortStateMap = Partial<Record<DiagnosticFactSourceKey, FactSortState>>;
export type DiagnosticFactLimitMap = Partial<Record<DiagnosticFactSourceKey, number>>;

type DiagnosticFactEvidenceRequest = {
  canUseLive: boolean;
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
};

type DiagnosticFactSourcesRequest = DiagnosticFactEvidenceRequest & {
  activeSourceKey: DiagnosticFactSourceKey;
  limits: DiagnosticFactLimitMap;
  sorts: DiagnosticFactSortStateMap;
};

type DiagnosticFactCallsRequest = DiagnosticFactEvidenceRequest & {
  fact: DiagnosticFactRow | null;
  factCallSort: FactCallSortState;
  pageSize: number;
  usingLiveFacts: boolean;
};

const defaultFactSort: FactSortState = { key: 'uncached', direction: 'desc' };

export function useDiagnosticFactSources(request: DiagnosticFactSourcesRequest) {
  const definition = diagnosticFactSourceDefinitions.find(
    candidate => candidate.key === request.activeSourceKey,
  ) ?? diagnosticFactSourceDefinitions[0];
  const sort = request.sorts[definition.key] ?? defaultFactSort;
  const query = useQuery({
    ...diagnosticFactSourceQueryOptions({
      runtime: request.contextRuntime,
      includeArchived: request.includeArchived,
      sourceKey: request.sourceKey,
      sourceRevision: request.sourceRevision,
      factSourceKey: definition.key,
      limit: request.limits[definition.key],
      sort: sort.key,
      direction: sort.direction,
    }),
    enabled: request.canUseLive,
  });
  const state = factLoadState(query, definition.title, request.canUseLive);
  const states: DiagnosticFactSourceStateMap = { [definition.key]: state };
  const modules = [{
    label: definition.title,
    status: deriveDashboardModuleState({
      enabled: request.canUseLive,
      hasData: Boolean(query.data),
      isError: query.isError,
      isFetching: query.isFetching,
      isPending: query.isPending,
    }),
  }];

  return {
    states,
    modules,
    progress: dashboardModuleProgress(modules.map(module => module.status)),
    progressError: query.isError && !query.data
      ? `${definition.title} unavailable: ${errorMessage(query.error)}`
      : null,
    sourceIsUpdating: (sourceKey: DiagnosticFactSourceKey) =>
      sourceKey === definition.key && query.isFetching && Boolean(query.data),
  };
}

export function useDiagnosticFactCalls(request: DiagnosticFactCallsRequest) {
  const enabled = request.canUseLive && request.usingLiveFacts && Boolean(request.fact);
  const query = useInfiniteQuery({
    ...diagnosticFactCallsQueryOptions({
      runtime: request.contextRuntime,
      includeArchived: request.includeArchived,
      sourceKey: request.sourceKey,
      sourceRevision: request.sourceRevision,
      fact: request.fact ?? {},
      pageSize: request.pageSize,
      sort: request.factCallSort.key,
      direction: request.factCallSort.direction,
    }),
    enabled,
  });
  const result = useMemo(() => {
    const pages = query.data?.pages ?? [];
    if (!pages.length) return null;
    return pages.slice(1).reduce(mergeFactCallResults, pages[0]);
  }, [query.data]);
  const state = factCallsState(enabled, query, result);

  return {
    query,
    result,
    state,
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
    },
  };
}

function factLoadState(
  query: { data?: unknown; error: unknown; isError: boolean; isFetching: boolean; isPending: boolean },
  title: string,
  enabled: boolean,
): FactLoadState {
  if (query.data) return { status: 'loaded', payload: query.data as Extract<FactLoadState, { status: 'loaded' }>['payload'] };
  if (!enabled) return { status: 'idle', message: 'Static aggregate fallback' };
  if (query.isError) return { status: 'error', message: errorMessage(query.error) };
  if (query.isFetching || query.isPending) return { status: 'loading', message: `Loading ${title.toLowerCase()}...` };
  return { status: 'idle', message: 'Waiting for live diagnostics' };
}

function factCallsState(
  enabled: boolean,
  query: { error: unknown; isError: boolean; isFetchingNextPage: boolean; isPending: boolean },
  result: DiagnosticFactCallsResult | null,
): FactCallsState {
  if (!enabled) return { status: 'idle', message: 'Static aggregate fact calls' };
  if (query.isError) return { status: 'error', message: errorMessage(query.error), result: result ?? undefined };
  if (result && query.isFetchingNextPage) return { status: 'appending', result };
  if (result) return { status: 'loaded', result };
  if (query.isPending) return { status: 'loading', message: 'Loading calls for selected fact...' };
  return { status: 'idle', message: 'Select a diagnostic fact' };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
