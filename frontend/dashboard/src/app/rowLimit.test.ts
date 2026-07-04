import { describe, expect, it } from 'vitest';

import {
  finiteRowLimitFallback,
  loadLimitFromPayload,
  nextRowLoadLimit,
  normalizeRowLimit,
  rowLimitNoCap,
  rowLimitSliderMaxValue,
  rowLimitSummaryLabel,
  rowLimitValueLabel,
  rowLoadStatusLabel,
} from './rowLimit';

describe('row limit helpers', () => {
  it('preserves no-cap payloads and fallback requests', () => {
    expect(loadLimitFromPayload({ rows: [], limit_label: 'All' })).toBe(rowLimitNoCap);
    expect(loadLimitFromPayload({ rows: [], loaded_row_count: 875 })).toBe(875);
    expect(loadLimitFromPayload({ rows: [], limit: null }, rowLimitNoCap)).toBe(rowLimitNoCap);
    expect(loadLimitFromPayload({ rows: [], limit: Number.NaN }, 500)).toBe(500);
  });

  it('normalizes typed row counts while keeping zero as no cap', () => {
    expect(normalizeRowLimit(Number.NaN)).toBe(100);
    expect(normalizeRowLimit(-1)).toBe(rowLimitNoCap);
    expect(normalizeRowLimit(0)).toBe(rowLimitNoCap);
    expect(normalizeRowLimit(42)).toBe(100);
    expect(normalizeRowLimit(1250.4)).toBe(1250);
  });

  it('chooses finite fallbacks and expands the quick slider past current data', () => {
    expect(finiteRowLimitFallback(null, rowLimitNoCap, 250)).toBe(250);
    expect(finiteRowLimitFallback(null, rowLimitNoCap, Number.NaN)).toBe(100);
    expect(rowLimitSliderMaxValue({ currentLimit: 500, loadedRows: 900, pendingLimit: 750 })).toBe(1900);
    expect(rowLimitSliderMaxValue({ currentLimit: rowLimitNoCap, loadedRows: 12_300, pendingLimit: rowLimitNoCap })).toBe(13_300);
  });

  it('increments finite load-more requests without switching to no cap', () => {
    expect(nextRowLoadLimit({ currentLimit: 500, loadedRows: 500, pendingLimit: 500 })).toBe(1500);
    expect(nextRowLoadLimit({ currentLimit: rowLimitNoCap, loadedRows: 2400, pendingLimit: rowLimitNoCap })).toBe(3400);
  });

  it('keeps row limit labels explicit for massive data controls', () => {
    expect(rowLimitValueLabel(rowLimitNoCap)).toBe('No cap');
    expect(rowLimitValueLabel(5000)).toBe('5,000');
    expect(rowLimitSummaryLabel(rowLimitNoCap)).toBe('no row cap');
    expect(rowLimitSummaryLabel(5000)).toBe('5,000 rows');
    expect(rowLoadStatusLabel({ loadedRows: 500, limit: 500, totalRows: 1700 })).toBe('Loaded 500 of 1,700');
    expect(rowLoadStatusLabel({ loadedRows: 1700, limit: rowLimitNoCap, totalRows: 1700 })).toBe('Loaded all 1,700');
    expect(rowLoadStatusLabel({ loadedRows: 1700, limit: 2000, totalRows: 1700 })).toBe('Loaded 1,700 rows');
  });
});
