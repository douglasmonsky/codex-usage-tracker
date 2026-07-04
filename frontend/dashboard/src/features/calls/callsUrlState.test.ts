import { describe, expect, it } from 'vitest';

import {
  buildCallsViewLink,
  cleanCallsDateInput,
  defaultCallsSortDirection,
  detailFirstSelectedCallId,
  readCallsSortKeyParam,
  readConfidenceFilterParam,
  readDateInputParam,
  readDensityParam,
  readInitialSelectedCallId,
  readPageVisibleRowsParam,
  readSortDirectionParam,
  readSourceFilterParam,
  readTimeFilterParam,
} from './callsUrlState';

describe('Calls URL state helpers', () => {
  it('hydrates legacy aliases for confidence, time, and detail-first state', () => {
    const href = 'https://example.test/react-dashboard.html?view=calls&pricing=cost-estimated&time=this-week&detail=first';

    expect(readConfidenceFilterParam(href)).toBe('cost-estimated');
    expect(readTimeFilterParam(href)).toBe('this-week');
    expect(readInitialSelectedCallId(href)).toBe(detailFirstSelectedCallId);
  });

  it('sanitizes URL-backed date, source, sort, density, and page params', () => {
    const href = 'https://example.test/react-dashboard.html?source=git&from=2026-02-30&to=2026-02-28&sort=cost&direction=asc&density=roomy&page=3';

    expect(readSourceFilterParam(href)).toBe('git');
    expect(readDateInputParam('from', href)).toBe('');
    expect(readDateInputParam('to', href)).toBe('2026-02-28');
    expect(readCallsSortKeyParam(href)).toBe('cost');
    expect(readSortDirectionParam('cost', href)).toBe('asc');
    expect(readDensityParam(href)).toBe('roomy');
    expect(readPageVisibleRowsParam(250, href)).toBe(750);
  });

  it('falls back invalid sort state to legacy defaults', () => {
    const href = 'https://example.test/react-dashboard.html?sort=unknown&direction=sideways&source=bad&date=bad&density=wide&page=-1';

    expect(readSourceFilterParam(href)).toBe('all');
    expect(readTimeFilterParam(href)).toBe('all');
    expect(readCallsSortKeyParam(href)).toBe('time');
    expect(readSortDirectionParam('time', href)).toBe('desc');
    expect(readDensityParam(href)).toBe('dense');
    expect(readPageVisibleRowsParam(250, href)).toBe(250);
  });

  it('builds normalized Calls links and clears stale legacy params', () => {
    const url = buildCallsViewLink(
      {
        localQuery: ' thread-9f3a ',
        modelFilter: 'o4-mini',
        effortFilter: 'high',
        confidenceFilter: 'cost-estimated',
        sourceFilter: 'source-file',
        timeFilter: 'custom',
        dateStart: cleanCallsDateInput('2026-07-01'),
        dateEnd: cleanCallsDateInput('2026-07-03'),
        sortKey: 'cost',
        sortDirection: defaultCallsSortDirection('cost'),
        density: 'roomy',
        selectedRecordId: 'record-1',
        visibleRowCount: 501,
        pageSize: 250,
      },
      'https://example.test/react-dashboard.html?view=calls&detail=first&pricing=cost-unpriced',
    );

    expect(url.searchParams.get('view')).toBe('calls');
    expect(url.searchParams.get('detail')).toBeNull();
    expect(url.searchParams.get('pricing')).toBeNull();
    expect(url.searchParams.get('call_q')).toBe('thread-9f3a');
    expect(url.searchParams.get('model')).toBe('o4-mini');
    expect(url.searchParams.get('confidence')).toBe('cost-estimated');
    expect(url.searchParams.get('date')).toBe('custom');
    expect(url.searchParams.get('time')).toBe('custom');
    expect(url.searchParams.get('from')).toBe('2026-07-01');
    expect(url.searchParams.get('to')).toBe('2026-07-03');
    expect(url.searchParams.get('direction')).toBeNull();
    expect(url.searchParams.get('page')).toBe('3');
  });
});
