import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadEvidence } from './evidence';

const runtime = { apiToken: 'local-token', contextApiEnabled: false, fileMode: false };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('evidence API client', () => {
  it('posts one bounded finding request with its exact analysis qualifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(successPayload()));
    vi.stubGlobal('fetch', fetchMock);

    const payload = await loadEvidence({
      kind: 'finding',
      selectorId: 'finding-3',
      analysisId: 'analysis-7',
      history: 'all',
    }, runtime);

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(String(input), 'http://localhost');
    expect(url.pathname).toBe('/api/v2/evidence');
    expect(url.search).toBe('');
    expect(JSON.parse(String(init.body))).toEqual({
      selector_kind: 'finding',
      selector_id: 'finding-3',
      analysis_id: 'analysis-7',
      section: 'summary',
      limit: 20,
      history: 'all',
    });
    expect(init).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-Codex-Usage-Token': 'local-token',
      },
    });
    expect(payload.schema).toBe('codex-usage-tracker.evidence-result.v1');
  });

  it('does not send the contextual allowance analysis as an unsupported evidence qualifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(successPayload('allowance')));
    vi.stubGlobal('fetch', fetchMock);

    await loadEvidence({
      kind: 'allowance',
      selectorId: 'interval-3',
      analysisId: 'allowance-7',
    }, runtime);

    const request = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(request).not.toHaveProperty('analysis_id');
  });

  it('preserves recoverable server error codes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      schema: 'codex-usage-tracker.error.v1',
      error: {
        message: 'call evidence not found: record-9',
        code: 'evidence_not_found',
      },
    }, 404)));

    await expect(loadEvidence({ kind: 'call', selectorId: 'record-9' }, runtime)).rejects.toMatchObject({
      name: 'EvidenceApiError',
      status: 404,
      code: 'evidence_not_found',
    });
  });
});

function successPayload(kind = 'finding') {
  return {
    schema: 'codex-usage-tracker.evidence-result.v1',
    selector: { kind, id: 'selector-1', section: 'summary' },
    records: [],
    next_cursor: null,
    dashboard_target: {},
    subject: null,
  };
}

function jsonResponse(payload: object, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
