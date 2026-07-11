import type { CallRow, ThreadRow } from '../../api/types';
import { formatNumber, money, pct } from '../shared/format';
import type { ThreadCallSortDirection, ThreadCallSortKey } from './threadsUrlState';

export type ThreadLifecycle = {
  firstExpensive: { call: CallRow; index: number } | null;
  largestJump: { call: CallRow; tokens: number } | null;
  cacheTrend: number | null;
  contextTrend: number | null;
  subagentBeforeSpike: boolean;
};

export type ThreadRelationships = {
  parentThreadLabel: string;
  subagentCalls: number;
  autoReviewCalls: number;
  attachedCalls: number;
  spawnedThreads: number;
  spawnedChildCalls: number;
};

export type ThreadStatus = {
  pricingStatus: string;
  creditStatus: string;
  cacheStatus: string;
  contextStatus: string;
  nextAction: string;
};

export type ThreadImpact = {
  codexCredits: string;
  allowanceImpact: string;
  attentionScore: string;
  costPerCall: string;
};

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

export function computeThreadLifecycle(calls: CallRow[], selectedThreadName: string): ThreadLifecycle {
  const chronologicalCalls = [...calls].sort((left, right) => callTimestamp(left) - callTimestamp(right));
  let largestJump: ThreadLifecycle['largestJump'] = null;
  let firstExpensive: ThreadLifecycle['firstExpensive'] = null;
  let subagentBeforeSpike = false;

  chronologicalCalls.forEach((call, index) => {
    if (!largestJump || call.totalTokens > largestJump.tokens) {
      largestJump = { call, tokens: call.totalTokens };
      subagentBeforeSpike = chronologicalCalls
        .slice(0, index)
        .some(candidate => isSubagentCall(candidate, selectedThreadName));
    }
    if (!firstExpensive && (call.cost >= 1 || (call.contextWindowPct ?? 0) >= 60)) {
      firstExpensive = { call, index };
    }
  });

  return {
    firstExpensive,
    largestJump,
    cacheTrend: trendBetween(chronologicalCalls.map(call => call.cachedPct)),
    contextTrend: trendBetween(
      chronologicalCalls
        .map(call => call.contextWindowPct)
        .filter((value): value is number => value !== null),
    ),
    subagentBeforeSpike,
  };
}

export function computeThreadRelationships(
  calls: CallRow[],
  allCalls: CallRow[],
  selectedThreadName: string,
): ThreadRelationships {
  const parentThreadLabel = dominantParentThread(calls, selectedThreadName);
  const childCalls = allCalls.filter(
    call => call.parentThread.trim() === selectedThreadName && call.thread !== selectedThreadName,
  );
  return {
    parentThreadLabel,
    subagentCalls: calls.filter(call => isSubagentCall(call, selectedThreadName)).length,
    autoReviewCalls: calls.filter(isAutoReviewCall).length,
    attachedCalls: calls.filter(
      call => Boolean(call.parentThread.trim() && call.parentThread.trim() !== selectedThreadName),
    ).length,
    spawnedThreads: new Set(childCalls.map(call => call.thread).filter(Boolean)).size,
    spawnedChildCalls: childCalls.length,
  };
}

export function countThreadEfficiencySignals(calls: CallRow[]): number {
  return calls.filter(call => {
    const signal = call.signal.trim().toLowerCase();
    return Boolean((signal && signal !== 'aggregate') || call.recommendation.trim());
  }).length;
}

export function computeThreadStatus(
  calls: CallRow[],
  selected: ThreadRow | null,
  lifecycle: ThreadLifecycle,
): ThreadStatus {
  return {
    pricingStatus: threadPricingStatus(calls),
    creditStatus: threadCreditStatus(calls),
    cacheStatus: selected ? pct(selected.cachePct) : '-',
    contextStatus: selected?.contextPct == null ? '-' : pct(selected.contextPct),
    nextAction: threadNextAction(selected, lifecycle),
  };
}

