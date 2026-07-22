import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createDashboardQueryClient } from '../../data/queryRuntime';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { DiagnosticsPage } from './DiagnosticsPage';

describe('DiagnosticsPage query lifecycle', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps completed snapshot modules and retries only interrupted work on return', async () => {
    const requestCounts = new Map<string, number>();
    let interruptedCommands = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const path = new URL(url, 'http://local.test').pathname;
      requestCounts.set(path, (requestCounts.get(path) ?? 0) + 1);

      if (path === '/api/diagnostics/facts' || path === '/api/diagnostics/tools' || path === '/api/diagnostics/compactions') {
        return Promise.resolve(jsonResponse({
          rows: [{ fact_type: 'cache', fact_name: 'large_uncached_input', associated_calls: 1 }],
          total_matched_rows: 1,
        }));
      }
      if (path === '/api/diagnostics/fact-calls') {
        return Promise.resolve(jsonResponse({ rows: [], total_matched_rows: 0 }));
      }
      if (path === '/api/diagnostics/commands' && requestCounts.get(path) === 1) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            interruptedCommands += 1;
            reject(new DOMException('Aborted', 'AbortError'));
          }, { once: true });
        });
      }
      return Promise.resolve(jsonResponse({
        status: 'ready',
        snapshot: { computed_at: '2026-07-14T02:00:00Z' },
      }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = createDashboardQueryClient();

    const first = renderDiagnostics(client);
    expect(screen.getByRole('note', { name: 'Feature maturity: Available during transition' })).toHaveTextContent(
      'usage_query(entity="call", measures=["tokens"]) → usage_evidence',
    );
    const modules = await screen.findByLabelText('Loading diagnostic snapshots modules');
    await waitFor(() => {
      expect(within(modules).getByText('Overview ready')).toBeInTheDocument();
      expect(within(modules).getByText('Commands loading')).toBeInTheDocument();
      expect(screen.getByRole('progressbar', { name: 'Loading diagnostic snapshots' })).toHaveAttribute('aria-valuenow', '9');
    });

    first.unmount();
    await waitFor(() => expect(interruptedCommands).toBe(1));

    renderDiagnostics(client);
    await screen.findByText('Live snapshots: 10');

    expect(requestCounts.get('/api/diagnostics/overview')).toBe(1);
    expect(requestCounts.get('/api/diagnostics/commands')).toBe(2);
    expect(requestCounts.get('/api/diagnostics/tool-output')).toBe(1);
  });

  it('loads only the selected diagnostic fact source', async () => {
    const requestCounts = new Map<string, number>();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = new URL(String(input), 'http://local.test').pathname;
      requestCounts.set(path, (requestCounts.get(path) ?? 0) + 1);
      if (path === '/api/diagnostics/facts' || path === '/api/diagnostics/tools') {
        return Promise.resolve(jsonResponse({
          rows: [{ fact_type: 'tool', fact_name: 'function_call', associated_calls: 1 }],
          total_matched_rows: 1,
        }));
      }
      if (path === '/api/diagnostics/fact-calls') {
        return Promise.resolve(jsonResponse({ rows: [], total_matched_rows: 0 }));
      }
      return Promise.resolve(jsonResponse({
        status: 'ready',
        snapshot: { computed_at: '2026-07-14T02:00:00Z' },
      }));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderDiagnostics(createDashboardQueryClient());
    await screen.findByText('Live facts: 1');

    expect(requestCounts.get('/api/diagnostics/facts')).toBe(1);
    expect(requestCounts.get('/api/diagnostics/tools')).toBeUndefined();

    fireEvent.click(screen.getByRole('tab', { name: /Tools/ }));
    await screen.findByText('Live tools: 1');

    expect(requestCounts.get('/api/diagnostics/tools')).toBe(1);
  });
});

function renderDiagnostics(client: ReturnType<typeof createDashboardQueryClient>) {
  return render(
    <QueryClientProvider client={client}>
      <DiagnosticsPage
        model={fixtureModel}
        contextRuntime={{ apiToken: 'local-token', contextApiEnabled: true, fileMode: false }}
        includeArchived
        sourceKey="fixture-source"
        sourceRevision="revision-1"
        rowLoadControls={{
          loadedRowCount: fixtureModel.calls.length,
          totalAvailableRows: fixtureModel.calls.length,
          canLoadMoreRows: false,
          canLoadAllRows: false,
          refreshing: false,
          onLoadMoreRows: vi.fn(),
          onLoadAllRows: vi.fn(),
        }}
        onOpenInvestigator={vi.fn()}
        onCopyCallLink={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: Record<string, unknown>): Response {
  return {
    ok: true,
    json: async () => payload,
  } as Response;
}
