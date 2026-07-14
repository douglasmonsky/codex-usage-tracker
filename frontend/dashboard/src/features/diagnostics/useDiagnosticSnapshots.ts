import { useQueries, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import {
  diagnosticSnapshotDefinitions,
  refreshDiagnosticSnapshot,
  refreshDiagnosticSnapshots,
  type DiagnosticSnapshotDefinition,
  type DiagnosticSnapshotMap,
} from '../../api/diagnostics';
import type { ContextRuntime } from '../../api/types';
import {
  dashboardModuleProgress,
  deriveDashboardModuleState,
} from '../../data/dashboardQueryRegistry';
import { diagnosticSnapshotQueryOptions } from '../../data/diagnosticsQueries';

type DiagnosticSnapshotsRequest = {
  canUseLive: boolean;
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
};

export function useDiagnosticSnapshots(request: DiagnosticSnapshotsRequest) {
  const queryClient = useQueryClient();
  const queries = useQueries({
    queries: diagnosticSnapshotDefinitions.map(definition => ({
      ...diagnosticSnapshotQueryOptions({
        runtime: request.contextRuntime,
        includeArchived: request.includeArchived,
        sourceKey: request.sourceKey,
        sourceRevision: request.sourceRevision,
        snapshotKey: definition.key,
      }),
      enabled: request.canUseLive,
    })),
  });
  const snapshots = useMemo<DiagnosticSnapshotMap>(() => Object.fromEntries(
    queries.flatMap((query, index) => query.data
      ? [[diagnosticSnapshotDefinitions[index].key, query.data] as const]
      : []),
  ), [queries]);
  const modules = diagnosticSnapshotDefinitions.map((definition, index) => ({
    label: definition.title,
    status: deriveDashboardModuleState({
      enabled: request.canUseLive,
      hasData: Boolean(queries[index].data),
      isError: queries[index].isError,
      isFetching: queries[index].isFetching,
      isPending: queries[index].isPending,
    }),
  }));

  async function refreshAll(): Promise<DiagnosticSnapshotMap> {
    const refreshed = await refreshDiagnosticSnapshots(request.contextRuntime);
    for (const definition of diagnosticSnapshotDefinitions) {
      const payload = refreshed[definition.key];
      if (payload) queryClient.setQueryData(snapshotQueryKey(request, definition), payload);
    }
    return refreshed;
  }

  async function refreshOne(definition: DiagnosticSnapshotDefinition) {
    const payload = await refreshDiagnosticSnapshot(definition, request.contextRuntime);
    queryClient.setQueryData(snapshotQueryKey(request, definition), payload);
    return payload;
  }

  return {
    snapshots,
    modules,
    progress: dashboardModuleProgress(modules.map(module => module.status)),
    progressError: terminalSnapshotError(queries),
    loading: queries.some(query => query.isFetching),
    refreshAll,
    refreshOne,
  };
}

function snapshotQueryKey(
  request: DiagnosticSnapshotsRequest,
  definition: DiagnosticSnapshotDefinition,
) {
  return diagnosticSnapshotQueryOptions({
    runtime: request.contextRuntime,
    includeArchived: request.includeArchived,
    sourceKey: request.sourceKey,
    sourceRevision: request.sourceRevision,
    snapshotKey: definition.key,
  }).queryKey;
}

function terminalSnapshotError(
  queries: Array<{ data?: unknown; error: unknown; isError: boolean }>,
): string | null {
  const index = queries.findIndex(query => query.isError && !query.data);
  if (index < 0) return null;
  return `${diagnosticSnapshotDefinitions[index].title} unavailable: ${errorMessage(queries[index].error)}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
