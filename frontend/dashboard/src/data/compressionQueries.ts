import { queryOptions } from '@tanstack/react-query';

import {
  loadCompressionProfile,
  type CompressionScopeRequest,
} from '../api/compressionLab';
import type { ContextRuntime } from '../api/types';
import {
  dashboardQueryDefinition,
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQuerySource,
} from './dashboardQueryRegistry';

const compressionProfileQuery = dashboardQueryDefinition('compression-profile');

export type CompressionQueryRequest = CompressionScopeRequest & {
  runtime: ContextRuntime;
  sourceKey?: string;
  sourceRevision: string;
};

export function compressionProfileQueryOptions(request: CompressionQueryRequest) {
  const source = dashboardQuerySource({
    sourceKey: request.sourceKey ?? (request.runtime.fileMode ? 'static-file' : 'local-api'),
    sourceRevision: request.sourceRevision,
  });
  const scope = {
    historyScope: request.includeArchived ? 'all' as const : 'active' as const,
    since: request.since ?? null,
  };
  return queryOptions({
    queryKey: dashboardQueryKey(
      compressionProfileQuery,
      source,
      scope,
      request.until ?? null,
      request.thread ?? null,
      request.model ?? null,
      request.effort ?? null,
      request.detectorFamilies ?? [],
    ),
    queryFn: ({ signal }) => loadCompressionProfile(request.runtime, request, { signal }),
    ...dashboardQueryOptions(compressionProfileQuery.dataClass),
  });
}
