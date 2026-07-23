import type { HistoryScope } from './shellUrl';
export { historyScopeFromPayload } from '../api/historyScope';

export type HistoryScopeStatusInput = {
  historyScope: HistoryScope;
  activeRows?: number;
  allRows?: number;
  archivedRows?: number;
};

export function historyScopeStatusLabel({
  historyScope,
  activeRows,
  allRows,
  archivedRows,
}: HistoryScopeStatusInput): string {
  const archivedCount = archivedAvailableRowCount({ activeRows, allRows, archivedRows });
  if (historyScope === 'all') {
    if (archivedCount === null) return 'All history selected';
    return archivedCount > 0
      ? `All history includes ${archivedCount.toLocaleString()} archived calls`
      : 'All history selected; no archived calls are indexed yet';
  }
  if (archivedCount === null || archivedCount <= 0) return 'Active sessions only';
  return `Active sessions only; ${archivedCount.toLocaleString()} archived calls hidden`;
}

function archivedAvailableRowCount({
  activeRows,
  allRows,
  archivedRows,
}: {
  activeRows?: number;
  allRows?: number;
  archivedRows?: number;
}): number | null {
  const archived = finiteOptionalCount(archivedRows);
  if (archived !== null) return archived;
  const active = finiteOptionalCount(activeRows);
  const all = finiteOptionalCount(allRows);
  return active !== null && all !== null ? Math.max(all - active, 0) : null;
}

function finiteOptionalCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.round(value) : null;
}
