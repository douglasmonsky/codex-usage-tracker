import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CompressionApiPayload } from '../../api/compressionLab';
import { createDashboardQueryClient } from '../../data/queryRuntime';
import { CompressionLabPage } from './CompressionLabPage';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Compression Lab workspace', () => {
  it('renders a cached shared profile as an overlap-aware savings portfolio', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(profilePayload())));

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Compression Lab' })).toBeInTheDocument();
    expect(await screen.findByText('1.2M')).toBeInTheDocument();
    expect(screen.getByText('240K')).toBeInTheDocument();
    expect(screen.getByText('120K to 360K')).toBeInTheDocument();
    expect(screen.getByText('Not included')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Compression opportunity families' })).toBeInTheDocument();
    expect(screen.getByText('Stale Context')).toBeInTheDocument();
    expect(screen.getAllByText('Exact warm profile')).toHaveLength(2);
    expect(screen.getByText('Savings are heuristic ranges, not an OpenAI usage ledger.')).toBeInTheDocument();
  });

  it('starts a missing profile explicitly and shows detector progress before publication', async () => {
    let resolveStatus!: (response: Response) => void;
    const statusResponse = new Promise<Response>(resolve => {
      resolveStatus = resolve;
    });
    let profileReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/compression/profile?')) {
        profileReads += 1;
        return profileReads === 1
          ? jsonResponse(missingPayload(), 404)
          : jsonResponse(profilePayload());
      }
      if (url.startsWith('/api/compression/start?')) return jsonResponse(statusPayload('running', 25));
      if (url.startsWith('/api/compression/status?')) return statusResponse;
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    await screen.findByText('No analysis for this scope yet');
    fireEvent.click(screen.getByRole('button', { name: 'Analyze usage' }));

    const progress = await screen.findByRole('progressbar', { name: 'Compression analysis progress' });
    expect(progress).toHaveAttribute('aria-valuenow', '25');
    expect(screen.getByText('Stale Context detector')).toBeInTheDocument();

    resolveStatus(jsonResponse(statusPayload('completed', 100)));
    await waitFor(() => expect(screen.getByText('240K')).toBeInTheDocument());
    expect(screen.queryByRole('progressbar', { name: 'Compression analysis progress' })).not.toBeInTheDocument();
  });

  it('aborts only the browser observer when navigation leaves an active server job', async () => {
    let runSignal: AbortSignal | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith('/api/compression/profile?')) return jsonResponse(missingPayload(), 404);
      if (url.startsWith('/api/compression/start?')) {
        runSignal = init?.signal ?? undefined;
        return jsonResponse(statusPayload('running', 25));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const page = renderPage();
    await screen.findByText('No analysis for this scope yet');
    fireEvent.click(screen.getByRole('button', { name: 'Analyze usage' }));
    await waitFor(() => expect(runSignal).toBeDefined());

    page.unmount();

    expect(runSignal?.aborted).toBe(true);
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/compression/cancel'),
      expect.anything(),
    );
  });
});

function renderPage() {
  const client = createDashboardQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <CompressionLabPage
        contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
        includeArchived={false}
        since={null}
        sourceKey="fixture-source"
        sourceRevision="revision-1"
      />
    </QueryClientProvider>,
  );
}

function profilePayload(): CompressionApiPayload {
  return {
    ...statusPayload('completed', 100),
    kind: 'profile',
    cache: { reused: true, mode: 'exact', request_reused: 'completed' },
    caveats: ['Savings are heuristic ranges, not an OpenAI usage ledger.'],
    profile: {
      candidate_count: 7,
      observed_exposure: { total: 1_200_000 },
      portfolio_estimate: { low: 120_000, likely: 240_000, high: 360_000 },
      families: [{
        family: 'stale_context',
        candidate_count: 4,
        adjusted_estimate: { low: 80_000, likely: 160_000, high: 240_000 },
      }],
      coverage: { call_count: 500, content_index_enabled: false },
      cache: { mode: 'exact', reused: true },
      duration_ms: 3,
      content_mode: 'aggregate',
      includes_indexed_content: false,
      includes_raw_fragments: false,
      warnings: [],
      caveats: ['Savings are heuristic ranges, not an OpenAI usage ledger.'],
    },
  };
}

function missingPayload(): CompressionApiPayload {
  return {
    ...statusPayload('error', 0),
    kind: 'profile',
    run_id: null,
    error: { code: 'compression_run_not_found', message: 'No profile.' },
  };
}

function statusPayload(status: 'running' | 'completed' | 'error', percent: number): CompressionApiPayload {
  return {
    schema: 'codex-usage-tracker-compression-api-v1',
    kind: 'status',
    run_id: 'compression-1',
    status,
    source_revision: 'generation:5',
    scope: { include_archived: false },
    coverage: {},
    cache: { reused: false, mode: null, request_reused: 'none' },
    progress: {
      percent,
      stage: status === 'completed' ? 'completed' : 'detectors',
      current_detector: status === 'running' ? 'stale_context' : null,
      completed_detectors: status === 'completed' ? 6 : 1,
      total_detectors: 6,
      records_examined: 500,
      candidate_count: 7,
    },
    error: null,
    next: status === 'running'
      ? { tool: 'usage_compression_status', arguments: { run_id: 'compression-1' }, poll_after_ms: 250 }
      : { tool: 'usage_compression_profile', arguments: { run_id: 'compression-1' } },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}
