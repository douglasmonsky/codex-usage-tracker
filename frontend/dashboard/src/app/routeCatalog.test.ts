import { describe, expect, it } from 'vitest';

import { dashboardRenderedViewIds } from '../routes/DashboardRouteView';
import { dashboardViewIds } from '../routes/dashboardSearch';
import { navItems, settingsNavItem } from './navigation';
import { navigationForPhase, routeCatalog, routeDefinition } from './routeCatalog';

describe('dashboard route catalog', () => {
  it('catalogs and renders every accepted dashboard view exactly once', () => {
    expect(new Set(routeCatalog.map(route => route.id))).toEqual(new Set(dashboardViewIds));
    expect(dashboardRenderedViewIds).toHaveLength(dashboardViewIds.length);
    expect(new Set(dashboardRenderedViewIds)).toEqual(new Set(dashboardViewIds));
  });

  it('keeps route IDs and labels unique', () => {
    expect(new Set(routeCatalog.map(route => route.id))).toHaveLength(routeCatalog.length);
    expect(new Set(routeCatalog.map(route => route.label))).toHaveLength(routeCatalog.length);
  });

  it('separates stable targets from direct-only compatibility routes', () => {
    expect(routeDefinition('evidence')).toMatchObject({
      maturity: 'stable', placement: 'contextual', lifecycle: 'active',
    });
    expect(routeDefinition('diagnostics')).toMatchObject({
      maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated',
    });
    expect(routeDefinition('cache-context')).toMatchObject({
      maturity: 'experimental', placement: 'hidden', lifecycle: 'deprecated',
    });
  });

  it('never makes a legacy workbench eligible for experimental navigation', () => {
    expect(routeCatalog.filter(route => route.experimentalNavigationEligible)).toEqual([]);
  });

  it('keeps every deprecated workbench direct-only with a concrete replacement', () => {
    const deprecatedWorkbenches = {
      investigator: 'usage_analyze(goal="usage_spike") → usage_evidence',
      'compression-lab': 'usage_analyze(goal="token_waste"); full-profile compression tools through 0.24.x',
      'cache-context': 'usage_analyze(goal="context_bloat") or usage_analyze(goal="cache_failure")',
      diagnostics: 'usage_query(entity="call", measures=["tokens"]) → usage_evidence',
      reports: 'usage_analyze(goal="usage_spike") or usage_query(...)',
    } as const;

    for (const id of Object.keys(deprecatedWorkbenches) as Array<keyof typeof deprecatedWorkbenches>) {
      expect(routeDefinition(id)).toMatchObject({
        placement: 'hidden',
        lifecycle: 'deprecated',
        replacementMcpOperation: deprecatedWorkbenches[id],
        replacementHref: '?view=explore&mode=calls',
      });
    }
  });

  it('exposes exactly three analytical destinations and Settings as a utility', () => {
    expect(navigationForPhase('simplified').map(route => route.id)).toEqual([
      'home', 'explore', 'limits',
    ]);
    expect(navItems.map(item => item.id)).toEqual(['home', 'explore', 'limits']);
    expect(settingsNavItem.id).toBe('settings');
    expect([...navItems, settingsNavItem]).toHaveLength(4);
  });

  it('keeps handoff parameters inside each route safe-parameter boundary', () => {
    for (const route of routeCatalog) {
      expect(new Set(route.safeParams).size).toBe(route.safeParams.length);
      expect(route.handoffParams.every(param => route.safeParams.includes(param))).toBe(true);
    }
    expect(routeDefinition('explore').handoffParams).toContain('mode');
    expect(routeDefinition('evidence').handoffParams).toEqual([
      'kind', 'record', 'thread_key', 'analysis', 'finding', 'evidence', 'return',
      'return_mode', 'mode',
    ]);
    expect(routeDefinition('limits').handoffParams).toContain('window');
  });
});
