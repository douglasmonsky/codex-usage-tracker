import type { DashboardBootPayload } from '../api/types';

export type HistoryScope = 'active' | 'all';

export type DataScope = {
  historyScope: HistoryScope;
  limit: number | null;
};

export type DataScopePreference = {
  historyScope?: HistoryScope;
  loadLimit?: number;
};

export const rowLimitMin = 1;
export const rowLimitNoCap = 0;
export const rowLimitStep = 100;

const rowLimitLoadMoreStep = 1_000;
const defaultRowLimit = 500;
const dataScopeSessionKey = 'codexUsageDashboardLoadSettings';

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

export function dataScopeFromCompatibilityLimit(limit: number, historyScope: HistoryScope): DataScope {
  const normalized = normalizeRowLimit(limit);
  return { historyScope, limit: normalized === rowLimitNoCap ? null : normalized };
}

export function requestLimitForDataScope(scope: DataScope): number {
  return scope.limit ?? rowLimitNoCap;
}

export function readDataScopePreference(storage = sessionStorageOrNull()): DataScopePreference | null {
  if (!storage) return null;
  try {
    const rawValue = storage.getItem(dataScopeSessionKey);
    if (!rawValue) return null;
    const parsed = JSON.parse(rawValue) as { loadLimit?: unknown; historyScope?: unknown };
    const loadLimit =
      typeof parsed.loadLimit === 'number' && Number.isFinite(parsed.loadLimit)
        ? normalizeRowLimit(parsed.loadLimit)
        : undefined;
    const historyScope =
      parsed.historyScope === 'active' || parsed.historyScope === 'all' ? parsed.historyScope : undefined;
    return loadLimit === undefined && historyScope === undefined ? null : { loadLimit, historyScope };
  } catch {
    return null;
  }
}

export function storeDataScopePreference(
  loadLimit: number,
  historyScope: HistoryScope,
  storage = sessionStorageOrNull(),
): void {
  if (!storage) return;
  try {
    storage.setItem(
      dataScopeSessionKey,
      JSON.stringify({ loadLimit: normalizeRowLimit(loadLimit), historyScope }),
    );
  } catch {
    // Storage can be disabled in private or embedded browser contexts.
  }
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
