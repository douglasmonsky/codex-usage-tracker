import { describe, expect, it } from 'vitest';
import type { ShellI18n } from '../../app/i18n';
import type { CallContextPayload, CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import {
  evidenceStateReadout,
  exactReadoutBody,
  nextDiagnosticMove,
  previousCallReadout,
  previousUnavailableReadout,
  readoutPositionDetail,
  serializedEvidenceReadoutDetail,
} from './callInvestigatorReadout';

const shellI18n: ShellI18n = {
  language: 'en',
  direction: 'ltr',
  languages: [],
  t: (key, fallback) => fallback ?? key,
  translateText: value => value,
  formatText: (template, values) => template.replace(/\{(\w+)\}/gu, (token, key) => String(values[key] ?? token)),
  navLabel: (_view, fallback) => fallback,
};

function callFixture(overrides: Partial<CallRow> = {}): CallRow {
  return {
    ...fixtureModel.calls[0],
    input: 10_000,
    cachedInput: 8_000,
    uncachedInput: 2_000,
    output: 1_000,
    cachedPct: 80,
    ...overrides,
  };
}

function payloadFixture(overrides: Partial<CallContextPayload> = {}): CallContextPayload {
  return {
    schema: 'test',
    record_id: 'record-1',
    entries: [{ role: 'user', text: 'visible' }],
    visible_char_count: 42,
    visible_token_estimate: 11,
    visible_token_estimator: 'fixture estimator',
    omitted: {},
    source: {},
    ...overrides,
  };
}

describe('callInvestigatorReadout', () => {
  it('formats exact aggregate accounting with localized template values', () => {
    expect(exactReadoutBody(callFixture(), shellI18n)).toBe(
      '10,000 input tokens = 8,000 cached + 2,000 uncached; 1,000 output tokens; 80.0% cache reuse.',
    );
  });

  it('explains previous-call cache drop and stable delta states', () => {
    expect(
      previousCallReadout(
        callFixture({ uncachedInput: 7_000, cachedInput: 1_000 }),
        callFixture({ uncachedInput: 2_000, cachedInput: 8_000 }),
      ),
    ).toBe('Fresh input rose by 5,000 while cached input fell by 7,000; classic cache-drop profile.');

    expect(previousCallReadout(callFixture(), callFixture())).toBe(
      'Token accounting broadly stable compared previous call in resolved thread.',
    );
    expect(previousUnavailableReadout(shellI18n)).toBe(
      'No previous call is loaded in resolved thread, call-to-call deltas unavailable.',
    );
  });

  it('summarizes loaded, deferred, loading, error, and idle evidence states', () => {
    expect(
      evidenceStateReadout(
        {
          status: 'loaded',
          payload: payloadFixture({ serialized_evidence: { raw_json_token_estimate: 80, raw_json_char_count: 320 } }),
        },
        shellI18n,
      ),
    ).toBe('Evidence analyzed: 1 selected-turn entries, 42 visible redacted chars, 11 visible tokens. Serialized local upper bound: 80 tokens.');

    expect(
      serializedEvidenceReadoutDetail(payloadFixture({ serialized_evidence: { deferred: true } }), shellI18n),
    ).toBe('Fast serialized estimate only; full serialized grouping deferred.');
    expect(evidenceStateReadout({ status: 'loading', message: 'Loading evidence...' }, shellI18n)).toBe('Loading evidence...');
    expect(evidenceStateReadout({ status: 'error', message: 'No token' }, shellI18n)).toBe('Evidence request failed: No token');
    expect(evidenceStateReadout({ status: 'idle' }, shellI18n)).toContain('Evidence is not loaded yet.');
  });

  it('prioritizes next diagnostic moves from cache miss, uncached spike, and healthy cache signals', () => {
    expect(
      nextDiagnosticMove(callFixture({ input: 4_000, cachedInput: 0, uncachedInput: 4_000 }), callFixture({ input: 4_000, cachedInput: 3_600 })),
    ).toBe('Compare previous call, then inspect loaded evidence see fresh context was sent after cache miss.');

    expect(nextDiagnosticMove(callFixture({ uncachedInput: 9_000 }), callFixture({ uncachedInput: 2_000 }))).toBe(
      'Inspect most recent evidence entries first; spike is in fresh uncached input, not cached history.',
    );
    expect(nextDiagnosticMove(callFixture({ input: 10_000, cachedInput: 9_000, uncachedInput: 1_000, cachedPct: 90 }), null)).toBe(
      'Cache reuse is healthy; focus on 1,000 uncached tokens were still billed as fresh input.',
    );
  });

  it('labels hydrated and loaded positions explicitly', () => {
    expect(readoutPositionDetail('Hydrated from /api/call')).toBe('Position: hydrated live record outside loaded snapshot');
    expect(readoutPositionDetail('2 of 10 loaded calls')).toBe('Position: 2 of 10 loaded calls');
  });
});
