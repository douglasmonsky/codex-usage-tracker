import type { DashboardBootPayload } from '../api/types';

export const rowLimitMin = 100;
export const rowLimitNoCap = 0;
export const rowLimitStep = 100;

const rowLimitLoadMoreStep = 1_000;
const defaultRowLimit = 500;

export function loadLimitFromPayload(payload: DashboardBootPayload | null, fallback = defaultRowLimit): number {
  if (payload?.limit_label === 'All') {
    return rowLimitNoCap;
  }
  if (fallback === rowLimitNoCap && payload?.limit == null) {
    return rowLimitNoCap;
  }
  const value = Number(payload?.limit ?? payload?.loaded_row_count ?? fallback);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

export function normalizeRowLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return rowLimitMin;
  }
  if (value <= rowLimitNoCap) {
    return rowLimitNoCap;
  }
  return Math.max(rowLimitMin, Math.round(value));
}

export function finiteRowLimitFallback(...values: Array<number | null | undefined>): number {
  const finiteValue = values.find(value => typeof value === 'number' && Number.isFinite(value) && value > 0);
  return finiteValue ? Math.max(rowLimitMin, Math.round(finiteValue)) : rowLimitMin;
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
  if (limit === rowLimitNoCap && loadedRows > 0) {
    return `Loaded all ${loadedRows.toLocaleString()}`;
  }
  if (totalRows > loadedRows) {
    return `Loaded ${loadedRows.toLocaleString()} of ${totalRows.toLocaleString()}`;
  }
  return `Loaded ${loadedRows.toLocaleString()} rows`;
}
