import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConversationalReadiness, HomeSummaryPayload } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { HomePage } from './HomePage';

const readiness: ConversationalReadiness = {
  schema: 'codex-usage-tracker-conversational-readiness-v1',
  state: 'ready',
  summary: 'Ready for local analysis.',
  next_action: null,
  configured_profile: 'core',
  runtime_version_matches: true,
  evidence: [],
};

const summary: HomeSummaryPayload = {
  schema: 'codex-usage-tracker-home-summary-v1',
  source_revision: 'generation:9',
  latest_refresh_at: '2026-07-21T11:30:00Z',
  latest_event_at: '2026-07-21T11:00:00Z',
  accounting: { physical_rows: 8, canonical_rows: 7, excluded_copied_rows: 1 },
  usage_metrics: {
    calls: 219_508,
    input_tokens: 30_904_976_404,
    cached_input_tokens: 29_943_852_200,
    uncached_input_tokens: 961_124_204,
    output_tokens: 76_742_865,
    reasoning_output_tokens: 23_811_450,
    total_tokens: 30_981_719_269,
    estimated_cost_usd: 20_755.33,
    usage_credits: 760_510.88,
    pricing_coverage: 1,
    credit_coverage: 1,
    source_generation: 121,
    materialized_calls: 219_698,
  },
  pricing: { configured: true, model_count: 2, estimated_model_count: 0 },
  allowance: {
    configured: false,
    error: null,
    observed_usage: { available: false, windows: [] },
    windows: [],
  },
  findings: Array.from({ length: 4 }, (_, index) => ({
    finding_id: `finding-${index}`,
    confidence: 'high',
    title: `Finding ${index}`,
    summary: `Evidence summary ${index}`,
    action: `Action ${index}`,
    follow_up_prompt: `Investigate finding ${index}`,
    evidence: { kind: 'call', record_id: `record-${index}` },
  })),
  recent_evidence: Array.from({ length: 7 }, (_, index) => ({
    kind: 'call',
    evidence_id: `record-${index}`,
    label: `Thread ${index}`,
    detail: 'gpt-5 · 1,000 tokens',
    observed_at: `2026-07-21T0${index}:00:00Z`,
    record_id: `record-${index}`,
  })),
};

function renderHome(element: ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      {element}
    </QueryClientProvider>,
  );
}

