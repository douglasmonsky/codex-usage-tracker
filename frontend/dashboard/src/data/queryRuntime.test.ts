import { describe, expect, it, vi } from 'vitest';

import type { DashboardBootPayload } from '../api/types';
import {
  createDashboardQueryClient,
  createSyntheticUsageTransport,
  metadataFromPayload,
  queryUsageSnapshot,
  readDashboardRuntimeMetadata,
  writeDashboardRuntimeMetadata,
  type UsageTransport,
} from './queryRuntime';
import type { UsageSnapshotStore } from './usageSnapshotCache';

const shellPayload = {
  api_token: 'fixture-token',
  loaded_row_count: 0,
  payload_cache_key: 'source-a',
  payload_cache_version: 1,
  rows: [],
  total_available_rows: 2,
} satisfies DashboardBootPayload & { payload_cache_key: string; payload_cache_version: number };

describe('dashboard query runtime', () => {
  it('restores a revision-matched snapshot without calling the network transport', async () => {
    const currentPayload = {
      ...shellPayload,
      latest_refresh_at: '2026-07-10T12:00:00Z',
    };
    const cachedPayload: DashboardBootPayload = {
      ...currentPayload,
      load_window: 'all',
      limit: 500,
      loaded_row_count: 1,
      rows: [{ record_id: 'cached-call' }],
    };
    const snapshotStore: UsageSnapshotStore = {
      read: vi.fn(async () => cachedPayload),
      write: vi.fn(async () => undefined),
    };
    const load = vi.fn<UsageTransport['load']>();

    const result = await queryUsageSnapshot({
      currentPayload,
      historyScope: 'active',
      loadLimit: 500,
      loadWindow: 'all',
      queryClient: createDashboardQueryClient(),
      snapshotStore,
      transport: { kind: 'production', load },
    });

    expect(result.rows?.[0]?.record_id).toBe('cached-call');
    expect(snapshotStore.read).toHaveBeenCalledOnce();
    expect(load).not.toHaveBeenCalled();
  });

  it('deduplicates equivalent snapshot loads and refreshes explicitly', async () => {
    const loadedPayload: DashboardBootPayload = {
      ...shellPayload,
      latest_refresh_at: '2026-07-10T12:00:00Z',
      limit: 37,
      loaded_row_count: 1,
      rows: [{ record_id: 'call-1' }],
    };
    const load = vi.fn<UsageTransport['load']>(async () => loadedPayload);
    const transport: UsageTransport = { kind: 'production', load };
    const queryClient = createDashboardQueryClient();

    await queryUsageSnapshot({ currentPayload: shellPayload, historyScope: 'active', loadLimit: 37, queryClient, transport });
    await queryUsageSnapshot({ currentPayload: shellPayload, historyScope: 'active', loadLimit: 37, queryClient, transport });
    expect(load).toHaveBeenCalledTimes(1);

    await queryUsageSnapshot({ currentPayload: loadedPayload, historyScope: 'active', loadLimit: 37, queryClient, refresh: true, transport });
    expect(load).toHaveBeenCalledTimes(2);
    expect(load.mock.calls[1]?.[1]).toMatchObject({ includeArchived: false, limit: 37, refresh: true });
  });

  it('does not reuse an in-memory snapshot after the source revision changes', async () => {
    const queryClient = createDashboardQueryClient();
    const load = vi.fn<UsageTransport['load']>(async currentPayload => ({
      ...shellPayload,
      latest_refresh_at: currentPayload?.latest_refresh_at,
      limit: 37,
      loaded_row_count: 1,
      rows: [{ record_id: currentPayload?.latest_refresh_at }],
    }));
    const transport: UsageTransport = { kind: 'production', load };

    await queryUsageSnapshot({
      currentPayload: { ...shellPayload, latest_refresh_at: 'revision-a' },
      historyScope: 'active',
      loadLimit: 37,
      queryClient,
      transport,
    });
    const next = await queryUsageSnapshot({
      currentPayload: { ...shellPayload, latest_refresh_at: 'revision-b' },
      historyScope: 'active',
      loadLimit: 37,
      queryClient,
      transport,
    });

    expect(load).toHaveBeenCalledTimes(2);
    expect(next.rows?.[0]?.record_id).toBe('revision-b');
  });

  it('passes an abort signal through the transport', async () => {
    const queryClient = createDashboardQueryClient();
    let requestSignal: AbortSignal | undefined;
    const transport: UsageTransport = {
      kind: 'production',
      load: async (_payload, request) => {
        requestSignal = request.signal;
        return new Promise((_resolve, reject) => {
          request.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        });
      },
    };
    const pending = queryUsageSnapshot({ currentPayload: shellPayload, historyScope: 'all', loadLimit: 0, queryClient, transport });
    await vi.waitFor(() => expect(requestSignal).toBeDefined());
    await queryClient.cancelQueries({ queryKey: ['usage'] });
    await expect(pending).rejects.toBeDefined();
    expect(requestSignal?.aborted).toBe(true);
  });

  it('persists only bounded revision and scope metadata', () => {
    window.sessionStorage.clear();
    const metadata = metadataFromPayload(shellPayload, {
      historyScope: 'all',
      loadWindow: 'all',
      limit: null,
      since: null,
    });
    writeDashboardRuntimeMetadata(metadata);
    expect(readDashboardRuntimeMetadata()).toEqual(metadata);
    const serialized = window.sessionStorage.getItem('codexUsageDashboardRuntimeMetadata') ?? '';
    expect(serialized).not.toContain('rows');
    expect(serialized.length).toBeLessThan(2_048);
  });

  it('keeps synthetic data behind an explicit provider', async () => {
    const transport = createSyntheticUsageTransport(shellPayload);
    expect(transport.kind).toBe('synthetic');
    await expect(transport.load(null, {})).resolves.toBe(shellPayload);
  });
});
