import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadReportsPack } from './reports';

afterEach(() => vi.unstubAllGlobals());

describe('reports API', () => {
  it('preserves an unbounded limit and maps generation metadata', async () => {
    let requestedUrl = '';
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      requestedUrl = String(input);
      return jsonResponse({
        schema: 'codex-usage-tracker-reports-pack-v1',
        generated_at: '2026-07-11T12:00:00+00:00',
        reports: [],
        evidence: {},
        row_count: 0,
        total_matched_rows: 42,
        raw_context_included: false,
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const pack = await loadReportsPack(runtime, { limit: 0, evidenceLimit: 8 });

    expect(requestedUrl).toContain('limit=0');
    expect(pack.generatedAt).toBe('2026-07-11T12:00:00+00:00');
    expect(pack.totalMatchedRows).toBe(42);
    expect(pack.rawContextIncluded).toBe(false);
  });

  it('rejects an incompatible schema before the dashboard uses it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ schema: 'unexpected-v2' })));

    await expect(loadReportsPack(runtime)).rejects.toThrow('unsupported schema');
  });

  it('forwards cancellation to the reports request', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      schema: 'codex-usage-tracker-reports-pack-v1',
      reports: [],
      evidence: {},
    }));
    vi.stubGlobal('fetch', fetchMock);
    const controller = new AbortController();

    await loadReportsPack(runtime, { signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/reports/pack?'),
      expect.objectContaining({ signal: controller.signal }),
    );
  });
});

const runtime = { apiToken: 'local-token', contextApiEnabled: false, fileMode: false };

function jsonResponse(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}
