import type { SortingState } from '@tanstack/react-table';
import type { ThreadRow } from '../../api/types';
import { threadColumnChoices } from '../shared/tables';
import { normalizeThreadRiskFilter, threadMatchesFilters, type ThreadRiskFilter } from './threadFilterSummary';

export type ThreadCallSortKey =
  | 'newest'
  | 'duration'
  | 'gap'
  | 'initiator'
  | 'model'
  | 'effort'
  | 'tokens'
  | 'cached'
  | 'uncached'
  | 'output'
  | 'reasoning'
  | 'cost'
  | 'cache';
export type ThreadCallSortDirection = 'asc' | 'desc';

export const threadsTablePageSize = 250;
export const detailFirstSelectedThreadName = '__detail_first__';

const threadCallSortValues = new Set<string>([
  'newest',
  'duration',
  'gap',
  'initiator',
  'model',
  'effort',
  'tokens',
  'cached',
  'uncached',
  'output',
  'reasoning',
  'cost',
  'cache',
]);
const threadSortKeyValues = new Set(threadColumnChoices.map(choice => choice.id).filter(id => id !== 'investigate'));

function readSelectedThreadParam(href = window.location.href): string | null {
  return new URL(href).searchParams.get('thread')?.trim() || null;
}

export function readInitialSelectedThreadParam(href = window.location.href): string | null {
  const threadName = readSelectedThreadParam(href);
  if (threadName) return threadName;
  const expandedThread = readLegacyExpandedThreadParam(href);
  if (expandedThread) return expandedThread;
  return readThreadSearchParam('detail', href) === 'first' ? detailFirstSelectedThreadName : null;
}

export function readThreadSearchParam(name: string, href = window.location.href): string {
  return new URL(href).searchParams.get(name)?.trim() ?? '';
}

export function readThreadRiskParam(href = window.location.href): ThreadRiskFilter {
  return normalizeThreadRiskFilter(readThreadSearchParam('risk', href));
}

export function filterThreads(
  threads: ThreadRow[],
  filters: { localQuery: string; globalQuery: string; riskFilter: ThreadRiskFilter },
): ThreadRow[] {
  return threads.filter(thread => threadMatchesFilters(thread, filters));
}

export function sortThreads(threads: ThreadRow[], sorting: SortingState): ThreadRow[] {
  const sort = sorting[0];
  if (!sort || !threadSortKeyValues.has(sort.id)) {
    return [...threads];
  }
  return [...threads].sort((left, right) => compareThreadsBySort(left, right, sort.id, sort.desc));
}

export function readThreadSortingParam(href = window.location.href): SortingState {
  const sortKey = normalizeLegacyThreadSortKey(readThreadSearchParam('sort', href));
  if (!threadSortKeyValues.has(sortKey)) {
    return [];
  }
  return [{ id: sortKey, desc: readThreadSearchParam('direction', href) === 'desc' }];
}

export function readThreadPageVisibleRowsParam(pageSize: number, href = window.location.href): number {
  const page = Number(readThreadSearchParam('page', href) || 1);
  return Number.isFinite(page) && page > 1 ? Math.floor(page) * pageSize : pageSize;
}

export function readThreadCallSortParam(href = window.location.href): ThreadCallSortKey {
return normalizeThreadCallSort(readThreadSearchParam('thread_call_sort', href));
}

export function readThreadCallSortDirectionParam(
  sortKey: ThreadCallSortKey,
  href = window.location.href,
): ThreadCallSortDirection {
  const direction = readThreadSearchParam('thread_call_direction', href).toLowerCase();
  return direction === 'asc' || direction === 'desc' ? direction : defaultThreadCallSortDirection(sortKey);
}

export function normalizeThreadCallSort(value: string): ThreadCallSortKey {
const normalizedValue = normalizeLegacyThreadCallSortKey(value);
return threadCallSortValues.has(normalizedValue) ? (normalizedValue as ThreadCallSortKey) : 'newest';
}

export function defaultThreadCallSortDirection(sortKey: ThreadCallSortKey): ThreadCallSortDirection {
  return sortKey === 'cache' || sortKey === 'effort' || sortKey === 'initiator' || sortKey === 'model' ? 'asc' : 'desc';
}

