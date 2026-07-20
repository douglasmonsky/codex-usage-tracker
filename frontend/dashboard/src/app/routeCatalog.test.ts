import { describe, expect, it } from 'vitest';

import { dashboardRenderedViewIds } from '../routes/DashboardRouteView';
import { dashboardViewIds } from '../routes/dashboardSearch';
import { secondaryNavItems } from './navigation';
import { navigationForPhase, routeCatalog, routeDefinition } from './routeCatalog';

describe('dashboard route catalog', () => {
  it('catalogs and renders every dashboard view exactly once', () => {
    expect(new Set(routeCatalog.map(route => route.id))).toEqual(new Set(dashboardViewIds));
    expect(dashboardRenderedViewIds).toHaveLength(dashboardViewIds.length);
    expect(new Set(dashboardRenderedViewIds)).toEqual(new Set(dashboardViewIds));
  });

  it('keeps route IDs and labels unique', () => {
    expect(new Set(routeCatalog.map(route => route.id))).toHaveLength(routeCatalog.length);
    expect(new Set(routeCatalog.map(route => route.label))).toHaveLength(routeCatalog.length);
  });

  it('classifies contextual and transitioning routes independently from navigation exposure', () => {
    expect(routeDefinition('call')).toMatchObject({
      maturity: 'stable', placement: 'contextual', lifecycle: 'active',
    });
    expect(routeDefinition('diagnostics')).toMatchObject({
      maturity: 'experimental', placement: 'primary', lifecycle: 'active',
    });
    expect(routeDefinition('cache-context')).toMatchObject({
      maturity: 'experimental', placement: 'hidden', lifecycle: 'transitioning',
    });
  });

  it('limits experimental navigation eligibility to the two approved routes', () => {
    expect(routeCatalog.filter(route => route.experimentalNavigationEligible).map(route => route.id)).toEqual([
      'investigator',
      'compression-lab',
    ]);
  });

  it('locks the Release N foundation navigation baseline', () => {
    expect(navigationForPhase('foundation').map(route => route.id)).toEqual([
      'overview', 'investigator', 'compression-lab', 'calls', 'threads',
      'usage-drain', 'cache-context', 'diagnostics', 'reports', 'settings',
    ]);
  });

  it('keeps legacy quick-link aliases hidden and deprecated', () => {
    expect(secondaryNavItems.map(({ label, maturity, placement, lifecycle }) => ({
      label, maturity, placement, lifecycle,
    }))).toEqual([
      { label: 'Files', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
      { label: 'Commands', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
      { label: 'Models', maturity: 'stable', placement: 'hidden', lifecycle: 'deprecated' },
    ]);
  });

  it('preserves the full Task 1 route params separately from handoff params', () => {
    expect(Object.fromEntries(routeCatalog.map(route => [route.id, route.safeParams]))).toEqual({
      overview: [], investigator: ['finding'], 'compression-lab': [],
      calls: ['explore', 'detail', 'call_q', 'source', 'sort', 'direction', 'density', 'page'],
      call: ['record', 'return', 'mode', 'max_entries', 'max_chars', 'include_tool_output', 'include_compaction_history'],
      threads: ['thread', 'thread_key', 'expand', 'threads', 'thread_q', 'risk', 'thread_call_sort', 'thread_call_page'],
      'usage-drain': ['usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence', 'limit_window', 'limit_hypothesis'],
      'cache-context': ['cache_thread'], diagnostics: ['diagnostic_source', 'diagnostic_fact'],
      reports: ['report'], settings: [],
    });
    expect(Object.fromEntries(routeCatalog.map(route => [route.id, route.handoffParams]))).toEqual({
      overview: [], investigator: ['finding'], 'compression-lab': [],
      calls: ['explore', 'detail', 'source', 'sort', 'direction', 'density', 'page'],
      call: ['record', 'return', 'mode'],
      threads: ['thread_key', 'expand', 'risk', 'thread_call_sort', 'thread_call_page'],
      'usage-drain': ['usage_plan', 'usage_effort', 'usage_subagents', 'usage_sample', 'usage_confidence', 'limit_window', 'limit_hypothesis'],
      'cache-context': [], diagnostics: ['diagnostic_source', 'diagnostic_fact'],
      reports: ['report'], settings: [],
    });
  });
});
