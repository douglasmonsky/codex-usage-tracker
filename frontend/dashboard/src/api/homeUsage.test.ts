import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadHomeUsageMetrics } from './homeUsage';

describe('loadHomeUsageMetrics', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('pages the focused v2 query when Recent spans more than one page', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([
        row(100, 60, 20, 10, 2),
        row(200, 120, 40, 20, 4),
      ], 'next-page'))
      .mockResolvedValueOnce(response([
        row(300, 180, 60, 30, 6),
      ], null));
    vi.stubGlobal('fetch', fetchMock);

    const metrics = await loadHomeUsageMetrics(
      { api_token: 'local-token' },
      {
        historyScope: 'active',
        loadWindow: 'rows',
        loadLimit: 3,
        since: null,
      },
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const firstRequest = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    const secondRequest = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(firstRequest).toMatchObject({
      entity: 'call',
      history: 'active',
      order_by: 'time',
      order: 'desc',
      limit: 3,
    });
    expect(secondRequest).toMatchObject({ cursor: 'next-page', limit: 1 });
    expect(metrics).toMatchObject({
      calls: 3,
      totalTokens: 600,
      cachedInputTokens: 360,
      uncachedInputTokens: 120,
      outputTokens: 60,
      reasoningOutputTokens: 30,
      estimatedCostUsd: 12,
      estimatedCredits: 6,
      hasPricingCoverage: true,
    });
  });

  it('pages grouped model metrics until the v2 cursor is exhausted', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([
        { ...row(100, 60, 20, 10, 2), model: 'gpt-a', call_count: 2 },
      ], 'next-model-page'))
      .mockResolvedValueOnce(response([
        { ...row(300, 180, 60, 30, 6), model: 'gpt-b', call_count: 3 },
      ], null));
    vi.stubGlobal('fetch', fetchMock);

    const metrics = await loadHomeUsageMetrics(
      { api_token: 'local-token' },
      {
        historyScope: 'all',
        loadWindow: 'week',
        loadLimit: 500,
        since: '2026-07-16T00:00:00Z',
      },
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const secondRequest = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(secondRequest).toMatchObject({
      entity: 'model',
      cursor: 'next-model-page',
      history: 'all',
      limit: 200,
    });
    expect(metrics).toMatchObject({
      calls: 5,
      totalTokens: 400,
      estimatedCostUsd: 8,
    });
  });
});

function row(
  tokens: number,
  cached: number,
  uncached: number,
  output: number,
  cost: number,
) {
  return {
    record_id: `call-${tokens}`,
    tokens,
    cached_tokens: cached,
    uncached_tokens: uncached,
    output_tokens: output,
    reasoning_tokens: output / 2,
    estimated_cost: cost,
    estimated_cost_coverage: 1,
    estimated_credits: cost / 2,
  };
}

function response(rows: object[], nextCursor: string | null): Response {
  return {
    ok: true,
    json: async () => ({
      schema: 'codex-usage-tracker.query.v2',
      rows,
      next_cursor: nextCursor,
    }),
  } as Response;
}
