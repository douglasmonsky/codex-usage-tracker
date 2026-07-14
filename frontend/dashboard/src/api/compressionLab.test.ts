import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  loadCompressionProfile,
  runCompressionAnalysis,
  type CompressionApiPayload,
} from './compressionLab';

const runtime = { apiToken: 'private-compression-token', contextApiEnabled: false, fileMode: false };
const scope = { includeArchived: true, since: '2026-07-01T00:00:00Z' };

afterEach(() => vi.restoreAllMocks());

describe('Compression Lab dashboard transport', () => {
  it('returns the shared structured missing-profile payload', async () => {
    const missing = compressionPayload('profile', 'error', 0);
    missing.error = { code: 'compression_run_not_found', message: 'No profile.' };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(missing, 404));

    await expect(loadCompressionProfile(runtime, scope)).resolves.toEqual(missing);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/compression\/profile\?.*include_archived=1.*since=/),
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Codex-Usage-Token': 'private-compression-token' }),
      }),
    );
  });

  it('starts, polls, and reloads the exact completed shared profile', async () => {
    const progress: CompressionApiPayload[] = [];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith('/api/compression/start?')) {
        expect(init?.method).toBe('POST');
        return jsonResponse(compressionPayload('status', 'running', 25));
      }
      if (url.startsWith('/api/compression/status?')) {
        return jsonResponse(compressionPayload('status', 'completed', 100));
      }
      if (url.startsWith('/api/compression/profile?')) {
        const profile = compressionPayload('profile', 'completed', 100);
        profile.profile = { candidate_count: 7 };
        return jsonResponse(profile);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const profile = await runCompressionAnalysis(runtime, scope, {
      pollIntervalMs: 0,
      onProgress: payload => progress.push(payload),
    });

    expect(profile.kind).toBe('profile');
    expect(profile.profile).toEqual({ candidate_count: 7 });
    expect(progress.map(payload => payload.progress?.percent)).toEqual([25, 100]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[2][0])).toContain('run_id=compression-1');
  });

  it('stops local polling on abort without issuing a server cancellation', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(compressionPayload('status', 'running', 10)),
    );

    const running = runCompressionAnalysis(runtime, scope, {
      signal: controller.signal,
      pollIntervalMs: 10_000,
    });
    await Promise.resolve();
    controller.abort();

    await expect(running).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
  });
});

function compressionPayload(
  kind: 'status' | 'profile',
  status: 'running' | 'completed' | 'error',
  percent: number,
): CompressionApiPayload {
  return {
    schema: 'codex-usage-tracker-compression-api-v1',
    kind,
    run_id: 'compression-1',
    status,
    source_revision: 'generation:5',
    scope: { include_archived: true },
    coverage: {},
    cache: { reused: false, mode: null, request_reused: 'none' },
    progress: {
      percent,
      stage: status === 'completed' ? 'completed' : 'detectors',
      current_detector: status === 'running' ? 'stale_context' : null,
      completed_detectors: status === 'completed' ? 6 : 1,
      total_detectors: 6,
      records_examined: 100,
      candidate_count: 7,
    },
    error: null,
    next: status === 'running'
      ? { tool: 'usage_compression_status', arguments: { run_id: 'compression-1' }, poll_after_ms: 250 }
      : { tool: 'usage_compression_profile', arguments: { run_id: 'compression-1' } },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}
