import type { ColumnDef } from '@tanstack/react-table';

import type { CallRow } from '../../api/types';
import type { ThreadCallSortKey } from './threadsUrlState';

export const callSortByColumn: Partial<Record<string, ThreadCallSortKey>> = {
  time: 'newest',
  duration: 'duration',
  previousCallGap: 'gap',
  initiator: 'initiator',
  model: 'model',
  effort: 'effort',
  totalTokens: 'tokens',
  cachedInput: 'cached',
  uncachedInput: 'uncached',
  output: 'output',
  reasoningOutput: 'reasoning',
  cost: 'cost',
  cachedPct: 'cache',
};

export const callColumnBySort: Record<ThreadCallSortKey, string> = {
  newest: 'time',
  duration: 'duration',
  gap: 'previousCallGap',
  initiator: 'initiator',
  model: 'model',
  effort: 'effort',
  tokens: 'totalTokens',
  cached: 'cachedInput',
  uncached: 'uncachedInput',
  output: 'output',
  reasoning: 'reasoningOutput',
  cost: 'cost',
  cache: 'cachedPct',
};

export function callColumnId(column: ColumnDef<CallRow, unknown>): string {
  if (column.id) return column.id;
  if ('accessorKey' in column && typeof column.accessorKey === 'string') {
    return column.accessorKey;
  }
  return '';
}
