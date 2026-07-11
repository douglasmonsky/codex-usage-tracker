import { describe, expect, it } from 'vitest';

import type { OverviewEndpointBundle } from './overviewQueries';
import { createOverviewEndpointCache } from './overviewEndpointCache';

describe('persistent Overview endpoint cache', () => {
  it('retains distinct data windows under the same source revision', () => {
    const cache = createOverviewEndpointCache(memoryStorageProvider());
    const bundle = emptyBundle();
    const allTime = { includeArchived: false, since: '', sourceRevision: 'refresh-1' };
    const lastWeek = {
      includeArchived: false,
      since: '2026-07-04T00:00:00Z',
      sourceRevision: 'refresh-1',
    };

    cache.write(allTime, bundle);
    cache.write(lastWeek, bundle);

    expect(cache.read(allTime)).toEqual(bundle);
    expect(cache.read(lastWeek)).toEqual(bundle);
  });

  it('does not restore an entry from an older source revision', () => {
    const cache = createOverviewEndpointCache(memoryStorageProvider());
    const identity = { includeArchived: false, since: '', sourceRevision: 'refresh-1' };
    cache.write(identity, emptyBundle());

    expect(cache.read({ ...identity, sourceRevision: 'refresh-2' })).toBeNull();
  });
});

function memoryStorageProvider(): () => Pick<Storage, 'getItem' | 'setItem'> {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
  };
  return () => storage;
}

function emptyBundle(): OverviewEndpointBundle {
  return {
    summary: { data: null, error: null },
    recommendations: { data: null, error: null },
  };
}
