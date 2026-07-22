import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DashboardBootPayload, HomeStatusPayload } from '../api/types';
import { useConversationalReadiness } from './useConversationalReadiness';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useConversationalReadiness', () => {
  it('loads deferred Home status immediately and reloads it after a dashboard refresh', async () => {
    let requestCount = 0;
    const fetchMock = vi.fn(async () => jsonResponse(homeStatus(`revision-${++requestCount}`)));
    vi.stubGlobal('fetch', fetchMock);
    const initialPayload: DashboardBootPayload = {
      api_token: 'test-token',
      context_api_enabled: true,
      shell_boot: true,
      readiness_deferred: true,
      home_summary_deferred: true,
    };

    const { result, rerender } = renderHook(
      ({ dashboardPayload }) => useConversationalReadiness(initialPayload, dashboardPayload),
      { initialProps: { dashboardPayload: initialPayload } },
    );

    await waitFor(() => expect(result.current.homeSummary?.source_revision).toBe('revision-1'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/status?include_archived=false',
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Codex-Usage-Token': 'test-token' }),
      }),
    );

    rerender({ dashboardPayload: { ...initialPayload, loaded_row_count: 1 } });

    await waitFor(() => expect(result.current.homeSummary?.source_revision).toBe('revision-2'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function homeStatus(sourceRevision: string): HomeStatusPayload {
  return {
    schema: 'codex-usage-tracker-status-v1',
    conversational_analysis: {
      schema: 'codex-usage-tracker-conversational-readiness-v1',
      state: 'ready',
      summary: 'MCP ready',
      next_action: null,
      evidence: [],
    },
    home_summary: {
      schema: 'codex-usage-tracker-home-summary-v1',
      source_revision: sourceRevision,
      latest_refresh_at: null,
      latest_event_at: null,
      accounting: {
        physical_rows: 1,
        canonical_rows: 1,
        excluded_copied_rows: 0,
      },
      pricing: { configured: false, model_count: 0, estimated_model_count: 0 },
      allowance: {
        configured: false,
        error: null,
        observed_usage: { available: false, windows: [] },
        windows: [],
      },
      findings: [],
      recent_evidence: [],
    },
  };
}

function jsonResponse(payload: HomeStatusPayload): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}
