import { describe, expect, it } from 'vitest';

import {
  evidenceConsolePrimaryRoutes,
  evidenceConsoleRouteIds,
  evidenceConsoleRoutes,
  evidenceConsoleSettingsRoute,
  exploreModes,
} from './evidenceConsoleRoutes';

describe('Evidence Console routes', () => {
  it('defines the exact stable target route and Explore-mode catalogs', () => {
    expect(evidenceConsoleRouteIds).toEqual(['home', 'explore', 'limits', 'evidence', 'settings']);
    expect(exploreModes).toEqual(['calls', 'threads']);
    expect(evidenceConsoleRoutes.map(route => route.id)).toEqual(evidenceConsoleRouteIds);
  });

  it('keeps target IDs and user-facing labels unique', () => {
    expect(new Set(evidenceConsoleRoutes.map(route => route.id))).toHaveLength(evidenceConsoleRoutes.length);
    expect(new Set(evidenceConsoleRoutes.map(route => route.label))).toHaveLength(evidenceConsoleRoutes.length);
  });

  it('exposes exactly three analytical destinations and one separate utility', () => {
    expect(evidenceConsolePrimaryRoutes.map(route => route.id)).toEqual(['home', 'explore', 'limits']);
    expect(evidenceConsoleSettingsRoute).toMatchObject({ id: 'settings', placement: 'utility' });
    expect(evidenceConsoleRoutes.find(route => route.id === 'evidence')).toMatchObject({
      placement: 'contextual',
    });
  });
});
