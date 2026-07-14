import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import {
  diagnosticSnapshotDefinitions,
  refreshDiagnosticSnapshots,
  type DiagnosticRefreshJob,
  type DiagnosticSnapshotMap,
} from '../../api/diagnostics';
import type { ContextRuntime } from '../../api/types';
import {
  dashboardModuleProgress,
  deriveDashboardModuleState,
} from '../../data/dashboardQueryRegistry';
import {
  investigatorAgenticQueryOptions,
  investigatorSnapshotQueryOptions,
} from '../../data/investigatorQueries';

type InvestigatorEvidenceRequest = {
  canUseLive: boolean;
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
};

export function useInvestigatorEvidence(request: InvestigatorEvidenceRequest) {
  const queryClient = useQueryClient();
  const [refreshJob, setRefreshJob] = useState<DiagnosticRefreshJob | null>(null);
  const agenticQuery = useQuery({
    ...investigatorAgenticQueryOptions({
      runtime: request.contextRuntime,
      includeArchived: request.includeArchived,
      sourceKey: request.sourceKey,
      sourceRevision: request.sourceRevision,
      evidenceLimit: 8,
    }),
    enabled: request.canUseLive,
    placeholderData: previous => previous,
  });
  const snapshotQueries = useQueries({
    queries: diagnosticSnapshotDefinitions.map(definition => ({
      ...investigatorSnapshotQueryOptions({
        runtime: request.contextRuntime,
        includeArchived: request.includeArchived,
        sourceKey: request.sourceKey,
        sourceRevision: request.sourceRevision,
        snapshotKey: definition.key,
      }),
      enabled: request.canUseLive,
    })),
  });
  const liveSnapshots = useMemo<DiagnosticSnapshotMap>(() => Object.fromEntries(
    snapshotQueries.flatMap((query, index) => query.data
      ? [[diagnosticSnapshotDefinitions[index].key, query.data] as const]
      : []),
  ), [snapshotQueries]);
  const modules = [
    {
      label: 'Investigation report',
      status: deriveDashboardModuleState({
        enabled: request.canUseLive,
        hasData: Boolean(agenticQuery.data),
        isError: agenticQuery.isError,
        isFetching: agenticQuery.isFetching,
        isPending: agenticQuery.isPending,
      }),
    },
    ...diagnosticSnapshotDefinitions.map((definition, index) => {
      const query = snapshotQueries[index];
      return {
        label: definition.title,
        status: deriveDashboardModuleState({
          enabled: request.canUseLive,
          hasData: Boolean(query.data),
          isError: query.isError,
          isFetching: query.isFetching,
          isPending: query.isPending,
        }),
      };
    }),
  ];

  async function refresh(): Promise<number> {
    setRefreshJob(null);
    const snapshots = await refreshDiagnosticSnapshots(request.contextRuntime, {
      onProgress: setRefreshJob,
    });
    for (const definition of diagnosticSnapshotDefinitions) {
      const payload = snapshots[definition.key];
      if (!payload) continue;
      queryClient.setQueryData(investigatorSnapshotQueryOptions({
        runtime: request.contextRuntime,
        includeArchived: request.includeArchived,
        sourceKey: request.sourceKey,
        sourceRevision: request.sourceRevision,
        snapshotKey: definition.key,
      }).queryKey, payload);
    }
    await agenticQuery.refetch();
    return Object.keys(snapshots).length;
  }

  return {
    agenticQuery,
    liveSnapshots,
    loadedSnapshotCount: snapshotQueries.filter(query => query.data).length,
    loadingSnapshots: snapshotQueries.some(query => query.isFetching),
    modules,
    progress: dashboardModuleProgress(modules.map(module => module.status)),
    progressError: terminalModuleError(agenticQuery, snapshotQueries),
    refreshJob,
    refresh,
  };
}

function terminalModuleError(
  agenticQuery: { data?: unknown; error: unknown; isError: boolean },
  snapshotQueries: Array<{ data?: unknown; error: unknown; isError: boolean }>,
): string | null {
  if (agenticQuery.isError && !agenticQuery.data) {
    return `Investigation report unavailable: ${errorMessage(agenticQuery.error)}`;
  }
  const snapshotIndex = snapshotQueries.findIndex(query => query.isError && !query.data);
  if (snapshotIndex < 0) return null;
  return `${diagnosticSnapshotDefinitions[snapshotIndex].title} unavailable: ${errorMessage(snapshotQueries[snapshotIndex].error)}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
