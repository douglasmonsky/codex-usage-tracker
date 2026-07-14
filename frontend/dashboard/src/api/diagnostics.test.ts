import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearDiagnosticApiCache,
  loadDiagnosticFactCalls,
  loadDiagnosticFactSource,
  type DiagnosticFactRow,
} from './diagnostics';
import type { ContextRuntime } from './types';

const runtime: ContextRuntime = {
  apiToken: 'local-diagnostics-token',
  contextApiEnabled: true,
  fileMode: false,
};

const fact: DiagnosticFactRow = {
  fact_type: 'cache',
  fact_name: 'large_uncached_input',
};

afterEach(() => {
  clearDiagnosticApiCache();
  vi.unstubAllGlobals();
});

describe('diagnostics transport', () => {
  it('forwards cancellation to fact-source and fact-call requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ rows: [] }));
    vi.stubGlobal('fetch', fetchMock);
    const sourceController = new AbortController();
    const callsController = new AbortController();

    await loadDiagnosticFactSource('facts', runtime, { signal: sourceController.signal });
    await loadDiagnosticFactCalls(fact, runtime, { signal: callsController.signal });

    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ signal: sourceController.signal }));
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ signal: callsController.signal }));
  });

  it('separates compatibility cache entries by source revision', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ rows: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await loadDiagnosticFactSource('facts', runtime, { cacheKey: 'revision-1' });
    await loadDiagnosticFactSource('facts', runtime, { cacheKey: 'revision-1' });
    await loadDiagnosticFactSource('facts', runtime, { cacheKey: 'revision-2' });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function jsonResponse(payload: Record<string, unknown>): Response {
  return {
    ok: true,
    json: async () => payload,
  } as Response;
}
