import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { diagnosticSnapshotDefinitions } from '../../api/diagnostics';
import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { InvestigatorPage } from './InvestigatorPage';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Investigator query lifecycle', () => {
  it('keeps credentials out of every registered query key', () => {
    const client = createDashboardQueryClient();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => responseFor(String(input))));

    renderInvestigator(client);

    const keys = client.getQueryCache().getAll().map(query => query.queryKey);
    expect(keys.length).toBe(diagnosticSnapshotDefinitions.length + 2);
    expect(JSON.stringify(keys)).not.toContain('private-investigator-token');
    expect(JSON.stringify(keys)).toContain('fixture-source');
    expect(keys.every(key => key[0] === 'dashboard')).toBe(true);
    const walkKey = keys.find(key => key[1] === 'investigator-walk');
    expect(walkKey).toContain('revision-1');
  });

  it('identifies every module while snapshots are still loading', async () => {
    const client = createDashboardQueryClient();
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/investigations/agentic?')) {
        return Promise.resolve(responseFor(url));
      }
      return new Promise<Response>(() => undefined);
    }));

    const view = renderInvestigator(client);

    expect(await screen.findByText('Investigation report ready')).toBeInTheDocument();
    for (const definition of diagnosticSnapshotDefinitions) {
      expect(screen.getByText(`${definition.title} loading`)).toBeInTheDocument();
    }
    expect(screen.getByRole('progressbar', { name: 'Loading investigation evidence' }))
      .toHaveAttribute('aria-valuenow', '1');
    view.unmount();
  });

  it('names the terminal module that failed without hiding the page', async () => {
    const client = createDashboardQueryClient();
    client.setDefaultOptions({ queries: { retryDelay: 0 } });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/diagnostics/commands?')) {
        return {
          ok: false,
          status: 503,
          json: async () => ({}),
        } as Response;
      }
      return responseFor(url);
    }));

    renderInvestigator(client);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Commands unavailable: Commands request failed with HTTP 503',
    );
    expect(screen.getByRole('heading', { name: 'Ranked findings' })).toBeInTheDocument();
  });

  it('shows granular diagnostic progress while refreshing evidence', async () => {
    const client = createDashboardQueryClient();
    let resolveRefreshStatus!: (response: Response) => void;
    const refreshStatus = new Promise<Response>(resolve => {
      resolveRefreshStatus = resolve;
    });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/diagnostics/refresh?')) {
        return jsonResponse(refreshJob('running', 3));
      }
      if (url.startsWith('/api/diagnostics/refresh/status?')) {
        return refreshStatus;
      }
      return responseFor(url);
    }));

    renderInvestigator(client);
    await screen.findByText('10 diagnostic modules');
    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));

    const progress = await screen.findByRole('progressbar', { name: 'Refreshing investigation evidence' });
    expect(progress).toHaveAttribute('aria-valuenow', '3');
    expect(progress).toHaveAttribute('aria-valuemax', '10');

    resolveRefreshStatus(jsonResponse(refreshJob('completed', 10)));
    expect(await screen.findByText(/Live evidence refreshed/)).toBeInTheDocument();
  });
});

function renderInvestigator(client: ReturnType<typeof createDashboardQueryClient>) {
  return render(
    <QueryClientProvider client={client}>
      <InvestigatorPage
        model={fixtureModel}
        contextRuntime={{
          apiToken: 'private-investigator-token',
          contextApiEnabled: true,
          fileMode: false,
        }}
        includeArchived={false}
        sourceKey="fixture-source"
        sourceRevision="revision-1"
        onOpenInvestigator={vi.fn()}
        onCopyCallLink={vi.fn()}
        onNavigateView={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function responseFor(url: string): Response {
  if (url.startsWith('/api/investigations/agentic?')) {
    return jsonResponse({
      schema: 'codex-usage-tracker-agentic-investigation-v1',
      content_mode: 'aggregate_investigation',
      includes_indexed_content: false,
      includes_raw_fragments: false,
      privacy_mode: 'normal',
      goal: 'token_waste',
      filters: {},
      summary: {
        finding_count: 0,
        top_finding: null,
        confidence: 'low',
        source_reports: [],
      },
      findings: [],
      recommended_next_tools: [],
      caveats: [],
    });
  }
  return jsonResponse({ status: 'ready' });
}

function jsonResponse(payload: unknown): Response {
  return { ok: true, json: async () => payload } as Response;
}

function refreshJob(status: 'running' | 'completed', completed: number) {
  return {
    schema: 'codex-usage-tracker-analysis-job-v1',
    job_id: 'investigator-refresh-test',
    job_kind: 'diagnostic-refresh',
    status,
    stage: status === 'completed' ? 'complete' : 'persisting_snapshots',
    progress: {
      completed_units: completed,
      total_units: 10,
      percent: completed * 10,
      current_unit: status === 'completed' ? null : 'commands',
    },
    error: null,
    next: status === 'completed'
      ? { action: 'reload_persisted_results' }
      : { action: 'poll', job_id: 'investigator-refresh-test', poll_after_ms: 0 },
  };
}
