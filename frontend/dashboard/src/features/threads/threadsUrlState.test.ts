import { describe, expect, it } from 'vitest';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import {
buildThreadsViewLink,
detailFirstSelectedThreadName,
filterThreads,
  readInitialSelectedThreadParam,
  readThreadCallPageVisibleRowsParam,
  readThreadCallSortDirectionParam,
  readThreadCallSortParam,
readThreadPageVisibleRowsParam,
readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  sortThreads,
  threadCallPageSize,
  threadPageNumberFromVisibleRows,
  threadsTablePageSize,
} from './threadsUrlState';

const baseHref = 'http://localhost/react-dashboard.html?view=threads';

describe('threadsUrlState', () => {
  it('hydrates selected thread state from current and legacy thread URLs', () => {
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
expect(readThreadCallPageVisibleRowsParam(threadCallPageSize, href)).toBe(10);
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
    expect(readThreadCallPageVisibleRowsParam(threadCallPageSize, href)).toBe(threadCallPageSize);
  });

  it('builds normalized thread view links and clears stale legacy params', () => {
    const url = buildThreadsViewLink(
      {
        localQuery: ' thread ',
        riskFilter: 'Medium',
        selectedThreadName: 'thread-3c5d',
        sorting: [{ id: 'cachePct', desc: true }],
visibleRowCount: 501,
threadCallSort: 'tokens',
threadCallSortDirection: 'asc',
visibleThreadCallCount: 12,
      },
      `${baseHref}&record=stale&detail=first&expand=all&threads=legacy-a,legacy-b`,
    );

    expect(url.searchParams.get('view')).toBe('threads');
    expect(url.searchParams.get('thread_q')).toBe('thread');
    expect(url.searchParams.get('risk')).toBe('Medium');
    expect(url.searchParams.get('thread')).toBe('thread-3c5d');
    expect(url.searchParams.get('sort')).toBe('cachePct');
    expect(url.searchParams.get('direction')).toBe('desc');
expect(url.searchParams.get('page')).toBe('3');
expect(url.searchParams.get('thread_call_sort')).toBe('tokens');
expect(url.searchParams.get('thread_call_direction')).toBe('asc');
expect(url.searchParams.get('thread_call_page')).toBe('3');
    expect(url.searchParams.get('record')).toBeNull();
    expect(url.searchParams.get('detail')).toBeNull();
    expect(url.searchParams.get('expand')).toBeNull();
    expect(url.searchParams.get('threads')).toBeNull();
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
visibleThreadCallCount: threadCallPageSize,
      },
      `${baseHref}&thread_q=old&risk=High&thread=old&sort=totalTokens&direction=desc&page=4&thread_call_sort=cache&thread_call_page=2`,
    );

    expect(url.searchParams.get('view')).toBe('threads');
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
visibleThreadCallCount: threadCallPageSize,
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
