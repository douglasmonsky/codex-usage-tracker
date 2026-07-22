import { describe, expect, it } from 'vitest';

import {
  buildExploreModeUrl,
  normalizeExploreUrl,
  readExploreMode,
} from './exploreState';

const baseHref = 'https://example.test/react-dashboard.html';

describe('exploreState', () => {
  it('defaults to Calls and normalizes both legacy evidence-browser URLs', () => {
    expect(readExploreMode(`${baseHref}?view=explore`)).toBe('calls');
    expect(readExploreMode(`${baseHref}?view=calls`)).toBe('calls');
    expect(readExploreMode(`${baseHref}?view=threads`)).toBe('threads');

    expect(normalizeExploreUrl(`${baseHref}?view=calls`).search).toBe('?view=explore&mode=calls');
    expect(normalizeExploreUrl(`${baseHref}?view=threads`).search).toBe('?view=explore&mode=threads');
  });

  it('keeps canonical call and thread selectors on deep-linked Explore URLs', () => {
    const callUrl = normalizeExploreUrl(`${baseHref}?view=calls&record=call-9&history=all`);
    const threadUrl = normalizeExploreUrl(
      `${baseHref}?view=threads&thread_key=session%3Athread-9&thread=Display+name`,
    );

    expect(callUrl.searchParams.get('record')).toBe('call-9');
    expect(callUrl.searchParams.get('history')).toBe('all');
    expect(threadUrl.searchParams.get('thread_key')).toBe('session:thread-9');
    expect(threadUrl.searchParams.get('thread')).toBe('Display name');
  });

  it('preserves shared scope and mode-specific filters while switching modes', () => {
    const threadsUrl = buildExploreModeUrl(
      'threads',
      `${baseHref}?view=explore&mode=calls&history=all&q=cache&time=this-week&project=tracker`
        + '&call_q=expensive&record=call-7&thread_q=agent&risk=High',
    );

    expect(threadsUrl.searchParams.get('mode')).toBe('threads');
    expect(threadsUrl.searchParams.get('history')).toBe('all');
    expect(threadsUrl.searchParams.get('q')).toBe('cache');
    expect(threadsUrl.searchParams.get('time')).toBe('this-week');
    expect(threadsUrl.searchParams.get('project')).toBe('tracker');
    expect(threadsUrl.searchParams.get('call_q')).toBe('expensive');
    expect(threadsUrl.searchParams.get('record')).toBe('call-7');
    expect(threadsUrl.searchParams.get('thread_q')).toBe('agent');
    expect(threadsUrl.searchParams.get('risk')).toBe('High');
  });

  it('swaps incompatible sort and pagination state without losing either mode', () => {
    const threadsUrl = buildExploreModeUrl(
      'threads',
      `${baseHref}?view=explore&mode=calls&sort=cost&direction=desc&page=4`
        + '&threads_sort=totalTokens&threads_direction=asc&threads_page=2',
    );

    expect(threadsUrl.searchParams.get('calls_sort')).toBe('cost');
    expect(threadsUrl.searchParams.get('calls_direction')).toBe('desc');
    expect(threadsUrl.searchParams.get('calls_page')).toBe('4');
    expect(threadsUrl.searchParams.get('sort')).toBe('totalTokens');
    expect(threadsUrl.searchParams.get('direction')).toBe('asc');
    expect(threadsUrl.searchParams.get('page')).toBe('2');

    const callsUrl = buildExploreModeUrl('calls', threadsUrl.toString());
    expect(callsUrl.searchParams.get('threads_sort')).toBe('totalTokens');
    expect(callsUrl.searchParams.get('threads_direction')).toBe('asc');
    expect(callsUrl.searchParams.get('threads_page')).toBe('2');
    expect(callsUrl.searchParams.get('sort')).toBe('cost');
    expect(callsUrl.searchParams.get('direction')).toBe('desc');
    expect(callsUrl.searchParams.get('page')).toBe('4');
  });

  it('drops incompatible active controls when the target mode has no saved state', () => {
    const url = buildExploreModeUrl(
      'threads',
      `${baseHref}?view=explore&mode=calls&sort=cost&direction=desc&page=3&explore=tools`,
    );

    expect(url.searchParams.get('calls_sort')).toBe('cost');
    expect(url.searchParams.get('calls_direction')).toBe('desc');
    expect(url.searchParams.get('calls_page')).toBe('3');
    expect(url.searchParams.has('sort')).toBe(false);
    expect(url.searchParams.has('direction')).toBe(false);
    expect(url.searchParams.has('page')).toBe(false);
    expect(url.searchParams.has('explore')).toBe(false);
  });
});
