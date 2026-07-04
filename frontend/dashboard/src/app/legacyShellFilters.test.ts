import { describe, expect, it } from 'vitest';

import { readLegacyShellFilters } from './legacyShellFilters';

describe('legacy shell filters', () => {
  it('accepts time as a date preset alias for copied shell links', () => {
    expect(readLegacyShellFilters('?time=last-7-days')).toEqual(
      expect.objectContaining({
        active: true,
        datePreset: 'last-7-days',
      }),
    );
  });

  it('keeps date ahead of time when both URL params are present', () => {
    expect(readLegacyShellFilters('?date=this-month&time=last-7-days')).toEqual(
      expect.objectContaining({
        active: true,
        datePreset: 'this-month',
      }),
    );
  });
});
