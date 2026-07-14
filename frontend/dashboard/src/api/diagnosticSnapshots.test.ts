import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ContextRuntime } from './types';
import {
  clearDiagnosticSnapshotCache,
  loadDiagnosticSnapshot,
  refreshDiagnosticSnapshot,
  refreshDiagnosticSnapshots,
  diagnosticSnapshotDefinitions,
  type DiagnosticRefreshJob,
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

  it('polls async full refresh progress before reloading persisted snapshots', async () => {
    const progress: DiagnosticRefreshJob[] = [];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = String(input);
      if (url.startsWith('/api/diagnostics/refresh?')) {
        return jsonResponse(refreshJob('running', 2, 10));
      }
      if (url.startsWith('/api/diagnostics/refresh/status?')) {
        return jsonResponse(refreshJob('completed', 10, 10));
      }
      const definition = diagnosticSnapshotDefinitions.find(candidate => url.startsWith(`${candidate.path}?`));
      if (definition) return jsonResponse({ status: 'ready', section: definition.key });
      throw new Error(`Unexpected request: ${url}`);
    });

    const refreshed = await refreshDiagnosticSnapshots(runtime, {
      pollIntervalMs: 0,
      onProgress: job => progress.push(job),
    });

    expect(progress.map(job => job.progress.completed_units)).toEqual([2, 10]);
    expect(Object.keys(refreshed)).toHaveLength(diagnosticSnapshotDefinitions.length);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes('/refresh/status?'))).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/diagnostics/') && !String(input).includes('/refresh')))
      .toHaveLength(diagnosticSnapshotDefinitions.length);
  });

  it('polls one async section refresh and reloads only that persisted snapshot', async () => {
    const definition = diagnosticSnapshotDefinitions[2];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = String(input);
      if (url.startsWith(`${definition.refreshPath}?`)) return jsonResponse(refreshJob('running', 0, 1));
      if (url.startsWith('/api/diagnostics/refresh/status?')) return jsonResponse(refreshJob('completed', 1, 1));
      if (url.startsWith(`${definition.path}?`)) return jsonResponse({ status: 'ready', section: definition.key });
      throw new Error(`Unexpected request: ${url}`);
    });

    await expect(refreshDiagnosticSnapshot(definition, runtime, { pollIntervalMs: 0 }))
      .resolves.toMatchObject({ status: 'ready', section: 'commands' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

function refreshJob(status: 'running' | 'completed', completed: number, total: number): DiagnosticRefreshJob {
  return {
    schema: 'codex-usage-tracker-analysis-job-v1',
    job_id: 'analysis-test',
    job_kind: 'diagnostic-refresh',
    status,
    stage: status === 'completed' ? 'complete' : 'persisting_snapshots',
    source_revision: 'generation:4',
    updated_at: '2026-07-14T00:00:00Z',
    progress: {
      completed_units: completed,
      total_units: total,
      percent: total ? completed / total * 100 : null,
      current_unit: status === 'completed' ? null : 'commands',
    },
    error: null,
    next: status === 'completed'
      ? { action: 'reload_persisted_results' }
      : { action: 'poll', job_id: 'analysis-test', poll_after_ms: 250 },
  };
}

function jsonResponse(payload: unknown): Response {
  return { ok: true, json: async () => payload } as Response;
}
