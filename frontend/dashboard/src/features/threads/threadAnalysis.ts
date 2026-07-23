import type { CallRow } from '../../api/types';
import type { ThreadCallSortDirection, ThreadCallSortKey } from './threadsUrlState';

export function compareCallTimeDescending(left: CallRow, right: CallRow): number {
  return callTimestamp(right) - callTimestamp(left);
}

export function sortThreadCalls(
  calls: CallRow[],
  sortKey: ThreadCallSortKey,
  direction: ThreadCallSortDirection,
): CallRow[] {
  return [...calls].sort((left, right) => {
    const comparison = compareThreadCallSortValues(
      threadCallSortValue(left, sortKey),
      threadCallSortValue(right, sortKey),
    );
    const primary = direction === 'asc' ? comparison : -comparison;
    return primary || compareCallTimeDescending(left, right) || left.id.localeCompare(right.id);
  });
}

function callTimestamp(call: CallRow): number {
  const parsed = Date.parse(call.rawTime || call.time);
  return Number.isFinite(parsed) ? parsed : 0;
}

function threadCallSortValue(call: CallRow, sortKey: ThreadCallSortKey): number | string {
  if (sortKey === 'duration') return call.durationSeconds;
  if (sortKey === 'gap') return call.previousCallGapSeconds;
  if (sortKey === 'initiator') return call.initiator.toLowerCase();
  if (sortKey === 'model') return call.model.toLowerCase();
  if (sortKey === 'effort') return call.effort.toLowerCase();
  if (sortKey === 'tokens') return call.totalTokens;
  if (sortKey === 'cached') return call.cachedInput;
  if (sortKey === 'uncached') return call.uncachedInput;
  if (sortKey === 'output') return call.output;
  if (sortKey === 'reasoning') return call.reasoningOutput;
  if (sortKey === 'cost') return call.cost;
  if (sortKey === 'cache') return call.cachedPct;
  return callTimestamp(call);
}

function compareThreadCallSortValues(left: number | string, right: number | string): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  return String(left).localeCompare(String(right));
}
