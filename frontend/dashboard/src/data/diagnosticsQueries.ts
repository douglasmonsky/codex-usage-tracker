import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';

import {
  diagnosticFactSourceDefinitions,
  loadDiagnosticFactCalls,
  loadDiagnosticFactSource,
  loadDiagnosticSnapshot,
  normalizeDiagnosticFactSortKey,
  type DiagnosticFactCallSortKey,
  type DiagnosticFactCallsResult,
  type DiagnosticFactRow,
  type DiagnosticFactSortKey,
  type DiagnosticFactSourceKey,
  type DiagnosticSnapshotKey,
  type DiagnosticSortDirection,
} from '../api/diagnostics';
import type { ContextRuntime } from '../api/types';
import {
  dashboardQueryDefinition,
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQuerySource,
} from './dashboardQueryRegistry';

export type DiagnosticQueryRequest = {
  runtime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
};

export type DiagnosticFactSourceQueryRequest = DiagnosticQueryRequest & {
  factSourceKey: DiagnosticFactSourceKey;
  limit?: number;
  offset?: number;
  sort?: DiagnosticFactSortKey;
  direction?: DiagnosticSortDirection;
};

export type DiagnosticFactCallsQueryRequest = DiagnosticQueryRequest & {
  fact: DiagnosticFactRow;
  pageSize?: number;
  sort?: DiagnosticFactCallSortKey;
  direction?: DiagnosticSortDirection;
};

export type DiagnosticSnapshotQueryRequest = DiagnosticQueryRequest & {
  snapshotKey: DiagnosticSnapshotKey;
};

const defaultFactCallPageSize = 8;
const diagnosticFactsQuery = dashboardQueryDefinition('diagnostics-facts');
const diagnosticFactCallsQuery = dashboardQueryDefinition('diagnostics-fact-calls');
const diagnosticSnapshotQuery = dashboardQueryDefinition('diagnostics-snapshot');

export function diagnosticFactSourceQueryOptions(request: DiagnosticFactSourceQueryRequest) {
  const definition = diagnosticFactSourceDefinitions.find(source => source.key === request.factSourceKey)
    ?? diagnosticFactSourceDefinitions[0];
  const limit = Math.max(1, Math.round(request.limit ?? definition.limit));
  const offset = Math.max(0, Math.round(request.offset ?? 0));
  const sort = normalizeDiagnosticFactSortKey(request.sort ?? 'uncached');
  const direction = request.direction ?? 'desc';
  return queryOptions({
    queryKey: dashboardQueryKey(
      diagnosticFactsQuery,
      diagnosticQuerySource(request),
      diagnosticQueryScope(request),
      request.factSourceKey,
      limit,
      offset,
      sort,
      direction,
    ),
    queryFn: ({ signal }) => loadDiagnosticFactSource(request.factSourceKey, request.runtime, {
      cacheKey: request.sourceRevision,
      direction,
      includeArchived: request.includeArchived,
      limit,
      offset,
      signal,
      sort,
    }),
    ...dashboardQueryOptions(diagnosticFactsQuery.dataClass),
  });
}

export function diagnosticFactCallsQueryOptions(request: DiagnosticFactCallsQueryRequest) {
  const pageSize = Math.max(1, Math.round(request.pageSize ?? defaultFactCallPageSize));
  const sort = request.sort ?? 'tokens';
  const direction = request.direction ?? 'desc';
  return infiniteQueryOptions({
    queryKey: dashboardQueryKey(
      diagnosticFactCallsQuery,
      diagnosticQuerySource(request),
      diagnosticQueryScope(request),
      String(request.fact.fact_type ?? ''),
      String(request.fact.fact_name ?? ''),
      pageSize,
      sort,
      direction,
    ),
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => loadDiagnosticFactCalls(request.fact, request.runtime, {
      cacheKey: request.sourceRevision,
      direction,
      includeArchived: request.includeArchived,
      limit: pageSize,
      offset: pageParam,
      signal,
      sort,
    }),
    getNextPageParam: (_lastPage, pages) => nextFactCallOffset(pages),
    ...dashboardQueryOptions(diagnosticFactCallsQuery.dataClass),
  });
}

export function diagnosticSnapshotQueryOptions(request: DiagnosticSnapshotQueryRequest) {
  return queryOptions({
    queryKey: dashboardQueryKey(
      diagnosticSnapshotQuery,
      diagnosticQuerySource(request),
      diagnosticQueryScope(request),
      request.snapshotKey,
    ),
    queryFn: ({ signal }) => loadDiagnosticSnapshot(request.snapshotKey, request.runtime, {
      cacheKey: request.sourceRevision,
      signal,
    }),
    ...dashboardQueryOptions(diagnosticSnapshotQuery.dataClass),
  });
}

function nextFactCallOffset(pages: DiagnosticFactCallsResult[]): number | undefined {
  const loaded = pages.reduce((total, page) => total + page.calls.length, 0);
  const totalMatched = Math.max(
    loaded,
    Number(pages.at(-1)?.rawPayload.total_matched_rows ?? loaded),
  );
  const lastPageSize = pages.at(-1)?.calls.length ?? 0;
  return loaded < totalMatched && lastPageSize > 0 ? loaded : undefined;
}

function diagnosticQuerySource(request: DiagnosticQueryRequest) {
  return dashboardQuerySource({
    sourceKey: request.sourceKey ?? (request.runtime.fileMode ? 'static-file' : 'local-api'),
    sourceRevision: request.sourceRevision,
  });
}

function diagnosticQueryScope(request: DiagnosticQueryRequest) {
  return {
    historyScope: request.includeArchived ? 'all' as const : 'active' as const,
  };
}
