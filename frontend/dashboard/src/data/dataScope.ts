import type { DashboardBootPayload } from '../api/types';

export type HistoryScope = 'active' | 'all';

export type LoadWindow = 'day' | 'week' | 'rows' | 'all';

export type DataScope = {
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  limit: number | null;
  since: string | null;
};

export type DataScopePreference = {
  historyScope?: HistoryScope;
  loadWindow?: LoadWindow;
  loadLimit?: number;
};

const rowLimitMin = 1;
export const rowLimitNoCap = 0;
const rowLimitStep = 100;

const rowLimitLoadMoreStep = 1_000;
const defaultRowLimit = 500;
const dataScopeSessionKey = 'codexUsageDashboardLoadSettings';
const loadWindowDurationsMs: Partial<Record<LoadWindow, number>> = {
  day: 24 * 60 * 60 * 1_000,
  week: 7 * 24 * 60 * 60 * 1_000,
};

export function loadLimitFromPayload(payload: DashboardBootPayload | null, fallback = defaultRowLimit): number {
  if (payload?.limit_label === 'All') return rowLimitNoCap;
  if (fallback === rowLimitNoCap && payload?.limit == null) return rowLimitNoCap;
  const value = Number(payload?.limit ?? payload?.loaded_row_count ?? fallback);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

export function normalizeRowLimit(value: number): number {
  if (!Number.isFinite(value)) return rowLimitMin;
  if (value <= rowLimitNoCap) return rowLimitNoCap;
  return Math.max(rowLimitMin, Math.round(value));
}

export function finiteRowLimitFallback(...values: Array<number | null | undefined>): number {
  const finiteValue = values.find(value => typeof value === 'number' && Number.isFinite(value) && value > 0);
  return finiteValue ? Math.max(rowLimitMin, Math.round(finiteValue)) : rowLimitMin;
}

export function dataScopeFromCompatibilityLimit(
  limit: number,
  historyScope: HistoryScope,
  since: string | null = null,
  loadWindow: LoadWindow = 'rows',
): DataScope {
  const normalized = normalizeRowLimit(limit);
  const scopedLimit = loadWindow === 'rows' && normalized !== rowLimitNoCap ? normalized : null;
  return { historyScope, loadWindow, limit: scopedLimit, since };
}

export function requestLimitForDataScope(scope: DataScope): number {
  return scope.limit ?? rowLimitNoCap;
}

export function currentLoadWindowFromPayload(payload: DashboardBootPayload | null): LoadWindow {
  if (isLoadWindow(payload?.load_window)) return payload.load_window;
  if (payload?.since) return 'week';
  return payload?.limit_label === 'All' || payload?.limit == null ? 'all' : 'rows';
}

export function initialLoadWindowFromPayload(payload: DashboardBootPayload | null): LoadWindow {
  return isLoadWindow(payload?.default_load_window)
    ? payload.default_load_window
    : currentLoadWindowFromPayload(payload);
}

export function sinceForLoadWindow(loadWindow: LoadWindow, now = new Date()): string | null {
  const duration = loadWindowDurationsMs[loadWindow];
  if (!duration) return null;
  const minuteAnchor = Math.floor(now.getTime() / 60_000) * 60_000;
  return new Date(minuteAnchor - duration).toISOString();
}

export function loadWindowLabel(loadWindow: LoadWindow, rowLimit = defaultRowLimit): string {
  if (loadWindow === 'day') return 'Last 24 hours';
  if (loadWindow === 'week') return 'Last 7 days';
  if (loadWindow === 'all') return 'All time';
  return `Most recent ${normalizeRowLimit(rowLimit).toLocaleString()}`;
}

export function readDataScopePreference(storage = sessionStorageOrNull()): DataScopePreference | null {
  if (!storage) return null;
  try {
    const rawValue = storage.getItem(dataScopeSessionKey);
    if (!rawValue) return null;
    const parsed = JSON.parse(rawValue) as {
      loadLimit?: unknown;
      historyScope?: unknown;
      loadWindow?: unknown;
    };
    const loadLimit =
      typeof parsed.loadLimit === 'number' && Number.isFinite(parsed.loadLimit)
        ? normalizeRowLimit(parsed.loadLimit)
        : undefined;
    const historyScope =
      parsed.historyScope === 'active' || parsed.historyScope === 'all' ? parsed.historyScope : undefined;
    const loadWindow = isLoadWindow(parsed.loadWindow) ? parsed.loadWindow : undefined;
    return loadLimit === undefined && historyScope === undefined && loadWindow === undefined
      ? null
      : { loadLimit, historyScope, loadWindow };
  } catch {
    return null;
  }
}

export function storeDataScopePreference(
  loadLimit: number,
  historyScope: HistoryScope,
  loadWindow: LoadWindow = 'rows',
  storage = sessionStorageOrNull(),
): void {
  if (!storage) return;
  try {
    storage.setItem(
      dataScopeSessionKey,
      JSON.stringify({ loadLimit: normalizeRowLimit(loadLimit), historyScope, loadWindow }),
    );
  } catch {
    // Storage can be disabled in private or embedded browser contexts.
  }
}

function isLoadWindow(value: unknown): value is LoadWindow {
  return value === 'day' || value === 'week' || value === 'rows' || value === 'all';
}

export function rowLimitSliderMaxValue({
  currentLimit,
  loadedRows,
  pendingLimit,
}: {
  currentLimit: number;
  loadedRows: number;
  pendingLimit: number;
}): number {
  const requestedFiniteRows = pendingLimit === rowLimitNoCap ? 0 : pendingLimit + rowLimitStep;
  const currentFiniteRows = currentLimit === rowLimitNoCap ? 0 : currentLimit;
  const largestFiniteRange = Math.max(rowLimitMin, currentFiniteRows, requestedFiniteRows, loadedRows);
  return Math.ceil((largestFiniteRange + rowLimitLoadMoreStep) / rowLimitStep) * rowLimitStep;
}

export function rowLimitValueLabel(value: number): string {
  return value === rowLimitNoCap ? 'No cap' : value.toLocaleString();
}

export function rowLimitSummaryLabel(value: number): string {
  return value === rowLimitNoCap ? 'no row cap' : `${value.toLocaleString()} rows`;
}

export function nextRowLoadLimit({
  currentLimit,
  loadedRows,
  pendingLimit,
}: {
  currentLimit: number;
  loadedRows: number;
  pendingLimit: number;
}): number {
  const baseLimit = Math.max(
    finiteRowLimitFallback(currentLimit),
    finiteRowLimitFallback(pendingLimit),
    finiteRowLimitFallback(loadedRows),
  );
  return baseLimit + rowLimitLoadMoreStep;
}

export function rowLoadStatusLabel({
  loadedRows,
  limit,
  totalRows,
}: {
  loadedRows: number;
  limit: number;
  totalRows: number;
}): string {
  if (limit === rowLimitNoCap && loadedRows > 0) return `Loaded all ${loadedRows.toLocaleString()}`;
  if (totalRows > loadedRows) return `Loaded ${loadedRows.toLocaleString()} of ${totalRows.toLocaleString()}`;
  return `Loaded ${loadedRows.toLocaleString()} rows`;
}

function sessionStorageOrNull(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}
