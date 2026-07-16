import type { CallRow } from '../../api/types';
import { pct } from '../shared/format';
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

export function threadLabelsMatch(callThread: string, threadName: string): boolean {
  const callLabel = callThread.trim();
  const summaryLabel = threadName.trim();
  return callLabel === summaryLabel || callLabel.startsWith(summaryLabel) || summaryLabel.startsWith(callLabel);
}

export function formatCredits(value: number): string {
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)} credits`;
}

export function formatCallContextUse(call: CallRow): string {
  return call.contextWindowPct == null ? '-' : pct(call.contextWindowPct);
}

export function callPricingStatusText(call: CallRow): string {
  if (call.cost <= 0) return 'No configured price';
  return call.pricingEstimated ? 'Best-guess estimate' : 'Configured price';
}

export function timelineSeverityClass(value: number | null): string {
  if (value == null) return 'low';
  if (value >= 65) return 'high';
  if (value >= 35) return 'medium';
  return 'low';
}

export function timelineWidth(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '0%';
  return `${Math.round(clamp(value, 0, 100))}%`;
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
