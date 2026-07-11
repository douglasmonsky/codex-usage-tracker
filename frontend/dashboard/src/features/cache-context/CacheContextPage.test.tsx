import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { CacheContextPage } from './CacheContextPage';

afterEach(() => vi.unstubAllGlobals());

describe('Cache and Context focused evidence', () => {
  it('uses full-scope summaries, threads, and selected thread calls', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/summary?')) return jsonResponse({
        schema: 'codex-usage-tracker-summary-v1',
        group_by: 'date',
        include_archived: false,
        privacy_mode: 'normal',
        rows: [{
          group_key: '2026-07-11', model_calls: 1200, sessions: 30, turns: 1200,
          input_tokens: 10_000, cached_input_tokens: 8_000, uncached_input_tokens: 2_000,
          output_tokens: 500, reasoning_output_tokens: 100, total_tokens: 10_600,
          avg_cache_ratio: 0.8, latest_event: '2026-07-11T12:00:00Z',
        }],
      });
      if (url.startsWith('/api/recommendations?')) return jsonResponse({
        schema: 'codex-usage-tracker-recommendations-v1', filters: { include_archived: false },
        row_count: 0, total_matched_rows: 0, truncated: false, rows: [],
      });
      if (url.startsWith('/api/threads?')) return jsonResponse({
        schema: 'codex-usage-tracker-threads-v1', include_archived: false,
        row_count: 1, total_matched_rows: 1, limit: 250, offset: 0, has_more: false,
        rows: [{
          thread_key: 'scope-key', thread_label: 'scope-thread',
          first_event_timestamp: '2026-07-10T10:00:00Z', latest_event_timestamp: '2026-07-11T12:00:00Z',
          latest_record_id: 'scope-call', call_count: 12, session_count: 1,
          input_tokens: 10_000, cached_input_tokens: 8_000, uncached_input_tokens: 2_000,
          output_tokens: 500, reasoning_output_tokens: 100, total_tokens: 10_600,
          estimated_cost_usd: 1.25, usage_credits: 4.5, avg_cache_ratio: 0.8,
          max_context_window_percent: 0.5, max_recommendation_score: 0.2,
          primary_recommendation: 'Keep the thread warm', initiator_summary: 'user',
          archived_call_count: 0, updated_at: '2026-07-11T12:00:00Z',
        }],
      });
      if (url.startsWith('/api/thread-calls?')) return jsonResponse({
        schema: 'codex-usage-tracker-thread-calls-v1', thread_key: 'scope-key',
        row_count: 1, total_matched_rows: 1, limit: null, offset: 0, has_more: false,
        rows: [{
          record_id: 'scope-call', call_started_at: '2026-07-11T12:00:00Z',
          thread_name: 'scope-thread', model: 'codex-1', effort: 'high',
          input_tokens: 1000, cached_input_tokens: 800, output_tokens: 50, total_tokens: 1050,
        }],
      });
      throw new Error(`Unexpected request: ${url}`);
    }));

    render(
      <QueryClientProvider client={createDashboardQueryClient()}>
        <CacheContextPage
          model={fixtureModel}
          contextRuntime={{ ...fixtureModel.contextRuntime, apiToken: 'local-token', fileMode: false }}
          includeArchived={false}
          focusedEndpointsEnabled
          sourceRevision="revision-1"
          onOpenInvestigator={vi.fn()}
          onCopyCallLink={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('progressbar', { name: 'Loading cache and context evidence' })).toBeInTheDocument();
    expect((await screen.findAllByText('scope-thread')).length).toBeGreaterThan(0);
    expect(screen.getByText('1,200')).toBeInTheDocument();
    expect(screen.getAllByText('80.0%').length).toBeGreaterThan(0);
    expect(await screen.findByText('1 loaded')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('progressbar', { name: 'Loading cache and context evidence' })).not.toBeInTheDocument());
  });
});

function jsonResponse(payload: unknown): Response {
  return { ok: true, json: async () => payload } as Response;
}
