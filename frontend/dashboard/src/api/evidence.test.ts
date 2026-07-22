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
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      selector_kind: 'finding',
      selector_id: 'finding-3',
      analysis_id: 'analysis-7',
      section: 'summary',
      limit: '20',
      history: 'all',
    });
    expect(init).toMatchObject({
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Codex-Usage-Token': 'local-token' },
    });
    expect(payload.data_class).toBe('aggregate');
  });

  it('does not send the contextual allowance analysis as an unsupported evidence qualifier', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(successPayload('allowance')));
    vi.stubGlobal('fetch', fetchMock);

    await loadEvidence({
      kind: 'allowance',
      selectorId: 'interval-3',
      analysisId: 'allowance-7',
    }, runtime);

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(url.searchParams.has('analysis_id')).toBe(false);
  });

  it('preserves recoverable server error codes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      error: 'call evidence not found: record-9',
      code: 'evidence_not_found',
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
    schema: 'codex-usage-tracker.mcp-envelope.v1',
    tool: 'usage_evidence',
    request_id: 'req-00000000000000000000000000000000',
    generated_at: '2026-07-21T12:00:00Z',
    source_revision: 'generation:7',
    data_class: 'aggregate',
    scope: { history: 'active', privacy_mode: 'normal', filters: {} },
    result_schema: 'codex-usage-tracker.evidence-result.v1',
    result: {
      schema: 'codex-usage-tracker.evidence-result.v1',
      selector: { kind, id: 'selector-1', section: 'summary' },
      records: [],
      next_cursor: null,
      dashboard_target: {},
      subject: null,
    },
  };
}

function jsonResponse(payload: object, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
