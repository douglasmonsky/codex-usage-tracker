import { describe, expect, it } from 'vitest';

import {
  legacyDirectRouteIds,
  legacyRouteAliases,
  normalizeDashboardRouteInput,
} from './legacyRouteAliases';

describe('legacy Evidence Console route aliases', () => {
  it('owns the complete deterministic 0.23 compatibility mapping', () => {
    expect(legacyRouteAliases).toEqual({
      overview: { view: 'home', params: {} },
      calls: { view: 'explore', params: { mode: 'calls' } },
      threads: { view: 'explore', params: { mode: 'threads' } },
      call: { view: 'evidence', params: { kind: 'call' } },
      'usage-drain': { view: 'limits', params: {} },
      settings: { view: 'settings', params: {} },
      investigator: null,
      'compression-lab': null,
      diagnostics: null,
      'cache-context': null,
      reports: null,
    });
    expect(legacyDirectRouteIds).toEqual([
      'investigator',
      'compression-lab',
      'diagnostics',
      'cache-context',
      'reports',
    ]);
  });

  it('normalizes aliases without hiding direct-only workbench routes', () => {
    expect(normalizeDashboardRouteInput('calls')).toEqual({
      view: 'explore',
      params: { mode: 'calls' },
    });
    expect(normalizeDashboardRouteInput('insights')).toEqual({ view: 'home', params: {} });
    expect(normalizeDashboardRouteInput('diagnostics')).toEqual({
      view: 'diagnostics',
      params: {},
    });
    expect(normalizeDashboardRouteInput('unknown')).toBeNull();
  });

  it('returns fresh parameter objects so normalization is mutation-safe', () => {
    const first = normalizeDashboardRouteInput('calls');
    const second = normalizeDashboardRouteInput('calls');
    expect(first).toEqual(second);
    expect(first?.params).not.toBe(second?.params);
  });
});
