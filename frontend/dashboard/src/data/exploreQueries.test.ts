import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadCallsPage, loadThreadCalls, loadThreadsPage } from './exploreQueries';

const runtime = { apiToken: 'token', contextApiEnabled: false, fileMode: false };

afterEach(() => vi.restoreAllMocks());

describe('Explore endpoint queries', () => {
  it('maps call filters, sorting, scope, and paging to the focused API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
      schema: 'codex-usage-tracker-calls-v1', rows: [], row_count: 0, total_matched_rows: 0, limit: 50, offset: 100,
    }));

    await loadCallsPage({
      runtime,
      includeArchived: true,
      sourceRevision: 'rev-1',
      filters: { query: 'cache', model: 'gpt-5.6', effort: 'high', since: '2026-07-01', pricingStatus: 'priced' },
      sort: 'tokens',
      direction: 'desc',
    }, 100, 50);

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      include_archived: 'true', limit: '50', offset: '100', q: 'cache', model: 'gpt-5.6', effort: 'high',
      since: '2026-07-01', pricing_status: 'priced', sort: 'tokens', direction: 'desc',
    });
  });

  it('uses paged threads and unbounded selected-thread calls', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-threads-v1', rows: [], row_count: 0, total_matched_rows: 0,
        limit: 25, offset: 0, include_archived: false,
      }))
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'thread-a', rows: [], row_count: 0,
        total_matched_rows: 0, limit: null, offset: 0,
      }));

    await loadThreadsPage({ runtime, includeArchived: false, sourceRevision: 'rev', query: 'thread', sort: 'calls', direction: 'asc' }, 0, 25);
    await loadThreadCalls({ runtime, includeArchived: false, sourceRevision: 'rev', threadKey: 'thread-a' });

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/threads?');
    const threadCallsUrl = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost');
    expect(threadCallsUrl.pathname).toBe('/api/thread-calls');
    expect(threadCallsUrl.searchParams.get('thread_key')).toBe('thread-a');
    expect(threadCallsUrl.searchParams.get('limit')).toBe('0');
  });
});

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}
