import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ContextRuntime } from '../api/types';
import type { OverviewEndpointCache } from './overviewEndpointCache';
import { loadOverviewEndpoints, type OverviewEndpointBundle } from './overviewQueries';

const runtime: ContextRuntime = {
  apiToken: 'local-token',
  contextApiEnabled: false,
  fileMode: false,
};

afterEach(() => vi.unstubAllGlobals());

describe('overview focused endpoint query', () => {
  it('loads summary and recommendations with the same history scope', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.startsWith('/api/summary')
        ? {
            schema: 'codex-usage-tracker-summary-v1',
            group_by: 'date',
            include_archived: true,
            privacy_mode: 'normal',
            rows: [],
          }
        : {
            schema: 'codex-usage-tracker-recommendations-v1',
            filters: { include_archived: true },
            row_count: 0,
            total_matched_rows: 0,
            truncated: false,
            rows: [],
          };
      return new Response(JSON.stringify(payload), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const bundle = await loadOverviewEndpoints({
      runtime,
      includeArchived: true,
      since: '2026-07-01',
    });

    expect(bundle.summary.data?.includeArchived).toBe(true);
    expect(bundle.recommendations.data?.includeArchived).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes('include_archived=true'))).toBe(true);
  });

  it('keeps a successful endpoint when its peer fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).startsWith('/api/summary')) return new Response('unavailable', { status: 503 });
      return new Response(JSON.stringify({
        schema: 'codex-usage-tracker-recommendations-v1',
        filters: { include_archived: false },
        row_count: 0,
        total_matched_rows: 0,
        truncated: false,
        rows: [],
      }), { status: 200 });
    }));

    const bundle = await loadOverviewEndpoints({ runtime, includeArchived: false });

    expect(bundle.summary.error).toContain('HTTP 503');
    expect(bundle.recommendations.data?.rowCount).toBe(0);
  });

  it('restores a revision-matched aggregate bundle without refetching', async () => {
    const cachedBundle = emptyBundle();
    const cache: OverviewEndpointCache = {
      read: vi.fn(() => cachedBundle),
      write: vi.fn(),
    };
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const bundle = await loadOverviewEndpoints({
      runtime,
      includeArchived: false,
      sourceRevision: 'refresh-2',
      cache,
    });

    expect(bundle).toBe(cachedBundle);
    expect(cache.read).toHaveBeenCalledWith({
      includeArchived: false,
      since: '',
      sourceRevision: 'refresh-2',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('persists a successful aggregate bundle under its source revision', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(
      String(input).startsWith('/api/summary')
        ? {
            schema: 'codex-usage-tracker-summary-v1',
            group_by: 'date',
            include_archived: false,
            privacy_mode: 'normal',
            rows: [],
          }
        : {
            schema: 'codex-usage-tracker-recommendations-v1',
            filters: { include_archived: false },
            row_count: 0,
            total_matched_rows: 0,
            truncated: false,
            rows: [],
          },
    ), { status: 200 })));
    const cache: OverviewEndpointCache = {
      read: vi.fn(() => null),
      write: vi.fn(),
    };

    const bundle = await loadOverviewEndpoints({
      runtime,
      includeArchived: false,
      since: '2026-07-04',
      sourceRevision: 'refresh-3',
      cache,
    });

    expect(cache.write).toHaveBeenCalledWith({
      includeArchived: false,
      since: '2026-07-04',
      sourceRevision: 'refresh-3',
    }, bundle);
  });
});

function emptyBundle(): OverviewEndpointBundle {
  return {
    summary: {
      data: {
        schema: 'codex-usage-tracker-summary-v1',
        groupBy: 'date',
        includeArchived: false,
        privacyMode: 'normal',
        rows: [],
      },
      error: null,
    },
    recommendations: {
      data: {
        schema: 'codex-usage-tracker-recommendations-v1',
        includeArchived: false,
        rowCount: 0,
        totalMatchedRows: 0,
        truncated: false,
        rows: [],
      },
      error: null,
    },
  };
}