export type ThreadsViewLinkState = {
  localQuery: string;
  riskFilter: ThreadRiskFilter;
  selectedThreadName: string | null;
  sorting: SortingState;
  visibleRowCount: number;
threadCallSort: ThreadCallSortKey;
threadCallSortDirection: ThreadCallSortDirection;
};

export function buildThreadsViewLink(state: ThreadsViewLinkState, href = window.location.href): URL {
  const url = new URL(href);
  url.searchParams.set('view', 'threads');
  url.searchParams.delete('record');
  url.searchParams.delete('detail');
  url.searchParams.delete('expand');
  url.searchParams.delete('threads');
  url.searchParams.delete('thread_call_page');

  const activeSort = state.sorting[0];
  const sortKey = activeSort && threadSortKeyValues.has(activeSort.id) ? activeSort.id : '';
  setOptionalThreadParam(url, 'thread_q', state.localQuery.trim(), '');
  setOptionalThreadParam(url, 'risk', state.riskFilter, 'all');
  setOptionalThreadParam(url, 'thread', state.selectedThreadName ?? '', '');
  setOptionalThreadParam(url, 'sort', sortKey, '');
  setOptionalThreadParam(url, 'direction', sortKey ? (activeSort?.desc ? 'desc' : 'asc') : '', '');
setOptionalThreadParam(url, 'page', String(threadPageNumberFromVisibleRows(state.visibleRowCount, threadsTablePageSize)), '1');
setOptionalThreadParam(url, 'thread_call_sort', state.selectedThreadName ? state.threadCallSort : '', 'newest');
setOptionalThreadParam(
  url,
  'thread_call_direction',
  state.selectedThreadName ? state.threadCallSortDirection : '',
  defaultThreadCallSortDirection(state.threadCallSort),
);
  return url;
}

export function threadPageNumberFromVisibleRows(visibleRows: number, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(visibleRows, pageSize) / pageSize));
}

function readLegacyExpandedThreadParam(href: string): string | null {
  const params = new URL(href).searchParams;
  const expand = params.get('expand')?.trim();
  if (expand === 'first' || expand === 'all') return detailFirstSelectedThreadName;
  const expandedThreads = params
    .get('threads')
    ?.split(',')
    .map(thread => thread.trim())
    .filter(Boolean);
  return expandedThreads?.[0] ?? null;
}

function normalizeLegacyThreadSortKey(value: string): string {
  if (value === 'total') return 'totalTokens';
  if (value === 'usage') return 'credits';
  if (value === 'cache') return 'cachePct';
  if (value === 'context') return 'contextPct';
  return value;
}

function normalizeLegacyThreadCallSortKey(value: string): string {
if (value === 'time') return 'newest';
if (value === 'total') {
return 'tokens';
}
  return value;
}

function compareThreadsBySort(left: ThreadRow, right: ThreadRow, key: string, desc: boolean): number {
  const comparison = compareThreadSortValues(threadSortValue(left, key), threadSortValue(right, key));
  const ordered = desc ? -comparison : comparison;
  return ordered || left.name.localeCompare(right.name);
}

function threadSortValue(thread: ThreadRow, key: string): number | string | null {
  if (key === 'latestActivity') return thread.latestActivityRaw || thread.latestActivity;
  if (key === 'totalDuration') return thread.totalDurationSeconds;
  if (key === 'averageGap') return thread.averageGapSeconds;
  const value = thread[key as keyof ThreadRow];
  if (typeof value === 'number' || typeof value === 'string') {
    return typeof value === 'string' ? value.toLowerCase() : value;
  }
  return null;
}

function compareThreadSortValues(left: number | string | null, right: number | string | null): number {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  if (typeof left === 'string' || typeof right === 'string') return String(left).localeCompare(String(right));
  return left - right;
}

function setOptionalThreadParam(url: URL, name: string, value: string, defaultValue: string) {
  if (!value || value === defaultValue) {
    url.searchParams.delete(name);
    return;
  }
  url.searchParams.set(name, value);
}
