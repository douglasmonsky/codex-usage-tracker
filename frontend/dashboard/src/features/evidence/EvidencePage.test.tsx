import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EvidenceApiError, loadEvidence, type EvidenceResult } from '../../api/evidence';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { EvidencePage } from './EvidencePage';

vi.mock('../../api/evidence', () => ({
  loadEvidence: vi.fn(),
  EvidenceApiError: class EvidenceApiError extends Error {
    constructor(message: string, readonly status: number, readonly code: string | null) {
      super(message);
    }
  },
}));

const mockedLoadEvidence = vi.mocked(loadEvidence);
const runtime = { apiToken: 'local-token', contextApiEnabled: false, fileMode: false };

function evidenceRecord(overrides: Record<string, unknown> = {}) {
  return {
    schema: 'codex-usage-tracker.evidence.v1',
    evidence_id: 'evidence-1',
    kind: 'call',
    label: 'Observed call evidence',
    selectors: { record_id: 'fixture-call-0' },
    metrics: { total_tokens: 2048, confidence: 'observed' },
    source_schema: 'canonical_usage.v2',
    dashboard_target: null,
    ...overrides,
  };
}

function evidence(overrides: Record<string, unknown> = {}): EvidenceResult {
  return {
    schema: 'codex-usage-tracker.evidence-result.v1',
    selector: { kind: 'thread', id: 'thread:alpha', section: 'summary' },
    records: [evidenceRecord({ kind: 'thread', label: 'Thread alpha' })],
    next_cursor: null,
    dashboard_target: {},
    subject: null,
    ...overrides,
  } as EvidenceResult;
}

function renderPage(search: string) {
  window.history.replaceState(null, '', `/${search}`);
  return render(
    <EvidencePage
      model={fixtureModel}
      contextRuntime={runtime}
      onContextApiEnabledChange={vi.fn()}
      onNavigateRecord={vi.fn()}
      onCopyCallLink={vi.fn()}
    />,
  );
}

describe('EvidencePage', () => {
  beforeEach(() => {
    mockedLoadEvidence.mockReset();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('reuses the Call Investigator with its explicit context controls', () => {
    renderPage('?view=evidence&kind=call&record=fixture-call-0');

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('Raw context gated')).toBeInTheDocument();
    expect(mockedLoadEvidence).not.toHaveBeenCalled();
  });

  it('renders a thread summary and its bounded first page of calls', async () => {
    mockedLoadEvidence
      .mockResolvedValueOnce(evidence())
      .mockResolvedValueOnce(evidence({
          schema: 'codex-usage-tracker.evidence-result.v1',
          selector: { kind: 'thread', id: 'thread:alpha', section: 'calls' },
          records: [evidenceRecord({ evidence_id: 'call-1', label: 'Call one' })],
          next_cursor: 'next-page',
          dashboard_target: {},
          subject: null,
      }));

    renderPage('?view=evidence&kind=thread&thread_key=thread%3Aalpha');

    expect(await screen.findByRole('heading', { name: 'Thread evidence' })).toBeInTheDocument();
    expect(screen.getByText('Thread alpha')).toBeInTheDocument();
    expect(await screen.findByText('Call one')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load more calls' })).toBeInTheDocument();
    expect(mockedLoadEvidence).toHaveBeenNthCalledWith(2, expect.objectContaining({
      kind: 'thread', selectorId: 'thread:alpha', section: 'calls', limit: 20,
    }), runtime);
  });

  it('renders persisted finding language, scope, confidence, limitations, and linked evidence', async () => {
    mockedLoadEvidence.mockResolvedValue(evidence({
        schema: 'codex-usage-tracker.evidence-result.v1',
        selector: { kind: 'finding', id: 'finding-3', section: 'summary', analysis_id: 'analysis-7' },
        records: [evidenceRecord({ label: 'Linked call 7' })],
        next_cursor: null,
        dashboard_target: {},
        subject: {
          finding_id: 'finding-3',
          title: 'Repeated cold starts',
          statement: 'Three observed calls reloaded the same workspace.',
          claim_type: 'observed-pattern',
          confidence: 'high',
          severity: 'medium',
          caveat_codes: ['bounded-history'],
          analysis_id: 'analysis-7',
        },
    }));

    renderPage('?view=evidence&kind=finding&analysis=analysis-7&finding=finding-3');

    expect(await screen.findByRole('heading', { name: 'Repeated cold starts' })).toBeInTheDocument();
    expect(screen.getByText('Three observed calls reloaded the same workspace.')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('bounded-history')).toBeInTheDocument();
    expect(screen.getByText('Linked call 7')).toBeInTheDocument();
  });

  it('renders an allowance transition only from persisted evidence facts', async () => {
    mockedLoadEvidence.mockResolvedValue(evidence({
        schema: 'codex-usage-tracker.evidence-result.v1',
        selector: { kind: 'allowance', id: 'interval-3', section: 'summary' },
        records: [evidenceRecord({
          kind: 'allowance_cycle',
          label: 'Weekly observed transition',
          metrics: { percent_delta: 8, credits_delta: 1200, quality_grade: 'A' },
        })],
        next_cursor: null,
        dashboard_target: {},
        subject: null,
    }));

    renderPage('?view=evidence&kind=allowance&analysis=allowance-7&evidence=interval-3');

    expect(await screen.findByRole('heading', { name: 'Allowance evidence' })).toBeInTheDocument();
    expect(screen.getByText('Weekly observed transition')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument();
    expect(screen.queryByText(/probably|likely/i)).not.toBeInTheDocument();
  });

  it('keeps malformed and stale links recoverable and supports canonical return navigation', async () => {
    renderPage('?view=evidence&kind=thread&thread_key=../unsafe');
    expect(screen.getByRole('heading', { name: 'Evidence unavailable' })).toBeInTheDocument();
    expect(mockedLoadEvidence).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Back to Explore' }));
    expect(new URL(window.location.href).searchParams.get('view')).toBe('explore');
  });

  it('renders a recoverable stale-link state without selector fallback', async () => {
    mockedLoadEvidence.mockRejectedValue(new EvidenceApiError(
      'thread evidence not found: thread:gone',
      404,
      'evidence_not_found',
    ));

    renderPage('?view=evidence&kind=thread&thread_key=thread%3Agone');

    expect(await screen.findByRole('heading', { name: 'Evidence unavailable' })).toBeInTheDocument();
    expect(screen.getByText(/saved evidence link is no longer available/i)).toBeInTheDocument();
    expect(mockedLoadEvidence).toHaveBeenCalledWith(expect.objectContaining({
      selectorId: 'thread:gone',
    }), runtime);
  });

  it('copies the normalized evidence URL', async () => {
    mockedLoadEvidence.mockResolvedValue(evidence());
    renderPage('?view=evidence&kind=thread&thread_key=thread%3Aalpha&analysis_id=compat');
    await screen.findByRole('heading', { name: 'Thread evidence' });

    fireEvent.click(screen.getByRole('button', { name: 'Copy evidence link' }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.not.stringContaining('analysis_id='),
    ));
  });
});
