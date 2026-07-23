import { describe, expect, it } from 'vitest';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import {
buildThreadsViewLink,
detailFirstSelectedThreadName,
filterThreads,
  readInitialSelectedThreadParam,
  readThreadCallSortDirectionParam,
  readThreadCallSortParam,
readThreadPageVisibleRowsParam,
readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  sortThreads,
  threadPageNumberFromVisibleRows,
  threadsTablePageSize,
} from './threadsUrlState';

const baseHref = 'http://localhost/react-dashboard.html?view=threads';

describe('threadsUrlState', () => {
  it('normalizes legacy expansion while dropping obsolete child page state', () => {
    expect(readInitialSelectedThreadParam('http://localhost/?view=threads&threads=alpha,beta')).toBe('alpha');
    expect(readInitialSelectedThreadParam('http://localhost/?view=threads&expand=first')).toBe(detailFirstSelectedThreadName);

    const url = buildThreadsViewLink({
      localQuery: 'cache',
      riskFilter: 'High',
      selectedThreadName: 'alpha',
      sorting: [{ id: 'totalTokens', desc: true }],
      visibleRowCount: threadsTablePageSize,
      threadCallSort: 'tokens',
      threadCallSortDirection: 'desc',
    }, 'http://localhost/?view=threads&thread_call_page=9');

    expect(url.searchParams.get('thread')).toBe('alpha');
    expect(url.searchParams.get('thread_call_sort')).toBe('tokens');
    expect(url.searchParams.has('thread_call_page')).toBe(false);
  });

  it('removes thread-only state when the accordion is collapsed', () => {
    const url = buildThreadsViewLink({
      localQuery: '',
      riskFilter: 'all',
      selectedThreadName: null,
      sorting: [],
      visibleRowCount: threadsTablePageSize,
      threadCallSort: 'newest',
      threadCallSortDirection: 'desc',
    }, 'http://localhost/?view=threads&thread=alpha&thread_call_page=4');

    expect(url.searchParams.has('thread')).toBe(false);
    expect(url.searchParams.has('thread_call_page')).toBe(false);
  });

  it('hydrates selected thread state from current and legacy thread URLs', () => {
    expect(readInitialSelectedThreadParam(
      `${baseHref}&thread_key=session%3A019e374d-c19f-7da3-a44f-8de043a7a64e&thread=Private%20project`,
    )).toBe('session:019e374d-c19f-7da3-a44f-8de043a7a64e');
    expect(readInitialSelectedThreadParam(`${baseHref}&thread=thread-3c5d`)).toBe('thread-3c5d');
    expect(readInitialSelectedThreadParam(`${baseHref}&detail=first`)).toBe(detailFirstSelectedThreadName);
    expect(readInitialSelectedThreadParam(`${baseHref}&expand=all`)).toBe(detailFirstSelectedThreadName);
    expect(readInitialSelectedThreadParam(`${baseHref}&threads=thread-7c2b,thread-9f3a`)).toBe('thread-7c2b');
  });

  it('sanitizes thread query, risk, sort, page, and selected-call params', () => {
const href = `${baseHref}&thread_q=%20thread-3c5d%20&risk=High&sort=totalTokens&direction=desc&page=3&thread_call_sort=cache&thread_call_direction=desc&thread_call_page=2`;

    expect(readThreadSearchParam('thread_q', href)).toBe('thread-3c5d');
    expect(readThreadRiskParam(href)).toBe('High');
    expect(readThreadSortingParam(href)).toEqual([{ id: 'totalTokens', desc: true }]);
expect(readThreadPageVisibleRowsParam(threadsTablePageSize, href)).toBe(750);
expect(readThreadCallSortParam(href)).toBe('cache');
expect(readThreadCallSortDirectionParam('cache', href)).toBe('desc');
    expect(readThreadSortingParam(`${baseHref}&sort=total&direction=desc`)).toEqual([{ id: 'totalTokens', desc: true }]);
    expect(readThreadSortingParam(`${baseHref}&sort=usage&direction=desc`)).toEqual([{ id: 'credits', desc: true }]);
    expect(readThreadSortingParam(`${baseHref}&sort=cache&direction=asc`)).toEqual([{ id: 'cachePct', desc: false }]);
    expect(readThreadSortingParam(`${baseHref}&sort=context&direction=desc`)).toEqual([{ id: 'contextPct', desc: true }]);
expect(readThreadCallSortParam(`${baseHref}&thread_call_sort=time`)).toBe('newest');
expect(readThreadCallSortParam(`${baseHref}&thread_call_sort=total`)).toBe('tokens');
expect(readThreadCallSortParam(`${baseHref}&thread_call_sort=reasoning`)).toBe('reasoning');
expect(readThreadCallSortParam(`${baseHref}&thread_call_sort=cached`)).toBe('cached');
expect(readThreadCallSortParam(`${baseHref}&thread_call_sort=uncached`)).toBe('uncached');
expect(readThreadCallSortDirectionParam('cache', `${baseHref}&thread_call_sort=cache`)).toBe('asc');
  });

  it('falls back invalid URL values to legacy defaults', () => {
    const href = `${baseHref}&risk=Critical&sort=investigate&direction=desc&page=-4&thread_call_sort=slow&thread_call_page=0`;

    expect(readThreadRiskParam(href)).toBe('all');
    expect(readThreadSortingParam(href)).toEqual([]);
    expect(readThreadPageVisibleRowsParam(threadsTablePageSize, href)).toBe(threadsTablePageSize);
    expect(readThreadCallSortParam(href)).toBe('newest');
  });

  it('builds normalized thread view links while preserving inactive call selection', () => {
    const url = buildThreadsViewLink(
      {
        localQuery: ' thread ',
        riskFilter: 'Medium',
        selectedThreadName: 'thread-3c5d',
        sorting: [{ id: 'cachePct', desc: true }],
visibleRowCount: 501,
threadCallSort: 'tokens',
threadCallSortDirection: 'asc',
      },
      `${baseHref}&record=stale&detail=first&expand=all&threads=legacy-a,legacy-b`,
    );

    expect(url.searchParams.get('view')).toBe('explore');
    expect(url.searchParams.get('mode')).toBe('threads');
    expect(url.searchParams.get('thread_q')).toBe('thread');
    expect(url.searchParams.get('risk')).toBe('Medium');
    expect(url.searchParams.get('thread')).toBe('thread-3c5d');
    expect(url.searchParams.get('sort')).toBe('cachePct');
    expect(url.searchParams.get('direction')).toBe('desc');
expect(url.searchParams.get('page')).toBe('3');
expect(url.searchParams.get('thread_call_sort')).toBe('tokens');
expect(url.searchParams.get('thread_call_direction')).toBe('asc');
expect(url.searchParams.get('thread_call_page')).toBeNull();
    expect(url.searchParams.get('record')).toBe('stale');
    expect(url.searchParams.get('detail')).toBeNull();
    expect(url.searchParams.get('expand')).toBeNull();
    expect(url.searchParams.get('threads')).toBeNull();
  });

  it('emits a canonical thread key and removes the display-name selector', () => {
    const url = buildThreadsViewLink(
      {
        localQuery: '',
        riskFilter: 'all',
        selectedThreadName: 'Private project',
        selectedThreadKey: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e',
        sorting: [],
        visibleRowCount: threadsTablePageSize,
        threadCallSort: 'newest',
        threadCallSortDirection: 'desc',
      },
      `${baseHref}&thread=stale&thread_key=session%3A019e374d-c19f-7da3-a44f-8de043a7a64f`,
    );

    expect(url.searchParams.get('thread_key')).toBe('session:019e374d-c19f-7da3-a44f-8de043a7a64e');
    expect(url.searchParams.has('thread')).toBe(false);
  });

  it('omits default thread view link params', () => {
    const url = buildThreadsViewLink(
      {
        localQuery: '',
        riskFilter: 'all',
        selectedThreadName: null,
        sorting: [],
visibleRowCount: threadsTablePageSize,
threadCallSort: 'newest',
threadCallSortDirection: 'desc',
      },
      `${baseHref}&thread_q=old&risk=High&thread=old&sort=totalTokens&direction=desc&page=4&thread_call_sort=cache&thread_call_page=2`,
    );

    expect(url.searchParams.get('view')).toBe('explore');
    expect(url.searchParams.get('mode')).toBe('threads');
    expect(url.searchParams.get('thread_q')).toBeNull();
    expect(url.searchParams.get('risk')).toBeNull();
    expect(url.searchParams.get('thread')).toBeNull();
    expect(url.searchParams.get('sort')).toBeNull();
    expect(url.searchParams.get('direction')).toBeNull();
expect(url.searchParams.get('page')).toBeNull();
expect(url.searchParams.get('thread_call_sort')).toBeNull();
expect(url.searchParams.get('thread_call_direction')).toBeNull();
expect(url.searchParams.get('thread_call_page')).toBeNull();
  });

  it('keeps ascending sort direction explicit when a thread sort key is active', () => {
    const url = buildThreadsViewLink(
      {
        localQuery: '',
        riskFilter: 'all',
        selectedThreadName: null,
        sorting: [{ id: 'totalTokens', desc: false }],
visibleRowCount: threadsTablePageSize,
threadCallSort: 'newest',
threadCallSortDirection: 'desc',
      },
      baseHref,
    );

    expect(url.searchParams.get('sort')).toBe('totalTokens');
    expect(url.searchParams.get('direction')).toBe('asc');
  });

  it('filters and sorts thread rows consistently with URL-backed table state', () => {
    const filtered = filterThreads(fixtureModel.threads, {
      globalQuery: '',
      localQuery: 'thread',
      riskFilter: 'High',
    });

    expect(filtered.map(thread => thread.name)).toEqual(['thread-9f3a', 'thread-1a8c']);
    expect(sortThreads(filtered, [{ id: 'totalTokens', desc: false }]).map(thread => thread.name)).toEqual([
      'thread-1a8c',
      'thread-9f3a',
    ]);
    expect(sortThreads(filtered, [{ id: 'totalTokens', desc: true }]).map(thread => thread.name)).toEqual([
      'thread-9f3a',
      'thread-1a8c',
    ]);
  });

  it('derives stable page numbers from visible row counts', () => {
    expect(threadPageNumberFromVisibleRows(1, 250)).toBe(1);
    expect(threadPageNumberFromVisibleRows(250, 250)).toBe(1);
    expect(threadPageNumberFromVisibleRows(251, 250)).toBe(2);
  });
});
