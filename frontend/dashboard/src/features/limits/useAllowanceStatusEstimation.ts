import { useQuery } from '@tanstack/react-query';
import { useRef } from 'react';

import { loadAllowanceStatus } from '../../api/allowanceIntelligence';
import type { AllowanceStatusPayload } from '../../api/allowanceIntelligenceTypes';
import type { ContextRuntime } from '../../api/types';
import {
  allowanceStatusPollInterval,
  isPageVisible,
} from './allowancePolling';

export function useFastAllowanceStatus(
  runtime: ContextRuntime,
  includeArchived: boolean,
  queryScope: readonly unknown[],
) {
  const snapshotRef = useRef<AllowanceStatusPayload | null>(null);
  return useQuery({
    queryKey: ['allowance-v2', 'status', ...queryScope],
    queryFn: async ({ signal }) => {
      const previous = snapshotRef.current;
      const payload = await loadAllowanceStatus(runtime, {
        includeArchived,
        sinceRevision: previous?.revision,
        includeEstimation: false,
      }, signal);
      if (!payload.changed && previous) {
        return { ...previous, changed: false, quality: payload.quality, next: payload.next };
      }
      snapshotRef.current = payload;
      return payload;
    },
    staleTime: 0,
    refetchInterval: query => allowanceStatusPollInterval(
      query.state.data?.data_state,
      query.state.fetchFailureCount,
      isPageVisible(),
    ),
    refetchIntervalInBackground: false,
    retry: false,
  });
}

export function useAllowanceStatusEstimation(
  runtime: ContextRuntime,
  includeArchived: boolean,
  queryScope: readonly unknown[],
  status: AllowanceStatusPayload | undefined,
): AllowanceStatusPayload | undefined {
  const revision = status?.revision ?? '';
  const query = useQuery({
    queryKey: ['allowance-v2', 'status-estimation', ...queryScope, revision],
    queryFn: ({ signal }) => loadAllowanceStatus(runtime, {
      includeArchived,
      includeEstimation: true,
    }, signal),
    enabled: Boolean(revision) && !status?.estimation,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  return query.data ?? status;
}
