import { afterEach, describe, expect, it, vi } from 'vitest';

import { enableContextApi, loadCallContext, type ContextRequestOptions } from './context';
import type { ContextRuntime } from './types';

const contextOptions: ContextRequestOptions = {
  includeToolOutput: false,
  includeCompactionHistory: false,
  maxChars: 8_000,
  maxEntries: 20,
  mode: 'quick',
};

function runtime(overrides: Partial<ContextRuntime> = {}): ContextRuntime {
  return {
    apiToken: 'local-token',
    contextApiEnabled: true,
    fileMode: false,
    ...overrides,
  };
}

function jsonResponse(payload: Record<string, unknown>, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as Response;
}

describe('context API client guards', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('does not attempt raw-context requests from static file mode', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadCallContext('record-1', runtime({ fileMode: true }), contextOptions)).rejects.toThrow(
      'Context loading requires the localhost dashboard server.',
    );
    await expect(enableContextApi(runtime({ fileMode: true }))).rejects.toThrow(
      'Context loading requires the localhost dashboard server.',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not attempt raw-context requests without a local API token', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadCallContext('record-1', runtime({ apiToken: '' }), contextOptions)).rejects.toThrow(
      'Context loading requires a localhost dashboard API token.',
    );
    await expect(enableContextApi(runtime({ apiToken: '' }))).rejects.toThrow(
      'Context loading requires a localhost dashboard API token.',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires explicit context API enablement before loading selected-turn evidence', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      loadCallContext('record-1', runtime({ contextApiEnabled: false }), contextOptions),
    ).rejects.toThrow('Context API is not enabled.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('enables context API through same-origin settings endpoint with local token header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ context_api_enabled: true }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(enableContextApi(runtime({ contextApiEnabled: false }))).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/^\/api\/context-settings\?/);
    expect(url).toContain('enabled=1');
    expect(init).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          Accept: 'application/json',
          'X-Codex-Usage-Token': 'local-token',
        }),
      }),
    );
  });

  it('loads selected-turn evidence through same-origin context endpoint with local token header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        schema: 'codex-usage-tracker-context-v1',
        loaded_on_demand: true,
        raw_context_persisted: false,
        record_id: 'record-1',
        entries: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadCallContext('record-1', runtime(), contextOptions)).resolves.toMatchObject({
      loaded_on_demand: true,
      raw_context_persisted: false,
      record_id: 'record-1',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/^\/api\/context\?/);
    expect(url).toContain('record_id=record-1');
    expect(url).toContain('include_tool_output=0');
    expect(url).toContain('include_compaction_history=0');
    expect(init).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          Accept: 'application/json',
          'X-Codex-Usage-Token': 'local-token',
        }),
      }),
    );
  });
});
