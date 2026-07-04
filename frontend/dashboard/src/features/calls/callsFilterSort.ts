import type { CallRow } from '../../api/types';
import { rowMatchesQuery } from '../shared/filtering';
import { callMatchesInvestigationPreset } from '../shared/investigationPresets';
import {
  callMatchesConfidenceFilter,
  callMatchesSourceFilter,
  type CallsDateRange,
  type CallsSortKey,
  type ConfidenceFilter,
  type SortDirection,
  type SourceFilter,
  type TimeFilter,
} from './callFilterSummary';

export type CallsFilterState = {
  globalQuery: string;
  localQuery: string;
  modelFilter: string;
  effortFilter: string;
  confidenceFilter: ConfidenceFilter;
  sourceFilter: SourceFilter;
  timeFilter: TimeFilter;
  dateStart: string;
  dateEnd: string;
  activePreset: string;
};

export function filterCalls(calls: CallRow[], filters: CallsFilterState): CallRow[] {
  return calls.filter(call => callMatchesCallsFilter(call, filters));
}

export function sortCalls(calls: CallRow[], sortKey: CallsSortKey, sortDirection: SortDirection): CallRow[] {
  return [...calls].sort((left, right) => compareCallsBySort(left, right, sortKey, sortDirection));
}

export function callsDateRange(
  filter: TimeFilter,
  dateStart: string,
  dateEnd: string,
  now: Date,
): CallsDateRange {
  const today = localDay(now);
  if (filter === 'custom') {
    const start = parseDateInput(dateStart);
    const end = parseDateInput(dateEnd);
    if (start && end && start > end) {
      return { active: true, invalid: true, start, endExclusive: addDays(end, 1), label: 'Invalid date range' };
    }
    return {
      active: Boolean(start || end),
      invalid: false,
      start,
      endExclusive: end ? addDays(end, 1) : null,
      label: formatDateRangeLabel('Custom', start, end),
    };
  }
  if (filter === 'today') {
    return {
      active: true,
      invalid: false,
      start: today,
      endExclusive: addDays(today, 1),
      label: formatDateRangeLabel('Today', today, today),
    };
  }
  if (filter === 'this-week') {
    const start = weekStart(today);
    return {
      active: true,
      invalid: false,
      start,
      endExclusive: addDays(start, 7),
      label: formatDateRangeLabel('This week', start, addDays(start, 6)),
    };
  }
  if (filter === 'last-7-days') {
    const start = addDays(today, -6);
    return {
      active: true,
      invalid: false,
      start,
      endExclusive: addDays(today, 1),
      label: formatDateRangeLabel('Last 7 days', start, today),
    };
  }
  if (filter === 'this-month') {
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    const endExclusive = new Date(today.getFullYear(), today.getMonth() + 1, 1);
    return {
      active: true,
      invalid: false,
      start,
      endExclusive,
      label: formatDateRangeLabel('This month', start, addDays(endExclusive, -1)),
    };
  }
  return { active: false, invalid: false, start: null, endExclusive: null, label: 'All time' };
}

function callMatchesCallsFilter(call: CallRow, filters: CallsFilterState): boolean {
  if (filters.modelFilter !== 'all' && call.model !== filters.modelFilter) {
    return false;
  }
  if (filters.effortFilter !== 'all' && call.effort !== filters.effortFilter) {
    return false;
  }
  if (!callMatchesConfidenceFilter(call, filters.confidenceFilter)) {
    return false;
  }
  if (!callMatchesSourceFilter(call, filters.sourceFilter)) {
    return false;
  }
  if (!callMatchesTimeFilter(call, filters.timeFilter, filters.dateStart, filters.dateEnd)) {
    return false;
  }
  if (filters.activePreset && !callMatchesInvestigationPreset(call, filters.activePreset)) {
    return false;
  }
  const searchableValues = [
    call.thread,
    call.cwd,
    call.project,
    call.projectRelativeCwd,
    call.gitBranch,
    call.gitRemoteLabel,
    call.sessionId,
    call.model,
    call.effort,
    call.initiator,
    call.initiatorReason,
    call.signal,
    call.recommendation,
    call.rawTime,
    call.sourceFile,
    call.lineNumber,
    call.tags.join(' '),
  ];
  return [filters.globalQuery, filters.localQuery].every(query => rowMatchesQuery(searchableValues, query));
}

