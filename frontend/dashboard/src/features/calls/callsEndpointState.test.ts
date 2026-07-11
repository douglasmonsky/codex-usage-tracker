import { describe, expect, it, vi } from 'vitest';

import { callsEndpointState } from './callsEndpointState';

const runtime = { apiToken: 'token', contextApiEnabled: false, fileMode: false };

describe('callsEndpointState', () => {
  it('maps supported filters and sort to the focused API', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-10T12:00:00Z'));
    const state = callsEndpointState({
      runtime,
      enabled: true,
      activePreset: '',
      sourceFilter: 'all',
      sortKey: 'total',
      timeFilter: 'last-7-days',
      dateStart: '',
      dateEnd: '',
      confidenceFilter: 'credit-override',
      globalQuery: 'cache',
      localQuery: '',
      modelFilter: 'gpt-5.6',
      effortFilter: 'high',
    });
    vi.useRealTimers();

    expect(state.enabled).toBe(true);
    expect(state.sort).toBe('tokens');
    expect(state.filters).toMatchObject({
      query: 'cache', model: 'gpt-5.6', effort: 'high', creditConfidence: 'user_override',
    });
    expect(state.filters.since).toContain('2026-07-04');
    expect(Date.parse(state.filters.until ?? '') - Date.parse(state.filters.since ?? '')).toBeGreaterThan(6 * 86_400_000);
  });

  it.each([
    ['preset', { activePreset: 'large-calls' }],
    ['source', { sourceFilter: 'git' }],
    ['derived sort', { sortKey: 'attention' }],
  ])('uses stored rows for unsupported %s state', (_label, override) => {
    const state = callsEndpointState({
      runtime,
      enabled: true,
      activePreset: '',
      sourceFilter: 'all',
      sortKey: 'time',
      timeFilter: 'all',
      dateStart: '',
      dateEnd: '',
      confidenceFilter: 'all',
      globalQuery: '',
      localQuery: '',
      modelFilter: 'all',
      effortFilter: 'all',
      ...override,
    } as Parameters<typeof callsEndpointState>[0]);
    expect(state.enabled).toBe(false);
    expect(state.reason).toContain('snapshot');
  });
});
