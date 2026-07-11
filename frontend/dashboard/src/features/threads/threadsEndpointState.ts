import type { SortingState } from '@tanstack/react-table';

import type { ContextRuntime } from '../../api/types';
import type { ThreadsApiSort } from '../../data/exploreQueries';
import type { ThreadRiskFilter } from './threadFilterSummary';

const apiSortByColumn: Record<string, ThreadsApiSort> = {
  name: 'thread',
  latestActivity: 'time',
  turns: 'calls',
  totalTokens: 'tokens',
  cachePct: 'cache',
};

export type ThreadsEndpointState = {
  enabled: boolean;
  reason: string;
  query: string;
  sort: ThreadsApiSort;
  direction: 'asc' | 'desc';
};

export function threadsEndpointState(input: {
  runtime: ContextRuntime;
  enabled: boolean;
  globalQuery: string;
  localQuery: string;
  riskFilter: ThreadRiskFilter;
  sorting: SortingState;
}): ThreadsEndpointState {
  const selectedSort = input.sorting[0];
  const sort = selectedSort ? apiSortByColumn[selectedSort.id] : 'tokens';
  const reason = fallbackReason(input, sort);
  return {
    enabled: !reason,
    reason,
    query: input.localQuery.trim() || input.globalQuery.trim(),
    sort: sort ?? 'tokens',
    direction: selectedSort ? (selectedSort.desc ? 'desc' : 'asc') : 'desc',
  };
}

function fallbackReason(
  input: Parameters<typeof threadsEndpointState>[0],
  sort: ThreadsApiSort | undefined,
): string {
  if (!input.enabled || input.runtime.fileMode || !input.runtime.apiToken) return 'Stored snapshot';
  if (input.globalQuery.trim() && input.localQuery.trim()) return 'Multiple searches use loaded snapshot';
  if (input.riskFilter !== 'all') return 'Risk filter uses loaded snapshot';
  if (!sort) return 'This sort uses loaded snapshot';
  return '';
}
