import { describe, expect, it } from 'vitest';

import { historyScopeFromPayload, historyScopeStatusLabel } from './historyScope';

describe('history scope helpers', () => {
  it('derives history scope from payload metadata with explicit includeArchived precedence', () => {
    expect(historyScopeFromPayload(null)).toBe('active');
    expect(historyScopeFromPayload(null, 'all')).toBe('all');
    expect(historyScopeFromPayload({ rows: [], include_archived: true, history_scope: 'active' })).toBe('all');
    expect(historyScopeFromPayload({ rows: [], include_archived: false, history_scope: 'all' })).toBe('active');
    expect(historyScopeFromPayload({ rows: [], history_scope: 'all-history' })).toBe('all');
    expect(historyScopeFromPayload({ rows: [], history_scope: 'active' }, 'all')).toBe('active');
    expect(historyScopeFromPayload({ rows: [], history_scope: 'unknown' }, 'all')).toBe('all');
  });

  it('reports active-history archived rows from explicit archived counts', () => {
    expect(historyScopeStatusLabel({ historyScope: 'active', archivedRows: 42 })).toBe(
      'Active sessions only; 42 archived calls hidden',
    );
    expect(historyScopeStatusLabel({ historyScope: 'active', archivedRows: 0 })).toBe('Active sessions only');
  });

  it('falls back to all minus active row counts when archived count is absent', () => {
    expect(historyScopeStatusLabel({ historyScope: 'active', activeRows: 500, allRows: 1750 })).toBe(
      'Active sessions only; 1,250 archived calls hidden',
    );
    expect(historyScopeStatusLabel({ historyScope: 'all', activeRows: 500, allRows: 1750 })).toBe(
      'All history includes 1,250 archived calls',
    );
  });

  it('handles unknown or zero archived counts explicitly', () => {
    expect(historyScopeStatusLabel({ historyScope: 'active' })).toBe('Active sessions only');
    expect(historyScopeStatusLabel({ historyScope: 'all' })).toBe('All history selected');
    expect(historyScopeStatusLabel({ historyScope: 'all', activeRows: 500, allRows: 400 })).toBe(
      'All history selected; no archived calls are indexed yet',
    );
  });
});
