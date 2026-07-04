import { describe, expect, it } from 'vitest';
import type { CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { callsDateRange, filterCalls, sortCalls, type CallsFilterState } from './callsFilterSort';

const baseFilter: CallsFilterState = {
  globalQuery: '',
  localQuery: '',
  modelFilter: 'all',
  effortFilter: 'all',
  confidenceFilter: 'all',
  sourceFilter: 'all',
  timeFilter: 'all',
  dateStart: '',
  dateEnd: '',
  activePreset: '',
};

function callFixture(id: string, overrides: Partial<CallRow> = {}): CallRow {
  return {
    ...fixtureModel.calls[0],
    id,
    rawTime: '2026-07-03T12:00:00',
    time: 'Jul 3, 12:00 PM',
    tags: [],
    signal: '',
    recommendation: '',
    contextWindowPct: 20,
    ...overrides,
  };
}

function withFilters(overrides: Partial<CallsFilterState>): CallsFilterState {
  return { ...baseFilter, ...overrides };
}

describe('callsFilterSort', () => {
  it('requires global and local queries to both match searchable call fields', () => {
    const calls = [
      callFixture('both', { thread: 'alpha-thread', tags: ['needle'] }),
      callFixture('global-only', { thread: 'alpha-thread', tags: ['other'] }),
      callFixture('local-only', { thread: 'beta-thread', tags: ['needle'] }),
    ];

    expect(filterCalls(calls, withFilters({ globalQuery: 'alpha', localQuery: 'needle' })).map(call => call.id)).toEqual([
      'both',
    ]);
  });

  it('applies model, effort, confidence, source, and preset filters together', () => {
    const matching = callFixture('matching', {
      model: 'codex-1',
      effort: 'high',
      pricingEstimated: false,
      cost: 1.25,
      signal: 'cache-risk',
      uncachedInput: 75_000,
      project: 'codex-usage-tracker',
      projectRelativeCwd: 'frontend/dashboard',
      cwd: '/repo',
      projectTags: ['dashboard'],
    });
    const missingSource = callFixture('missing-source', {
      model: 'codex-1',
      effort: 'high',
      pricingEstimated: false,
      cost: 1.25,
      signal: 'cache-risk',
      project: '',
      projectRelativeCwd: '',
      cwd: '',
      projectTags: [],
      sessionId: '',
      turnId: '',
      parentSessionId: '',
      gitBranch: '',
      gitRemoteLabel: '',
      gitRemoteHash: '',
      sourceFile: '',
      lineNumber: null,
    });
    const wrongEffort = callFixture('wrong-effort', {
      model: 'codex-1',
      effort: 'low',
      pricingEstimated: false,
      cost: 1.25,
      signal: 'cache-risk',
    });

    expect(
      filterCalls(
        [matching, missingSource, wrongEffort],
        withFilters({
          modelFilter: 'codex-1',
          effortFilter: 'high',
          confidenceFilter: 'cost-exact',
          sourceFilter: 'project',
          activePreset: 'cache-misses',
        }),
      ).map(call => call.id),
    ).toEqual(['matching']);
  });

  it('treats invalid custom date ranges as active filters with no matches', () => {
    const range = callsDateRange('custom', '2026-07-10', '2026-07-01', new Date('2026-07-15T12:00:00'));

    expect(range).toMatchObject({ active: true, invalid: true, label: 'Invalid date range' });
    expect(
      filterCalls(
        [callFixture('inside', { rawTime: '2026-07-03T12:00:00' })],
        withFilters({ timeFilter: 'custom', dateStart: '2026-07-10', dateEnd: '2026-07-01' }),
      ),
    ).toEqual([]);
  });

  it('includes calls through the selected custom end date', () => {
    expect(callsDateRange('custom', '2026-07-01', '2026-07-03', new Date('2026-07-15T12:00:00'))).toMatchObject({
      label: 'Custom: 2026-07-01 to 2026-07-03',
    });

    const calls = [
      callFixture('before', { rawTime: '2026-06-30T23:59:59' }),
      callFixture('start', { rawTime: '2026-07-01T00:00:00' }),
      callFixture('end', { rawTime: '2026-07-03T23:59:59' }),
      callFixture('after', { rawTime: '2026-07-04T00:00:00' }),
    ];

    expect(
      filterCalls(calls, withFilters({ timeFilter: 'custom', dateStart: '2026-07-01', dateEnd: '2026-07-03' })).map(
        call => call.id,
      ),
    ).toEqual(['start', 'end']);
  });

  it('sorts by attention signals before falling back to time', () => {
    const calls = [
      callFixture('newer-low-attention', { rawTime: '2026-07-03T12:00:00', contextWindowPct: 10, uncachedInput: 100 }),
      callFixture('older-recommendation', {
        rawTime: '2026-07-03T10:00:00',
        recommendation: 'Investigate context pressure',
        contextWindowPct: 80,
      }),
      callFixture('older-signal', { rawTime: '2026-07-03T09:00:00', signal: 'cache-risk' }),
    ];

    expect(sortCalls(calls, 'attention', 'desc').map(call => call.id)).toEqual([
      'older-signal',
      'older-recommendation',
      'newer-low-attention',
    ]);
  });

  it('keeps null context values last while preserving deterministic time/id tie breaks', () => {
    const calls = [
      callFixture('null-context', { rawTime: '2026-07-03T14:00:00', contextWindowPct: null }),
      callFixture('context-a', { rawTime: '2026-07-03T11:00:00', contextWindowPct: 45 }),
      callFixture('context-b', { rawTime: '2026-07-03T12:00:00', contextWindowPct: 45 }),
    ];

    expect(sortCalls(calls, 'context', 'asc').map(call => call.id)).toEqual([
      'context-b',
      'context-a',
      'null-context',
    ]);
  });
});
