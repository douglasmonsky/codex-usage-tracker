import type { CallsSortKey, ConfidenceFilter, SortDirection, SourceFilter, TimeFilter } from './callFilterSummary';

export type Density = 'dense' | 'roomy';

export const detailFirstSelectedCallId = '__detail_first__';

const confidenceFilterValues = new Set<string>([
  'all',
  'cost-exact',
  'cost-estimated',
  'cost-unpriced',
  'credit-exact',
  'credit-estimated',
  'credit-override',
  'credit-missing',
]);
const timeFilterValues = new Set<string>(['all', 'today', 'this-week', 'last-7-days', 'this-month', 'custom']);
const sourceFilterValues = new Set<string>(['all', 'project', 'session', 'git', 'source-file', 'missing']);
const callsSortKeyValues = new Set<string>([
  'time',
  'duration',
  'gap',
  'attention',
  'thread',
  'initiator',
  'model',
  'effort',
  'total',
  'cached',
  'uncached',
  'output',
  'reasoning',
  'cost',
  'usage',
  'cache',
  'context',
]);

export function readCallsSearchParam(name: string, href = window.location.href): string {
  return new URL(href).searchParams.get(name)?.trim() ?? '';
}

export function readConfidenceFilterParam(href = window.location.href): ConfidenceFilter {
  const value = readCallsSearchParam('confidence', href) || readCallsSearchParam('pricing', href);
  return confidenceFilterValues.has(value) ? (value as ConfidenceFilter) : 'all';
}

export function readSourceFilterParam(href = window.location.href): SourceFilter {
  const value = readCallsSearchParam('source', href);
  return sourceFilterValues.has(value) ? (value as SourceFilter) : 'all';
}

export function readTimeFilterParam(href = window.location.href): TimeFilter {
  const value = readCallsSearchParam('date', href) || readCallsSearchParam('time', href);
  return timeFilterValues.has(value) ? (value as TimeFilter) : 'all';
}

export function readDateInputParam(name: string, href = window.location.href): string {
  return cleanCallsDateInput(readCallsSearchParam(name, href));
}

export function readInitialSelectedCallId(href = window.location.href): string | null {
  const recordId = readCallsSearchParam('record', href);
  if (recordId) return recordId;
  return readCallsSearchParam('detail', href) === 'first' ? detailFirstSelectedCallId : null;
}

export function readCallsSortKeyParam(href = window.location.href): CallsSortKey {
  const value = readCallsSearchParam('sort', href);
  return coerceCallsSortKey(value);
}

export function coerceCallsSortKey(value: string): CallsSortKey {
  return callsSortKeyValues.has(value) ? (value as CallsSortKey) : 'time';
}

export function readSortDirectionParam(sortKey: CallsSortKey, href = window.location.href): SortDirection {
  const value = readCallsSearchParam('direction', href);
  return value === 'asc' || value === 'desc' ? value : defaultCallsSortDirection(sortKey);
}

export function readDensityParam(href = window.location.href): Density {
  return readCallsSearchParam('density', href) === 'roomy' ? 'roomy' : 'dense';
}

export function readPageVisibleRowsParam(pageSize: number, href = window.location.href): number {
  const page = Number(readCallsSearchParam('page', href) || 1);
  return Number.isFinite(page) && page > 1 ? Math.floor(page) * pageSize : pageSize;
}

export type CallsViewLinkState = {
  localQuery: string;
  modelFilter: string;
  effortFilter: string;
  confidenceFilter: ConfidenceFilter;
  sourceFilter: SourceFilter;
  timeFilter: TimeFilter;
  dateStart: string;
  dateEnd: string;
  sortKey: CallsSortKey;
  sortDirection: SortDirection;
  density: Density;
  selectedRecordId: string;
  visibleRowCount: number;
  pageSize: number;
};

export function buildCallsViewLink(state: CallsViewLinkState, href = window.location.href): URL {
  const url = new URL(href);
  url.searchParams.set('view', 'calls');
  url.searchParams.delete('detail');
  url.searchParams.delete('pricing');
  setOptionalCallsParam(url, 'record', state.selectedRecordId, '');
  setOptionalCallsParam(url, 'call_q', state.localQuery.trim(), '');
  setOptionalCallsParam(url, 'model', state.modelFilter, 'all');
  setOptionalCallsParam(url, 'effort', state.effortFilter, 'all');
  setOptionalCallsParam(url, 'confidence', state.confidenceFilter, 'all');
  setOptionalCallsParam(url, 'source', state.sourceFilter, 'all');
  setOptionalCallsParam(url, 'time', state.timeFilter, 'all');
  setOptionalCallsParam(url, 'date', state.timeFilter, 'all');
  setOptionalCallsParam(url, 'from', state.timeFilter === 'custom' ? state.dateStart : '', '');
  setOptionalCallsParam(url, 'to', state.timeFilter === 'custom' ? state.dateEnd : '', '');
  setOptionalCallsParam(url, 'sort', state.sortKey, 'time');
  setOptionalCallsParam(url, 'direction', state.sortDirection, defaultCallsSortDirection(state.sortKey));
  setOptionalCallsParam(url, 'density', state.density, 'dense');
  setOptionalCallsParam(url, 'page', String(pageNumberFromVisibleRows(state.visibleRowCount, state.pageSize)), '1');
  return url;
}

export function defaultCallsSortDirection(key: CallsSortKey): SortDirection {
  return key === 'cache' || key === 'effort' || key === 'initiator' || key === 'model' || key === 'thread' ? 'asc' : 'desc';
}

export function cleanCallsDateInput(value: string): string {
  const date = parseCallsDateInput(value);
  return date ? localCallsDateKey(date) : '';
}

function pageNumberFromVisibleRows(visibleRows: number, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(visibleRows, pageSize) / pageSize));
}

function setOptionalCallsParam(url: URL, name: string, value: string, defaultValue: string) {
  if (!value || value === defaultValue) {
    url.searchParams.delete(name);
    return;
  }
  url.searchParams.set(name, value);
}

function parseCallsDateInput(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

function localCallsDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
