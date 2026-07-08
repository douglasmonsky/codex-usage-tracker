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
});

describe('dashboard live usage client', () => {
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
});

function jsonResponse(payload: Record<string, unknown>) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}
