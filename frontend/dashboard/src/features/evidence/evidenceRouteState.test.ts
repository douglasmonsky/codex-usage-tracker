import { describe, expect, it } from 'vitest';

import {
  buildEvidenceReturnUrl,
  normalizeEvidenceUrl,
  readEvidenceRouteState,
} from './evidenceRouteState';

describe('contextual Evidence route state', () => {
  it.each([
    ['?view=evidence&kind=call&record=record-7', 'call', 'record-7', null],
    ['?view=evidence&kind=thread&thread_key=thread%3Aalpha', 'thread', 'thread:alpha', null],
    ['?view=evidence&kind=finding&analysis=analysis-7&finding=finding-3', 'finding', 'finding-3', 'analysis-7'],
    ['?view=evidence&kind=allowance&analysis=allowance-7&evidence=interval-3', 'allowance', 'interval-3', 'allowance-7'],
  ])('reads %s without selector fallback', (search, kind, selectorId, analysisId) => {
    expect(readEvidenceRouteState(`http://localhost/${search}`)).toMatchObject({
      status: 'ready',
      kind,
      selectorId,
      analysisId,
    });
  });

  it.each([
    '?view=evidence&kind=call',
    '?view=evidence&kind=thread&thread_key=../unsafe',
    '?view=evidence&kind=finding&analysis=analysis-7',
    '?view=evidence&kind=analysis&analysis=analysis-7',
    '?view=evidence&kind=allowance&evidence=interval%2F3',
  ])('rejects malformed or unsupported selectors: %s', search => {
    expect(readEvidenceRouteState(`http://localhost/${search}`).status).toBe('invalid');
  });

  it('normalizes compatibility selector names to the canonical Task 21 URL', () => {
    const url = normalizeEvidenceUrl(
      'http://localhost/?view=evidence&kind=finding&analysis_id=analysis-7&finding_id=finding-3',
    );

    expect(url.searchParams.get('analysis')).toBe('analysis-7');
    expect(url.searchParams.get('finding')).toBe('finding-3');
    expect(url.searchParams.has('analysis_id')).toBe(false);
    expect(url.searchParams.has('finding_id')).toBe(false);
  });

  it('normalizes the direct Call Investigator compatibility route through 0.23', () => {
    const url = normalizeEvidenceUrl('http://localhost/?view=call&record=record-7');

    expect(url.searchParams.get('view')).toBe('evidence');
    expect(url.searchParams.get('kind')).toBe('call');
    expect(readEvidenceRouteState(url)).toMatchObject({
      status: 'ready', kind: 'call', selectorId: 'record-7',
    });
  });

  it('builds canonical kind defaults and preserves explicit Explore return state', () => {
    const callReturn = buildEvidenceReturnUrl(
      'http://localhost/?view=evidence&kind=call&record=record-7&call_q=expensive',
    );
    expect(callReturn.searchParams.get('view')).toBe('explore');
    expect(callReturn.searchParams.get('mode')).toBe('calls');
    expect(callReturn.searchParams.get('call_q')).toBe('expensive');
    expect(callReturn.searchParams.has('record')).toBe(false);

    const threadReturn = buildEvidenceReturnUrl(
      'http://localhost/?view=evidence&kind=thread&thread_key=thread%3Aalpha&return=explore&return_mode=threads',
    );
    expect(threadReturn.searchParams.get('view')).toBe('explore');
    expect(threadReturn.searchParams.get('mode')).toBe('threads');
    expect(threadReturn.searchParams.get('thread_key')).toBe('thread:alpha');
    expect(threadReturn.searchParams.has('return')).toBe(false);

    expect(buildEvidenceReturnUrl(
      'http://localhost/?view=evidence&kind=finding&analysis=analysis-7&finding=finding-3',
    ).searchParams.get('view')).toBe('home');
    const allowanceReturn = buildEvidenceReturnUrl(
      'http://localhost/?view=evidence&kind=allowance&analysis=allowance-7&evidence=interval-3',
    );
    expect(allowanceReturn.searchParams.get('view')).toBe('limits');
    expect(allowanceReturn.searchParams.get('analysis_id')).toBe('allowance-7');
  });
});
