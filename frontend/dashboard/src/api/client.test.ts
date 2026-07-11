import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadUsagePayload, modelFromBootPayload } from './client';
import type { DashboardBootPayload } from './types';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('dashboard API model builder', () => {
  it('derives model cost bars from live aggregate rows', () => {
    const payload: DashboardBootPayload = {
      loaded_row_count: 3,
      total_available_rows: 3,
      rows: [
        {
          record_id: 'cost-1',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'thread-a',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 100,
          cached_input_tokens: 5,
          output_tokens: 26_000,
          total_tokens: 26_100,
          estimated_cost_usd: 0.35,
          usage_credits: 9,
        },
        {
          record_id: 'cost-2',
          call_started_at: '2026-07-02T11:00:00Z',
          thread_name: 'thread-b',
          model: 'o3',
          effort: 'low',
          input_tokens: 80,
          cached_input_tokens: 20,
          output_tokens: 20,
          total_tokens: 100,
          estimated_cost_usd: 0.25,
          usage_credits: 6,
        },
        {
          record_id: 'cost-3',
          call_started_at: '2026-07-03T10:00:00Z',
          thread_name: 'thread-a',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 60,
          cached_input_tokens: 0,
          output_tokens: 10,
          total_tokens: 70,
          estimated_cost_usd: 0.15,
          usage_credits: 4,
        },
      ],
    };

    const model = modelFromBootPayload(payload);
    expect(model.modelCosts).toEqual([
      expect.objectContaining({ label: 'codex-1', value: 0.5 }),
      expect.objectContaining({ label: 'o3', value: 0.25 }),
    ]);
    expect(model.findings.map(finding => finding.title)).toEqual([
      'Cache Misses (Large Inputs)',
      'Long Thread: thread-a',
      'High Model Effort',
      'Tool Output Volume',
    ]);
    expect(model.findings[0]).toEqual(expect.objectContaining({ rank: 1, severity: 'High' }));
    expect(model.reports).toEqual([
      expect.objectContaining({ title: 'Cost Curves', status: 'Ready', owner: 'Threads' }),
      expect.objectContaining({ title: 'Usage Drain Model', status: 'Ready', owner: 'Reports' }),
      expect.objectContaining({ title: 'Fast Mode Proxy', status: 'Ready', owner: 'Calls' }),
    ]);
  });

  it('keeps event timestamp distinct from call start timestamp', () => {
    const payload: DashboardBootPayload = {
      loaded_row_count: 1,
      total_available_rows: 1,
      rows: [
        {
          record_id: 'timestamp-1',
          event_timestamp: '2026-07-02T10:04:30Z',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'thread-a',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 100,
          cached_input_tokens: 5,
          output_tokens: 10,
          total_tokens: 110,
        },
      ],
    };

    const [call] = modelFromBootPayload(payload).calls;

    expect(call).toEqual(
      expect.objectContaining({
        eventTimestamp: '2026-07-02T10:04:30Z',
        rawTime: '2026-07-02T10:04:30Z',
        callStartedAt: '2026-07-02T10:00:00Z',
      }),
    );
  });

  it('keeps loaded-row cards while preserving the complete scope summary', () => {
    const payload: DashboardBootPayload = {
      load_window: 'all',
      loaded_row_count: 2,
      total_available_rows: 500,
      summary: {
        visible_calls: 500,
        total_tokens: 999_999,
      },
      rows: [
        {
          record_id: 'loaded-card-a',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'thread-a',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1_000,
          cached_input_tokens: 400,
          output_tokens: 250,
          reasoning_output_tokens: 75,
          total_tokens: 1_325,
        },
        {
          record_id: 'loaded-card-b',
          call_started_at: '2026-07-02T11:00:00Z',
          thread_name: 'thread-b',
          model: 'codex-1',
          effort: 'medium',
          input_tokens: 500,
          cached_input_tokens: 100,
          output_tokens: 125,
          reasoning_output_tokens: 25,
          total_tokens: 650,
        },
      ],
    };

    const model = modelFromBootPayload(payload);
    expect(model.scopeSummary).toEqual(
      expect.objectContaining({
        visibleCalls: 500,
        totalTokens: 999_999,
      }),
    );
    expect(model.cards.find(card => card.label === 'Total Calls')).toEqual(
      expect.objectContaining({
        value: '2',
        detail: 'loaded calls in this dashboard',
      }),
    );
    expect(model.cards.find(card => card.label === 'Total Tokens')).toEqual(
      expect.objectContaining({
        value: '1.98K',
        breakdown: [
          { label: 'Cached', value: '500' },
          { label: 'Uncached', value: '1K' },
          { label: 'Output', value: '375' },
          { label: 'Reasoning', value: '100' },
        ],
      }),
    );
    expect(modelFromBootPayload({ ...payload, load_window: 'rows' }).scopeSummary).toBeUndefined();
  });

  it('builds usage drain series from loaded rows', () => {
    const payload: DashboardBootPayload = {
      loaded_row_count: 2,
      total_available_rows: 2,
      rows: [
        {
          record_id: 'drain-a',
          event_timestamp: '2026-07-01T10:00:00Z',
          call_started_at: '2026-07-01T10:00:00Z',
          thread_name: 'thread-a',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1_000,
          cached_input_tokens: 400,
          output_tokens: 250,
          total_tokens: 1_250,
          usage_credits: 25,
          rate_limit_plan_type: 'pro',
          rate_limit_secondary_used_percent: 60,
          rate_limit_secondary_resets_at: 1_783_707_267,
        },
        {
          record_id: 'drain-b',
          event_timestamp: '2026-07-02T10:00:00Z',
          call_started_at: '2026-07-02T10:00:00Z',
          thread_name: 'thread-b',
          model: 'codex-1',
          effort: 'medium',
          input_tokens: 500,
          cached_input_tokens: 100,
          output_tokens: 125,
          total_tokens: 625,
          usage_credits: 75,
          rate_limit_plan_type: 'pro',
          rate_limit_secondary_used_percent: 65,
          rate_limit_secondary_resets_at: 1_783_707_267,
        },
      ],
    };

    const model = modelFromBootPayload(payload);

    expect(model.actualVsPredictedSeries).toHaveLength(2);
    expect(model.actualVsPredictedSeries[0].points.map(point => point.value)).toEqual([25, 100]);
    expect(model.usageRemainingSeries[0].points.map(point => point.value)).toEqual([40, 35]);
    expect(model.weeklyWindows).toEqual([
      expect.objectContaining({
        plan: 'pro',
        observedPct: 65,
        credits: 100,
      }),
    ]);
    expect(model.weeklyCreditSeries[0].points[0]).toEqual(
      expect.objectContaining({
        value: expect.any(Number),
        low: expect.any(Number),
        high: expect.any(Number),
      }),
    );
  });
});