describe('HomePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders bounded status, findings, and evidence without legacy dashboard modules', () => {
    renderHome(
      <HomePage
        model={fixtureModel}
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Usage pulse')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Selected scope usage metrics' })).toBeInTheDocument();
    expect(screen.getByText('Total Calls')).toBeInTheDocument();
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('Cache Reuse')).toBeInTheDocument();
    expect(screen.getByText('Estimated Cost')).toBeInTheDocument();
    expect(screen.getByText('219,508')).toBeInTheDocument();
    expect(screen.getByText('30.98B')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Recent findings' })).getAllByRole('article')).toHaveLength(3);
    expect(screen.queryByRole('region', { name: 'Home status' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Recent evidence' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Usage Constellation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Report library/i)).not.toBeInTheDocument();
  });

  it.each([
    {
      name: 'all-time payload changing to Recent',
      payload: {
        api_token: 'scope-token',
        load_window: 'all' as const,
        history_scope: 'active',
        limit: 500,
      },
      historyScope: 'active' as const,
      loadLimit: 500,
    },
    {
      name: 'active payload changing to all history',
      payload: {
        api_token: 'scope-token',
        load_window: 'rows' as const,
        history_scope: 'active',
        limit: 500,
      },
      historyScope: 'all' as const,
      loadLimit: 500,
    },
    {
      name: 'embedded payload changing row limit',
      payload: {
        api_token: 'scope-token',
        load_window: 'rows' as const,
        history_scope: 'active',
        limit: 500,
      },
      historyScope: 'active' as const,
      loadLimit: 1_000,
    },
  ])('queries v2 instead of reusing stale metrics for $name', async ({
    payload,
    historyScope,
    loadLimit,
  }) => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'codex-usage-tracker.query.v2',
        rows: [],
        next_cursor: null,
      }),
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    renderHome(
      <HomePage
        model={fixtureModel}
        payload={payload}
        summary={summary}
        readiness={readiness}
        historyScope={historyScope}
        loadWindow="rows"
        loadLimit={loadLimit}
        scopeSince={null}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(request).toMatchObject({
      entity: 'call',
      history: historyScope,
      limit: Math.min(200, loadLimit),
    });
  });

  it('offers setup guidance, copyable prompts, refresh, and contextual evidence', async () => {
    const onRefresh = vi.fn();
    const onOpenCall = vi.fn();
    renderHome(
      <HomePage
        model={fixtureModel}
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing={false}
        onRefresh={onRefresh}
        onNavigate={vi.fn()}
        onOpenCall={onOpenCall}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Copy starter prompt' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Explore' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Limits' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ask Codex about your usage' })).toBeInTheDocument();
    expect(screen.getByText(/These prompts use the Codex Usage Tracker MCP or plugin/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText('How to enable the MCP or plugin'));
    expect(screen.getByText('codex-usage-tracker setup')).toBeInTheDocument();
    const promptRow = screen.getByRole('article', { name: 'Find the biggest usage drivers' });
    expect(within(promptRow).getByText(/What drove my Codex usage this week/i)).toBeInTheDocument();
    fireEvent.click(within(promptRow).getByRole('button', { name: 'Copy prompt' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('What drove my Codex usage this week'));
    expect(await screen.findByText('Prompt copied')).toBeInTheDocument();
    const subagentPrompt = screen.getByRole('article', { name: 'Review subagent usage' });
    expect(within(subagentPrompt).getByText(/Compare parent and subagent calls/i)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(subagentPrompt).getByRole('button', { name: 'Copy prompt' }));
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('Where did Codex use subagents'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Open evidence' })[0]);

    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenCall).toHaveBeenCalledWith('record-0');
  });

  it('shows Home loading progress and omits overview-card footnotes', () => {
    renderHome(
      <HomePage
        model={fixtureModel}
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing
        refreshProgressPercent={42}
        refreshProgressText="Refreshing local usage index"
        homeStatusLoading={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    expect(screen.getByRole('progressbar', { name: 'Refreshing local usage index' }))
      .toHaveAttribute('aria-valuenow', '42');
    expect(screen.queryByText('0 detailed rows available')).not.toBeInTheDocument();
    expect(screen.queryByText('reported token accounting')).not.toBeInTheDocument();
    expect(screen.queryByText('complete selected scope')).not.toBeInTheDocument();
  });

  it('copies each server-provided follow-up without generating finding text in React', async () => {
    renderHome(
      <HomePage
        model={fixtureModel}
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Copy follow-up' })[1]);
    expect(screen.getAllByRole('button', { name: 'Copy follow-up' })[1]).toHaveAttribute(
      'title',
      expect.stringContaining('paste into Codex'),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Investigate finding 1');
    expect(await screen.findByText('Follow-up copied')).toBeInTheDocument();
  });

  it('labels empty usage metrics as unavailable instead of measured zeroes', () => {
    renderHome(
      <HomePage
        model={{ ...fixtureModel, calls: [], scopeSummary: undefined }}
        payload={{ pricing_configured: true }}
        summary={{ ...summary, usage_metrics: null }}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    expect(screen.getByText('No input data')).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('No reported input tokens in this scope')).not.toBeInTheDocument();
    expect(screen.queryByText('No loaded calls have mapped cost rates')).not.toBeInTheDocument();
  });

  it('keeps cache evidence while marking unpriced calls unavailable', () => {
    const call = fixtureModel.calls[0]!;
    renderHome(
      <HomePage
        model={{
          ...fixtureModel,
          calls: [{
            ...call,
            cost: 0,
            standardCost: null,
            priorityCost: null,
            billingBasis: 'unknown',
            credits: 0,
          }],
          scopeSummary: undefined,
        }}
        payload={{ pricing_configured: true }}
        summary={{ ...summary, usage_metrics: null }}
        readiness={readiness}
        historyScope="active"
        loadWindow="all"
        loadLimit={500}
        scopeSince={null}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    expect(screen.queryByText('No input data')).not.toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('pricing coverage unavailable')).not.toBeInTheDocument();
  });
});
