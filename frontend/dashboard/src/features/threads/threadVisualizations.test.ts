import { describe, expect, it } from 'vitest';

import { buildThreads, usageRowToCall } from '../../api/client';
import { validateVisualizationSpec } from '../../visualization';
import { buildCacheFrontierSpec, buildThreadLifecycleSpec } from './threadVisualizations';

const calls = [
  usageRowToCall({ record_id: 'a', event_timestamp: '2026-07-10T10:00:00Z', thread_name: 'Thread A', input_tokens: 60_000, cached_input_tokens: 10_000, total_tokens: 62_000, context_window_percent: 0.7 }),
  usageRowToCall({ record_id: 'b', event_timestamp: '2026-07-10T11:00:00Z', thread_name: 'Thread A', input_tokens: 70_000, cached_input_tokens: 50_000, total_tokens: 74_000, context_window_percent: 0.84, previous_call_delta_seconds: 3_600 }),
];

describe('thread visualization specs', () => {
  it('builds valid cache frontier and lifecycle contracts', () => {
    const frontier = buildCacheFrontierSpec(buildThreads(calls), 'active', 'revision');
    const lifecycle = buildThreadLifecycleSpec(calls, 'Thread A', 'active', 'revision');

    expect(validateVisualizationSpec(frontier)).toEqual([]);
    expect(validateVisualizationSpec(lifecycle)).toEqual([]);
    expect(frontier.data.rows[0]).toMatchObject({ thread: 'Thread A' });
    expect(lifecycle.data.rows[1]).toMatchObject({ event: 'Cold resume', contextPercent: 84 });
  });
});
