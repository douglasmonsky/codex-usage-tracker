import { createMemoryHistory } from '@tanstack/react-router';
import { describe, expect, it } from 'vitest';

import {
  isDashboardViewId,
  normalizeDashboardView,
  validateDashboardSearch,
} from '../routes/dashboardSearch';
import { createDashboardRouter, dashboardBasepath } from './dashboardRouter';

describe('dashboard search contract', () => {
  it('normalizes legacy and unknown views without dropping feature search state', () => {
    expect(
      validateDashboardSearch({
        view: 'insights',
        record: ' call-7 ',
        report: 'weekly-credits',
        custom_future_filter: 'preserved',
      }),
    ).toEqual({
      view: 'overview',
      record: 'call-7',
      report: 'weekly-credits',
      custom_future_filter: 'preserved',
    });
    expect(normalizeDashboardView('not-a-view')).toBe('overview');
    expect(isDashboardViewId('compression-lab')).toBe(true);
  });

  it('types shared parameters and removes invalid values', () => {
    expect(
      validateDashboardSearch({ view: 'call', return: 'insights', history: 'all', finding: '4' }),
    ).toMatchObject({ view: 'call', return: 'overview', history: 'all', finding: 4 });
    const search = validateDashboardSearch({ view: 'threads', return: 'call', history: 'weekly', finding: '-2' });
    expect(search).toEqual({ view: 'threads' });
    expect(isDashboardViewId(search.view)).toBe(true);
  });
});

describe('dashboard router', () => {
  it('keeps the served dashboard document outside the Vite asset base', () => {
    expect(dashboardBasepath()).toBe('/');
  });

  it('hydrates legacy query routes and preserves view-specific parameters', async () => {
    const history = createMemoryHistory({
      initialEntries: ['/?view=call&record=call-9&return=threads&mode=full&max_entries=50'],
    });
    const router = createDashboardRouter({ history, basepath: '/' });

    await router.load();

    expect(router.state.location.search).toMatchObject({
      view: 'call',
      record: 'call-9',
      return: 'threads',
      mode: 'full',
      max_entries: 50,
    });
  });

  it('navigates with typed search updates without erasing unrelated filters', async () => {
    const history = createMemoryHistory({ initialEntries: ['/?view=calls&model=gpt-5&history=all'] });
    const router = createDashboardRouter({ history, basepath: '/' });
    await router.load();

    await router.navigate({
      to: '.',
      search: previous => ({ ...previous, view: 'threads', thread: 'thread-7' }),
    });

    expect(router.state.location.search).toMatchObject({
      view: 'threads',
      model: 'gpt-5',
      history: 'all',
      thread: 'thread-7',
    });
  });
});
