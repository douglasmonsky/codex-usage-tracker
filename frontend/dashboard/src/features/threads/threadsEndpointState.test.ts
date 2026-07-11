import { describe, expect, it } from 'vitest';

import { threadsEndpointState } from './threadsEndpointState';

const runtime = { apiToken: 'token', contextApiEnabled: false, fileMode: false };

describe('threadsEndpointState', () => {
  it('maps supported thread sorts to the focused API', () => {
    expect(threadsEndpointState({
      runtime,
      enabled: true,
      globalQuery: '',
      localQuery: 'dashboard',
      riskFilter: 'all',
      sorting: [{ id: 'cachePct', desc: false }],
    })).toEqual({ enabled: true, reason: '', query: 'dashboard', sort: 'cache', direction: 'asc' });
  });

  it('falls back for derived risk and unsupported columns', () => {
    expect(threadsEndpointState({ runtime, enabled: true, globalQuery: '', localQuery: '', riskFilter: 'High', sorting: [] }).enabled).toBe(false);
    expect(threadsEndpointState({ runtime, enabled: true, globalQuery: '', localQuery: '', riskFilter: 'all', sorting: [{ id: 'cost', desc: true }] }).enabled).toBe(false);
  });
});