function compareCallsBySort(left: CallRow, right: CallRow, key: CallsSortKey, direction: SortDirection): number {
  const leftValue = callSortValue(left, key);
  const rightValue = callSortValue(right, key);
  if (leftValue === null && rightValue !== null) {
    return 1;
  }
  if (rightValue === null && leftValue !== null) {
    return -1;
  }
  const comparison = compareCallSortValues(leftValue, rightValue);
  if (comparison !== 0) {
    return direction === 'asc' ? comparison : -comparison;
  }
  return compareCallTimeDescending(left, right) || left.id.localeCompare(right.id);
}

function callSortValue(call: CallRow, key: CallsSortKey): number | string | null {
  if (key === 'time') return callTime(call);
  if (key === 'duration') return call.durationSeconds;
  if (key === 'gap') return call.previousCallGapSeconds;
  if (key === 'attention') return callAttentionScore(call);
  if (key === 'thread') return call.thread.toLowerCase();
  if (key === 'initiator') return call.initiator.toLowerCase();
  if (key === 'model') return call.model.toLowerCase();
  if (key === 'effort') return call.effort.toLowerCase();
  if (key === 'total') return call.totalTokens;
  if (key === 'cached') return call.input * (call.cachedPct / 100);
  if (key === 'uncached') return call.uncachedInput;
  if (key === 'output') return call.output;
  if (key === 'reasoning') return call.reasoningOutput;
  if (key === 'cost') return call.cost;
  if (key === 'usage') return call.credits;
  if (key === 'cache') return call.cachedPct;
  return call.contextWindowPct;
}

function callAttentionScore(call: CallRow): number {
  const explicitSignal = call.signal && call.signal !== 'aggregate' ? 1_000 : 0;
  const recommendation = call.recommendation ? 750 : 0;
  const contextPressure = call.contextWindowPct ?? 0;
  const uncachedInputWeight = Math.min(call.uncachedInput / 1_000, 250);
  const costWeight = Math.min(call.cost * 25, 200);
  const creditWeight = Math.min(call.credits, 200);
  const durationWeight = Math.min(call.durationSeconds / 60, 120);
  return explicitSignal + recommendation + contextPressure + uncachedInputWeight + costWeight + creditWeight + durationWeight;
}

function compareCallSortValues(left: number | string | null, right: number | string | null): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  if (typeof left === 'string' || typeof right === 'string') {
    return String(left).localeCompare(String(right));
  }
  return left - right;
}

export function compareCallTimeDescending(left: CallRow, right: CallRow): number {
  return callTime(right) - callTime(left);
}

function callTime(call: CallRow): number {
  const time = Date.parse(call.rawTime);
  return Number.isFinite(time) ? time : 0;
}

function parseDateInput(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function formatDateRangeLabel(prefix: string, start: Date | null, end: Date | null): string {
  const startLabel = start ? localDateKey(start) : '';
  const endLabel = end ? localDateKey(end) : '';
  if (startLabel && endLabel && startLabel === endLabel) return `${prefix}: ${startLabel}`;
  if (startLabel && endLabel) return `${prefix}: ${startLabel} to ${endLabel}`;
  if (startLabel) return `${prefix}: from ${startLabel}`;
  if (endLabel) return `${prefix}: through ${endLabel}`;
  return prefix;
}

function localDay(value = new Date()): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function weekStart(date: Date): Date {
  const day = date.getDay();
  return addDays(date, day === 0 ? -6 : 1 - day);
}

function callMatchesTimeFilter(call: CallRow, filter: TimeFilter, dateStart = '', dateEnd = '', now = new Date()): boolean {
  if (filter === 'all') {
    return true;
  }
  const range = callsDateRange(filter, dateStart, dateEnd, now);
  if (range.invalid) {
    return false;
  }
  if (!range.active) {
    return true;
  }
  const timestamp = Date.parse(call.rawTime);
  if (!Number.isFinite(timestamp)) {
    return false;
  }
  if (range.start && timestamp < range.start.getTime()) {
    return false;
  }
  if (range.endExclusive && timestamp >= range.endExclusive.getTime()) {
    return false;
  }
  return true;
}
