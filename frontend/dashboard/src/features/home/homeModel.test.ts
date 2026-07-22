import { describe, expect, it } from 'vitest';

import type {
  ConversationalReadiness,
  DashboardBootPayload,
  HomeSummaryPayload,
} from '../../api/types';
import { buildHomeModel } from './homeModel';

const now = new Date('2026-07-21T12:00:00Z');

function readiness(
  state: ConversationalReadiness['state'] = 'ready',
): ConversationalReadiness {
  return {
    schema: 'codex-usage-tracker-conversational-readiness-v1',
    state,
    summary: `${state} summary`,
    next_action: null,
    configured_profile: 'core',
    runtime_version_matches: state === 'ready',
    evidence: [],
  };
}

function summary(overrides: Partial<HomeSummaryPayload> = {}): HomeSummaryPayload {
  return {
    schema: 'codex-usage-tracker-home-summary-v1',
    source_revision: 'generation:7',
    latest_refresh_at: '2026-07-21T11:30:00Z',
    latest_event_at: '2026-07-21T11:00:00Z',
    accounting: {
      physical_rows: 12,
      canonical_rows: 10,
      excluded_copied_rows: 2,
    },
    pricing: {
      configured: true,
      model_count: 4,
      estimated_model_count: 0,
    },
    allowance: {
      configured: false,
      error: null,
      observed_usage: { available: false, windows: [] },
      windows: [],
    },
    findings: [],
    recent_evidence: [],
    ...overrides,
  };
}

function payload(overrides: Partial<DashboardBootPayload> = {}): DashboardBootPayload {
  return {
    pricing_configured: true,
    pricing_snapshot: {
      configured: true,
      model_count: 4,
      official_model_count: 4,
      estimated_model_count: 0,
    },
    ...overrides,
  };
}

describe('Home model', () => {
  it('builds a fresh five-card status summary', () => {
    const model = buildHomeModel({
      payload: payload(),
      summary: summary(),
      readiness: readiness(),
      now,
    });

    expect(model.statusCards).toHaveLength(5);
    expect(model.statusCards.find(card => card.id === 'index')).toMatchObject({ value: 'Fresh' });
    expect(model.statusCards.find(card => card.id === 'mcp')?.detail).toContain('core profile');
    expect(model.statusCards.find(card => card.id === 'accounting')?.detail).toContain(
      '12 physical · 2 copied excluded',
    );
  });

  it('marks an old index stale without changing the source revision', () => {
    const model = buildHomeModel({
      payload: payload(),
      summary: summary({ latest_refresh_at: '2026-07-19T10:00:00Z' }),
      readiness: readiness(),
      now,
    });

    expect(model.statusCards.find(card => card.id === 'index')).toMatchObject({
      value: 'Stale',
      detail: expect.stringContaining('generation:7'),
    });
  });

  it('renders safe missing states for an empty index', () => {
    const model = buildHomeModel({ payload: {}, summary: undefined, readiness: undefined, now });

    expect(model.statusCards).toHaveLength(5);
    expect(model.statusCards.find(card => card.id === 'index')?.value).toBe('Missing');
    expect(model.statusCards.find(card => card.id === 'accounting')?.value).toBe('No indexed calls');
    expect(model.findings).toEqual([]);
    expect(model.recentEvidence).toEqual([]);
  });

  it('distinguishes partial pricing and copied-row accounting', () => {
    const model = buildHomeModel({
      payload: payload({
        pricing_snapshot_warning: 'Pricing snapshot changed since refresh.',
        pricing_snapshot: {
          configured: true,
          model_count: 4,
          official_model_count: 2,
          estimated_model_count: 2,
        },
      }),
      summary: summary(),
      readiness: readiness(),
      now,
    });

    expect(model.statusCards.find(card => card.id === 'pricing')).toMatchObject({ value: 'Partial' });
    expect(model.statusCards.find(card => card.id === 'accounting')?.detail).toContain(
      '2 copied excluded',
    );
  });

  it('shows MCP-ready and MCP-unavailable states deterministically', () => {
    const readyModel = buildHomeModel({ payload: payload(), summary: summary(), readiness: readiness(), now });
    const unavailableModel = buildHomeModel({
      payload: payload(),
      summary: summary(),
      readiness: readiness('unavailable'),
      now,
    });

    expect(readyModel.statusCards.find(card => card.id === 'mcp')?.value).toBe('Ready');
    expect(unavailableModel.statusCards.find(card => card.id === 'mcp')?.value).toBe('Unavailable');
  });

  it('uses the current allowance when present and reports a missing allowance safely', () => {
    const available = buildHomeModel({
      payload: payload({
        observed_usage: {
          available: true,
          source: 'local observation',
          windows: [{ key: 'weekly', label: 'Weekly', used_percent: 37 }],
        },
      }),
      summary: summary(),
      readiness: readiness(),
      now,
    });
    const missing = buildHomeModel({
      payload: payload({ allowance_configured: false }),
      summary: summary(),
      readiness: readiness(),
      now,
    });

    expect(available.statusCards.find(card => card.id === 'allowance')?.value).toBe('63% remaining');
    expect(missing.statusCards.find(card => card.id === 'allowance')?.value).toBe('Not configured');
  });

  it('uses bounded Home status pricing and allowance before usage rows hydrate', () => {
    const model = buildHomeModel({
      payload: {},
      summary: summary({
        pricing: {
          configured: true,
          model_count: 3,
          estimated_model_count: 0,
          error: null,
        },
        allowance: {
          configured: true,
          error: null,
          observed_usage: {
            available: true,
            source: 'local observation',
            windows: [{ key: 'weekly', label: 'Weekly', used_percent: 37 }],
          },
          windows: [],
        },
      }),
      readiness: readiness(),
      now,
    });

    expect(model.statusCards.find(card => card.id === 'pricing')?.value).toBe('Ready');
    expect(model.statusCards.find(card => card.id === 'allowance')?.value).toBe('63% remaining');
  });

  it('caps findings at three and recent evidence at five', () => {
    const findings = Array.from({ length: 6 }, (_, index) => ({
      finding_id: `finding-${index}`,
      confidence: 'high' as const,
      title: `Finding ${index}`,
      summary: `Why ${index}`,
      action: `Act ${index}`,
      follow_up_prompt: `Investigate ${index}`,
      evidence: { kind: 'call' as const, record_id: `record-${index}` },
    }));
    const recent_evidence = Array.from({ length: 8 }, (_, index) => ({
      kind: 'call' as const,
      evidence_id: `record-${index}`,
      label: `Thread ${index}`,
      detail: 'gpt-5 · 1,000 tokens',
      observed_at: `2026-07-21T0${index}:00:00Z`,
      record_id: `record-${index}`,
    }));
    const model = buildHomeModel({
      payload: payload(),
      summary: summary({ findings, recent_evidence }),
      readiness: readiness(),
      now,
    });

    expect(model.findings).toHaveLength(3);
    expect(model.recentEvidence).toHaveLength(5);
  });

  it('drops findings that are not high confidence', () => {
    const model = buildHomeModel({
      payload: payload(),
      summary: summary({
        findings: [{
          finding_id: 'finding-review',
          confidence: 'review',
          title: 'Review only',
          summary: 'Not deterministic enough for Home',
          action: 'Inspect manually',
          follow_up_prompt: 'Review this',
          evidence: { kind: 'call', record_id: 'record-review' },
        }],
      }),
      readiness: readiness(),
      now,
    });

    expect(model.findings).toEqual([]);
  });
});
