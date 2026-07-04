import { describe, expect, it } from 'vitest';

import { modelFromBootPayload } from './client';
import type { DashboardBootPayload } from './types';

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
