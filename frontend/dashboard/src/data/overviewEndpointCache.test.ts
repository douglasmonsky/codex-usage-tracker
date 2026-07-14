import { describe, expect, it } from 'vitest';

import type { OverviewEndpointBundle } from './overviewQueries';
import { createOverviewEndpointCache } from './overviewEndpointCache';

describe('persistent Overview endpoint cache', () => {
  it('retains distinct data windows under the same source revision', () => {
    const cache = createOverviewEndpointCache(memoryStorageProvider());
    const bundle = emptyBundle();
    const allTime = {
      includeArchived: false,
      since: '',
      sourceKey: 'config-1',
      sourceRevision: 'refresh-1',
    };
    const lastWeek = {
      includeArchived: false,
      since: '2026-07-04T00:00:00Z',
      sourceKey: 'config-1',
      sourceRevision: 'refresh-1',
    };

    cache.write(allTime, bundle);
    cache.write(lastWeek, bundle);

    expect(cache.read(allTime)).toEqual(bundle);
    expect(cache.read(lastWeek)).toEqual(bundle);
  });

  it('does not restore an entry from an older source revision', () => {
    const cache = createOverviewEndpointCache(memoryStorageProvider());
    const identity = {
      includeArchived: false,
      since: '',
      sourceKey: 'config-1',
      sourceRevision: 'refresh-1',
    };
    cache.write(identity, emptyBundle());

    expect(cache.read({ ...identity, sourceRevision: 'refresh-2' })).toBeNull();
    expect(cache.read({ ...identity, sourceKey: 'config-2' })).toBeNull();
  });

  it('does not persist a bundle containing raw or indexed content', () => {
    const values = new Map<string, string>();
    const cache = createOverviewEndpointCache(memoryStorageProvider(values));
    const identity = {
      includeArchived: false,
      since: '',
      sourceKey: 'config-1',
      sourceRevision: 'refresh-1',
    };
    const unsafe = {
      ...emptyBundle(),
      summary: { data: { raw_context: 'private prompt' }, error: null },
    } as unknown as OverviewEndpointBundle;

    cache.write(identity, unsafe);

    expect(values.size).toBe(0);
    expect(cache.read(identity)).toBeNull();
  });

  it('quarantines an unsafe record written by an older dashboard version', () => {
    const values = new Map<string, string>();
    const identity = {
      includeArchived: false,
      since: '',
      sourceKey: 'config-1',
      sourceRevision: 'refresh-1',
    };
    values.set('codexUsageOverviewEndpointCache', JSON.stringify([{
      identity,
      bundle: {
        ...emptyBundle(),
        summary: {
          data: {
            schema: 'codex-usage-tracker-context-v1',
            entries: [{ text: 'private prompt' }],
          },
          error: null,
        },
      },
      storedAt: Date.now(),
    }]));
    const cache = createOverviewEndpointCache(memoryStorageProvider(values));

    expect(cache.read(identity)).toBeNull();
    expect(values.get('codexUsageOverviewEndpointCache')).toBe('[]');
  });
});

function memoryStorageProvider(values = new Map<string, string>()): () => Pick<Storage, 'getItem' | 'setItem'> {
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
