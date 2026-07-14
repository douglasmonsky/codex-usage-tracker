import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ContextRuntime } from './types';
import {
  clearDiagnosticSnapshotCache,
  loadDiagnosticSnapshot,
  type DiagnosticSnapshotKey,
  type DiagnosticSnapshotPayload,
} from './diagnosticSnapshots';

const runtime: ContextRuntime = {
  apiToken: 'private-diagnostics-token',
  contextApiEnabled: false,
  fileMode: false,
};

type SnapshotLoader = (
  key: DiagnosticSnapshotKey,
  runtime: ContextRuntime,
  options: { cacheKey?: string; signal?: AbortSignal },
) => Promise<DiagnosticSnapshotPayload>;

const loadSnapshot = loadDiagnosticSnapshot as SnapshotLoader;

afterEach(() => {
  clearDiagnosticSnapshotCache();
  vi.restoreAllMocks();
});

describe('diagnostic snapshot transport', () => {
  it('forwards cancellation to the snapshot request', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ status: 'ready' }));

    await loadSnapshot('overview', runtime, {
      cacheKey: 'revision-1',
      signal: controller.signal,
    });

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it('does not reuse a diagnostic snapshot across source revisions', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ status: 'first' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'second' }));

    await expect(loadSnapshot('overview', runtime, { cacheKey: 'revision-1' }))
      .resolves.toMatchObject({ status: 'first' });
    await expect(loadSnapshot('overview', runtime, { cacheKey: 'revision-2' }))
      .resolves.toMatchObject({ status: 'second' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function jsonResponse(payload: unknown): Response {
  return { ok: true, json: async () => payload } as Response;
}
