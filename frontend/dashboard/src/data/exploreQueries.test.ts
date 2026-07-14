import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  loadCallsPage,
  loadThreadCallContext,
  loadThreadCalls,
  loadThreadsPage,
} from './exploreQueries';

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

  it('pages both thread summaries and selected-thread calls', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-threads-v1', rows: [], row_count: 0, total_matched_rows: 0,
        limit: 25, offset: 0, include_archived: false,
      }))
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'thread-a', rows: [], row_count: 0,
        total_matched_rows: 125, limit: 25, offset: 100,
      }));

    await loadThreadsPage({ runtime, includeArchived: false, sourceRevision: 'rev', query: 'thread', sort: 'calls', direction: 'asc' }, 0, 25);
    await loadThreadCalls(
      { runtime, includeArchived: false, sourceRevision: 'rev', threadKey: 'thread-a' },
      100,
      25,
    );

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/threads?');
    const threadCallsUrl = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost');
    expect(threadCallsUrl.pathname).toBe('/api/thread-calls');
    expect(threadCallsUrl.searchParams.get('thread_key')).toBe('thread-a');
    expect(threadCallsUrl.searchParams.get('limit')).toBe('25');
    expect(threadCallsUrl.searchParams.get('offset')).toBe('100');
  });

  it('passes the selected thread sort to SQLite and fetches bounded context around a call', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'thread-a',
        rows: [{ record_id: 'selected', event_timestamp: '2026-07-02T10:00:00Z', thread_name: 'thread-a' }],
        row_count: 1, total_matched_rows: 101, limit: 25, offset: 0,
      }))
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'thread-a',
        rows: [
          { record_id: 'newer', event_timestamp: '2026-07-02T10:01:00Z', thread_name: 'thread-a' },
          { record_id: 'selected', event_timestamp: '2026-07-02T10:00:00Z', thread_name: 'thread-a' },
        ],
        row_count: 2, total_matched_rows: 51, limit: 51, offset: 0,
      }))
      .mockResolvedValueOnce(response({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'thread-a',
        rows: [
          { record_id: 'selected', event_timestamp: '2026-07-02T10:00:00Z', thread_name: 'thread-a' },
          { record_id: 'older', event_timestamp: '2026-07-02T09:59:00Z', thread_name: 'thread-a' },
        ],
        row_count: 2, total_matched_rows: 51, limit: 51, offset: 0,
      }));

    await loadThreadCalls({
      runtime,
      includeArchived: true,
      sourceRevision: 'rev',
      threadKey: 'thread-a',
      sort: 'cost',
      direction: 'asc',
    }, 0, 25);
    const context = await loadThreadCallContext({
      runtime,
      includeArchived: true,
      sourceRevision: 'rev',
      threadKey: 'thread-a',
      selectedRecordId: 'selected',
      selectedEventTimestamp: '2026-07-02T10:00:00Z',
    });

    const sortedUrl = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(sortedUrl.searchParams.get('sort')).toBe('cost');
    expect(sortedUrl.searchParams.get('direction')).toBe('asc');
    const newerUrl = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost');
    const olderUrl = new URL(String(fetchMock.mock.calls[2][0]), 'http://localhost');
    expect(newerUrl.searchParams.get('since')).toBe('2026-07-02T10:00:00Z');
    expect(newerUrl.searchParams.get('direction')).toBe('asc');
    expect(olderUrl.searchParams.get('until')).toBe('2026-07-02T10:00:00Z');
    expect(olderUrl.searchParams.get('direction')).toBe('desc');
    expect(context.rows.map(row => row.id)).toEqual(['newer', 'selected', 'older']);
  });
});

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}
