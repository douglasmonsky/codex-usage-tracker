import { describe, expect, it } from 'vitest';
import type { CallDetailResult } from '../../api/calls';
import type { CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { callInvestigatorCallForCurrentUrl, resolveCallInvestigatorSelection } from './callInvestigatorState';

function callFixture(id: string, overrides: Partial<CallRow> = {}): CallRow {
  return {
    ...fixtureModel.calls[0],
    id,
    rawTime: '2026-07-03T12:00:00Z',
    time: 'Jul 3, 12:00 PM',
    thread: 'fixture-thread',
    ...overrides,
  };
}

function detailFixture(record: CallRow, previousRecord: CallRow | null, nextRecord: CallRow | null): CallDetailResult {
  return {
    record,
    previousRecord,
    nextRecord,
    adjacentRecords: [previousRecord, record, nextRecord].filter(Boolean) as CallRow[],
    rawPayload: {},
  };
}

describe('callInvestigatorState', () => {
  it('selects the current URL record or first loaded call for current-view exports', () => {
    expect(
      callInvestigatorCallForCurrentUrl(
        fixtureModel,
        'http://localhost/react-dashboard.html?view=call&record=fixture-call-2',
      ).map(call => call.id),
    ).toEqual(['fixture-call-2']);
    expect(callInvestigatorCallForCurrentUrl(fixtureModel, 'http://localhost/react-dashboard.html?view=call').map(call => call.id)).toEqual([
      'fixture-call-0',
    ]);
    expect(callInvestigatorCallForCurrentUrl(fixtureModel, 'http://localhost/react-dashboard.html?view=call&record=missing')).toEqual([]);
  });

  it('resolves loaded snapshot records with adjacent navigation and loaded position labels', () => {
    const calls = [
      callFixture('older', { rawTime: '2026-07-03T10:00:00Z', thread: 'thread-a' }),
      callFixture('selected', { rawTime: '2026-07-03T11:00:00Z', thread: 'thread-a' }),
      callFixture('newer', { rawTime: '2026-07-03T12:00:00Z', thread: 'thread-a' }),
      callFixture('other-thread', { rawTime: '2026-07-03T13:00:00Z', thread: 'thread-b' }),
    ];

    const selection = resolveCallInvestigatorSelection({ calls, recordId: 'selected', detail: null });

    expect(selection.call?.id).toBe('selected');
    expect(selection.previous?.id).toBe('older');
    expect(selection.next?.id).toBe('newer');
    expect(selection.positionLabel).toBe('2 of 4 loaded calls');
    expect(selection.threadCalls.map(call => call.id)).toEqual(['newer', 'selected', 'older']);
  });

  it('hydrates records outside the loaded snapshot with API previous and next rows', () => {
    const loadedCalls = [callFixture('loaded-a', { thread: 'loaded-thread' })];
    const previous = callFixture('hydrated-prev', { rawTime: '2026-07-03T10:00:00Z', thread: 'hydrated-thread' });
    const record = callFixture('hydrated-record', { rawTime: '2026-07-03T11:00:00Z', thread: 'hydrated-thread' });
    const next = callFixture('hydrated-next', { rawTime: '2026-07-03T12:00:00Z', thread: 'hydrated-thread' });

    const selection = resolveCallInvestigatorSelection({
      calls: loadedCalls,
      recordId: 'hydrated-record',
      detail: detailFixture(record, previous, next),
    });

    expect(selection.modelIndex).toBe(-1);
    expect(selection.call?.id).toBe('hydrated-record');
    expect(selection.previous?.id).toBe('hydrated-prev');
    expect(selection.next?.id).toBe('hydrated-next');
    expect(selection.positionLabel).toBe('Hydrated from /api/call');
    expect(selection.threadCalls.map(call => call.id)).toEqual(['hydrated-next', 'hydrated-record', 'hydrated-prev']);
  });

  it('ignores stale hydrated detail for a different selected record', () => {
    const calls = [callFixture('loaded-a'), callFixture('loaded-b')];
    const staleDetail = detailFixture(callFixture('stale-record'), null, null);

    const selection = resolveCallInvestigatorSelection({ calls, recordId: 'loaded-b', detail: staleDetail });

    expect(selection.hydratedDetail).toBeNull();
    expect(selection.call?.id).toBe('loaded-b');
    expect(selection.positionLabel).toBe('2 of 2 loaded calls');
  });
});
