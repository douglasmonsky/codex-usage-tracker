import { queryOptions } from '@tanstack/react-query';

import { loadReportsPack } from '../api/reports';
import type { ContextRuntime } from '../api/types';
import type { LoadWindow } from './dataScope';
import {
  dashboardQueryDefinition,
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQuerySource,
} from './dashboardQueryRegistry';

const reportsQuery = dashboardQueryDefinition('reports');

export type ReportsQueryRequest = {
  runtime: ContextRuntime;
  includeArchived: boolean;
  loadWindow: LoadWindow;
  limit: number;
  evidenceLimit: number;
  sourceKey?: string;
  sourceRevision: string;
};

export function reportsQueryOptions(request: ReportsQueryRequest) {
  return queryOptions({
    queryKey: dashboardQueryKey(
      reportsQuery,
      dashboardQuerySource({
        sourceKey: request.sourceKey ?? (request.runtime.fileMode ? 'static-file' : 'local-api'),
        sourceRevision: request.sourceRevision,
      }),
      {
        historyScope: request.includeArchived ? 'all' : 'active',
        loadWindow: request.loadWindow,
        limit: request.limit,
      },
      request.evidenceLimit,
    ),
    queryFn: ({ signal }) => loadReportsPack(request.runtime, {
      limit: request.limit,
      evidenceLimit: request.evidenceLimit,
      includeArchived: request.includeArchived,
      signal,
    }),
    ...dashboardQueryOptions(reportsQuery.dataClass),
  });
}
