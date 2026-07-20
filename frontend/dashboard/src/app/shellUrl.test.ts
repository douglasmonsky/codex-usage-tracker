import { describe, expect, it } from 'vitest';

import {
  callReturnViewFromSearch,
  callReturnViewLabel,
  clearInactiveViewSearchParams,
  hasCallReturnViewParam,
  historyScopeFromUrl,
  historyScopeUrl,
  normalizeLegacyShellUrl,
  viewFromUrlParam,
} from './shellUrl';

describe('shell URL compatibility helpers', () => {
it('maps legacy Insights route params to the renamed Overview workspace', () => {
  expect(viewFromUrlParam('insights')).toBe('overview');
  expect(callReturnViewFromSearch('?return=insights')).toBe('overview');
    expect(callReturnViewFromSearch('?return=call')).toBe('calls');
    expect(callReturnViewFromSearch('?return=unknown&view=call', 'threads')).toBe('threads');
    expect(hasCallReturnViewParam('?view=call&return=insights')).toBe(true);
    expect(hasCallReturnViewParam('?view=call')).toBe(false);
  });

  it('normalizes legacy copied links in place while preserving other query params', () => {
    const url = new URL('https://example.test/react-dashboard.html?view=insights&return=insights&record=abc&q=cache');

    expect(normalizeLegacyShellUrl(url)).toBe(true);
  expect(url.searchParams.get('view')).toBe('overview');
  expect(url.searchParams.get('return')).toBe('overview');
    expect(url.searchParams.get('record')).toBe('abc');
    expect(url.searchParams.get('q')).toBe('cache');
    expect(normalizeLegacyShellUrl(url)).toBe(false);
  });

  it('derives history scope URLs without dropping existing shell params', () => {
    expect(historyScopeFromUrl('active', '?history=all')).toBe('all');
    expect(historyScopeFromUrl('all', '?history=active')).toBe('all');

    const allHistoryUrl = historyScopeUrl('all', 'https://example.test/react-dashboard.html?view=threads&q=cache');
    expect(allHistoryUrl.searchParams.get('history')).toBe('all');
    expect(allHistoryUrl.searchParams.get('view')).toBe('threads');
    expect(allHistoryUrl.searchParams.get('q')).toBe('cache');

    const activeUrl = historyScopeUrl('active', allHistoryUrl.href);
    expect(activeUrl.searchParams.has('history')).toBe(false);
    expect(activeUrl.searchParams.get('view')).toBe('threads');
  });

  it('labels return views from the full route catalog', () => {
    expect(callReturnViewLabel('calls')).toBe('Calls');
    expect(callReturnViewLabel('investigator')).toBe('Investigate');
    expect(callReturnViewLabel('cache-context')).toBe('Cache And Context');
  });

it('clears inactive workspace URL state while preserving shared shell filters', () => {
  const url = new URL(
    'https://example.test/react-dashboard.html?view=overview&finding=2&thread=thread-a&thread_key=thread-key-a&expand=all&threads=thread-a,thread-b&thread_q=cache&risk=Low&thread_call_sort=total&thread_call_page=2&cache_thread=Thread%20Alpha&report=weekly-credits&usage_plan=Weekly&usage_effort=high&usage_subagents=0&usage_sample=80&usage_confidence=0.55&diagnostic_source=tools&diagnostic_fact=tool:read&record=fixture-call-0&return=calls&mode=full&max_entries=50&max_chars=0&include_tool_output=1&include_compaction_history=true&detail=first&call_q=cache&source=missing&sort=total&direction=asc&density=roomy&page=3&model=gpt-5&effort=high&confidence=cost-estimated&date=last-7-days&history=all&q=cache',
  );

  clearInactiveViewSearchParams(url, 'overview');

  for (const name of [
    'finding',
    'thread',
    'thread_key',
    'expand',
    'threads',
    'thread_q',
    'risk',
    'thread_call_sort',
    'thread_call_page',
    'cache_thread',
    'report',
    'usage_plan',
    'usage_effort',
    'usage_subagents',
    'usage_sample',
    'usage_confidence',
    'diagnostic_source',
    'diagnostic_fact',
    'record',
    'return',
    'mode',
    'max_entries',
    'max_chars',
    'include_tool_output',
    'include_compaction_history',
    'detail',
    'call_q',
    'source',
    'sort',
    'direction',
    'density',
    'page',
  ]) {
    expect(url.searchParams.get(name)).toBeNull();
  }
  expect(url.searchParams.get('model')).toBe('gpt-5');
  expect(url.searchParams.get('effort')).toBe('high');
  expect(url.searchParams.get('confidence')).toBe('cost-estimated');
  expect(url.searchParams.get('date')).toBe('last-7-days');
  expect(url.searchParams.get('history')).toBe('all');
  expect(url.searchParams.get('q')).toBe('cache');
});

it('preserves active workspace URL state while clearing other workspace state', () => {
  const callsUrl = new URL(
    'https://example.test/react-dashboard.html?view=calls&detail=first&call_q=cache&source=missing&sort=total&direction=asc&density=roomy&page=3&diagnostic_source=tools&report=weekly-credits',
  );

  clearInactiveViewSearchParams(callsUrl, 'calls');

  expect(callsUrl.searchParams.get('detail')).toBe('first');
  expect(callsUrl.searchParams.get('call_q')).toBe('cache');
  expect(callsUrl.searchParams.get('source')).toBe('missing');
  expect(callsUrl.searchParams.get('sort')).toBe('total');
  expect(callsUrl.searchParams.get('direction')).toBe('asc');
  expect(callsUrl.searchParams.get('density')).toBe('roomy');
  expect(callsUrl.searchParams.get('page')).toBe('3');
  expect(callsUrl.searchParams.get('diagnostic_source')).toBeNull();
  expect(callsUrl.searchParams.get('report')).toBeNull();

  const callUrl = new URL(
    'https://example.test/react-dashboard.html?view=call&record=fixture-call-0&return=calls&mode=full&max_entries=50&max_chars=0&include_tool_output=1&include_compaction_history=true&call_q=cache',
  );

  clearInactiveViewSearchParams(callUrl, 'call');

  expect(callUrl.searchParams.get('record')).toBe('fixture-call-0');
  expect(callUrl.searchParams.get('return')).toBe('calls');
  expect(callUrl.searchParams.get('mode')).toBe('full');
  expect(callUrl.searchParams.get('max_entries')).toBe('50');
  expect(callUrl.searchParams.get('max_chars')).toBe('0');
expect(callUrl.searchParams.get('include_tool_output')).toBe('1');
expect(callUrl.searchParams.get('include_compaction_history')).toBe('true');
expect(callUrl.searchParams.get('call_q')).toBeNull();

const reportReturnUrl = new URL(
  'https://example.test/react-dashboard.html?view=call&record=fixture-call-6&return=reports&report=weekly-credits&mode=full&diagnostic_fact=tool:read',
);

clearInactiveViewSearchParams(reportReturnUrl, 'call', 'reports');

expect(reportReturnUrl.searchParams.get('record')).toBe('fixture-call-6');
expect(reportReturnUrl.searchParams.get('return')).toBe('reports');
expect(reportReturnUrl.searchParams.get('report')).toBe('weekly-credits');
expect(reportReturnUrl.searchParams.get('mode')).toBe('full');
expect(reportReturnUrl.searchParams.get('diagnostic_fact')).toBeNull();
});
});