describe('dashboard live usage client', () => {
  it('loads a bounded evidence sample for time windows', async () => {
    const progress = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url).toContain('limit=500');
      expect(url).toContain('load_window=week');
      expect(url).toContain('since=2026-07-04T10%3A15%3A00.000Z');
      return jsonResponse({
        api_token: 'token',
        load_window: 'week',
        since: '2026-07-04T10:15:00.000Z',
        loaded_row_count: 2,
        total_available_rows: 3,
        limit: 500,
        has_more: true,
        rows: [
          { record_id: 'recent-week-row-1', total_tokens: 1 },
          { record_id: 'recent-week-row-2', total_tokens: 2 },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const payload = await loadUsagePayload(
      { api_token: 'token', loaded_row_count: 500, rows: [] },
      {
        refresh: false,
        limit: 0,
        loadWindow: 'week',
        since: '2026-07-04T10:15:00.000Z',
        onProgress: progress,
      },
    );

    expect(payload.load_window).toBe('week');
    expect(payload.rows).toHaveLength(2);
    expect(payload.limit).toBe(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(progress).toHaveBeenCalledWith(
      expect.objectContaining({ phase: 'loading_rows', completed: 2, total: 3, percent: 100 }),
    );
  });

  it('polls async refresh jobs before loading usage rows', async () => {
    const progress = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/refresh/start')) {
        return jsonResponse({ job_id: 'job-1', status: 'running', percent: 0 });
      }
      if (url.includes('/api/refresh/status')) {
        return jsonResponse({
          job_id: 'job-1',
          status: 'completed',
          phase: 'finalizing',
          percent: 100,
        });
      }
      if (url.includes('/api/usage?')) {
        return jsonResponse({
          api_token: 'token',
          refresh_jobs_available: true,
          loaded_row_count: 0,
          total_available_rows: 0,
          limit: 500,
          rows: [],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const payload = await loadUsagePayload(
      {
        api_token: 'token',
        refresh_jobs_available: true,
        limit: 500,
        loaded_row_count: 0,
        rows: [],
      },
      { refresh: true, onProgress: progress },
    );

    expect(payload.loaded_row_count).toBe(0);
    expect(fetchMock.mock.calls.map(call => String(call[0]))).toEqual([
      expect.stringContaining('/api/refresh/start?'),
      expect.stringContaining('/api/refresh/status?'),
      expect.stringContaining('/api/usage?'),
    ]);
    expect(String(fetchMock.mock.calls[2][0])).toContain('refresh=0');
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ status: 'running' }));
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ status: 'completed', percent: 100 }));
  });

  it('loads uncapped usage rows in finite pages', async () => {
    const progress = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('offset=10000')) {
        return jsonResponse({
          api_token: 'token',
          loaded_row_count: 1,
          total_available_rows: 10001,
          limit: 10000,
          has_more: false,
          rows: [{ record_id: 'row-b', total_tokens: 2 }],
        });
      }
      return jsonResponse({
        api_token: 'token',
        loaded_row_count: 10000,
        total_available_rows: 10001,
        limit: 10000,
        has_more: true,
        rows: Array.from({ length: 10000 }, (_, index) => ({
          record_id: `row-a-${index}`,
          total_tokens: 1,
        })),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const payload = await loadUsagePayload(
      {
        api_token: 'token',
        loaded_row_count: 500,
        total_available_rows: 10001,
        rows: [],
      },
      { refresh: false, limit: 0, onProgress: progress },
    );

    expect(payload.rows).toHaveLength(10001);
    expect(payload.loaded_row_count).toBe(10001);
    expect(payload.limit).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toContain('limit=10000');
    expect(String(fetchMock.mock.calls[1][0])).toContain('offset=10000');
    expect(progress).toHaveBeenCalledWith(
      expect.objectContaining({ phase: 'loading_rows', completed: 10000, total: 10001, percent: 99 }),
    );
    expect(progress).toHaveBeenCalledWith(
      expect.objectContaining({ phase: 'loading_rows', completed: 10001, total: 10001, percent: 100 }),
    );
  });
});

function jsonResponse(payload: Record<string, unknown>) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}
