import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConversationalReadiness, HomeSummaryPayload } from '../../api/types';
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

describe('HomePage', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders bounded status, findings, and evidence without legacy dashboard modules', () => {
    render(
      <HomePage
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Home status' })).getAllByRole('article')).toHaveLength(5);
    expect(within(screen.getByRole('region', { name: 'Recent findings' })).getAllByRole('article')).toHaveLength(3);
    expect(within(screen.getByRole('region', { name: 'Recent evidence' })).getAllByRole('listitem')).toHaveLength(5);
    expect(screen.queryByText(/Usage Constellation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Report library/i)).not.toBeInTheDocument();
  });

  it('supports the four primary Home actions and contextual evidence launch', async () => {
    const onRefresh = vi.fn();
    const onNavigate = vi.fn();
    const onOpenCall = vi.fn();
    render(
      <HomePage
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        refreshing={false}
        onRefresh={onRefresh}
        onNavigate={onNavigate}
        onOpenCall={onOpenCall}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Copy starter prompt' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('usage'));
    expect(await screen.findByText('Starter prompt copied')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open Explore' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open Limits' }));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Home' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Open evidence' })[0]);

    expect(onNavigate).toHaveBeenNthCalledWith(1, 'explore');
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'limits');
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenCall).toHaveBeenCalledWith('record-0');
  });

  it('copies each server-provided follow-up without generating finding text in React', async () => {
    render(
      <HomePage
        payload={{ pricing_configured: true }}
        summary={summary}
        readiness={readiness}
        refreshing={false}
        onRefresh={vi.fn()}
        onNavigate={vi.fn()}
        onOpenCall={vi.fn()}
      />,
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Copy follow-up' })[1]);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Investigate finding 1');
    expect(await screen.findByText('Follow-up copied')).toBeInTheDocument();
  });
});