export function computeThreadImpact(
  selected: ThreadRow | null,
  status: ThreadStatus,
  relationships: ThreadRelationships,
  signalCount: number,
): ThreadImpact | null {
  if (!selected) return null;
  const attentionScore = threadAttentionScore(selected, status, relationships, signalCount);
  return {
    codexCredits: `${formatCredits(selected.credits)} (${status.creditStatus})`,
    allowanceImpact: `${formatCredits(selected.credits)} counted`,
    attentionScore: formatNumber(attentionScore),
    costPerCall: money(selected.costPerCall),
  };
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

export function formatTrendPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return `${value >= 0 ? '+' : ''}${pct(value)}`;
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

function dominantParentThread(calls: CallRow[], selectedThreadName: string): string {
  const counts = new Map<string, number>();
  calls.forEach(call => {
    const parentThread = call.parentThread.trim();
    if (!parentThread || parentThread === selectedThreadName) return;
    counts.set(parentThread, (counts.get(parentThread) ?? 0) + 1);
  });
  return [...counts.entries()].sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  )[0]?.[0] ?? '';
}

function isSubagentCall(call: CallRow, selectedThreadName: string): boolean {
  const parentThread = call.parentThread.trim();
  return Boolean(parentThread && parentThread !== selectedThreadName) || call.initiator.toLowerCase().includes('subagent');
}

function isAutoReviewCall(call: CallRow): boolean {
  const model = call.model.toLowerCase();
  const initiator = call.initiator.toLowerCase();
  return model.includes('auto-review') || initiator.includes('auto-review');
}

function threadAttentionScore(
  selected: ThreadRow,
  status: ThreadStatus,
  relationships: ThreadRelationships,
  signalCount: number,
): number {
  const contextRatio = (selected.contextPct ?? 0) / 100;
  const cacheRatio = selected.cachePct / 100;
  const pricingScore = status.pricingStatus === 'No price'
    ? 36
    : status.pricingStatus === 'Estimated' || status.pricingStatus === 'Mixed'
      ? 18
      : 0;
  const relationScore = relationships.subagentCalls * 4
    + relationships.autoReviewCalls * 6
    + relationships.attachedCalls * 3;
  return Math.round(
    clamp(selected.cost * 24, 0, 72)
      + clamp(selected.totalTokens / 3500, 0, 42)
      + clamp((0.55 - cacheRatio) * 70, 0, 38)
      + clamp(contextRatio * 45, 0, 45)
      + pricingScore
      + clamp(selected.credits * 2.4, 0, 72)
      + relationScore
      + signalCount * 10,
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function threadPricingStatus(calls: CallRow[]): string {
  if (!calls.length) return 'Unknown';
  const pricedCalls = calls.filter(call => call.cost > 0);
  const estimatedCalls = calls.filter(call => call.pricingEstimated);
  if (!pricedCalls.length) return 'No price';
  if (estimatedCalls.length === calls.length) return 'Estimated';
  if (estimatedCalls.length > 0 || pricedCalls.length < calls.length) return 'Mixed';
  return 'Configured';
}

function threadCreditStatus(calls: CallRow[]): string {
  if (!calls.length) return 'Unknown';
  const ratedCalls = calls.filter(call => call.credits > 0);
  const estimatedCalls = calls.filter(
    call => call.usageCreditConfidence.trim().toLowerCase() === 'estimated',
  );
  if (!ratedCalls.length) return 'No mapped rate';
  if (estimatedCalls.length === calls.length) return 'Estimated mapping';
  if (estimatedCalls.length > 0 || ratedCalls.length < calls.length) return 'Mixed';
  return 'Official match';
}

function threadNextAction(selected: ThreadRow | null, lifecycle: ThreadLifecycle): string {
  if (lifecycle.contextTrend !== null && lifecycle.contextTrend >= 20) return 'Review context growth';
  if (lifecycle.cacheTrend !== null && lifecycle.cacheTrend <= -25) return 'Check cache drop';
  if (lifecycle.subagentBeforeSpike) return 'Compare subagent calls';
  if (selected && ((selected.contextPct ?? 0) >= 60 || selected.cachePct < 30)) {
    return 'Inspect thread timeline';
  }
  return 'Review recommendations';
}

function trendBetween(values: number[]): number | null {
  if (values.length < 2) return null;
  return values[values.length - 1] - values[0];
}
