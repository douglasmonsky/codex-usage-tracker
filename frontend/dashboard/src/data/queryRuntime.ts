import { isCancelledError, QueryClient } from '@tanstack/react-query';

import {
  loadUsagePayload,
  type RefreshProgressPayload,
  type UsagePayloadRequest,
} from '../api/client';
import type { DashboardBootPayload } from '../api/types';
import {
  dataScopeFromCompatibilityLimit,
  currentLoadWindowFromPayload,
  loadLimitFromPayload,
  requestLimitForDataScope,
  type DataScope,
  type HistoryScope,
  type LoadWindow,
} from './dataScope';
import {
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQueryPolicies,
  dashboardQueryPrefix,
  dashboardQuerySource,
} from './dashboardQueryRegistry';
import { isAbortError } from './httpTransportSupport';
import {
  persistentUsageSnapshotStore,
  type UsageSnapshotIdentity,
  type UsageSnapshotStore,
} from './usageSnapshotCache';

export type UsageTransport = {
  kind: 'production' | 'synthetic';
  load: (
    currentPayload: DashboardBootPayload | null,
    request: UsagePayloadRequest,
  ) => Promise<DashboardBootPayload>;
};

const productionUsageTransport: UsageTransport = {
  kind: 'production',
  load: loadUsagePayload,
};

export function createSyntheticUsageTransport(payload: DashboardBootPayload): UsageTransport {
  return { kind: 'synthetic', load: async () => payload };
}

export type DashboardRuntimeMetadata = {
  schema: 'codex-usage-dashboard-runtime-v1';
  sourceKey: string;
  sourceRevision: string;
  scope: DataScope;
  updatedAt: number;
};

type UsageQueryRequest = {
  currentPayload: DashboardBootPayload | null;
  historyScope: HistoryScope;
  loadWindow?: LoadWindow;
  loadLimit: number;
  since?: string | null;
  onProgress?: (progress: RefreshProgressPayload) => void;
  queryClient?: QueryClient;
  refresh?: boolean;
  transport?: UsageTransport;
  snapshotStore?: UsageSnapshotStore;
};

const metadataStorageKey = 'codexUsageDashboardRuntimeMetadata';
const metadataMaxBytes = 2_048;

const usageQueryKeys = {
  all: dashboardQueryPrefix('usage-snapshot'),
  snapshot: (sourceKey: string, sourceRevision: string, scope: DataScope) =>
    dashboardQueryKey(
      'usage-snapshot',
      dashboardQuerySource({ sourceKey, sourceRevision }),
      scope,
    ),
};

export function createDashboardQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        ...dashboardQueryOptions('aggregate'),
      },
    },
  });
}

export const dashboardQueryClient = createDashboardQueryClient();

export async function queryUsageSnapshot({
  currentPayload,
  historyScope,
  loadWindow,
  loadLimit,
  since = null,
  onProgress,
  queryClient = dashboardQueryClient,
  refresh = false,
  snapshotStore = persistentUsageSnapshotStore,
  transport = productionUsageTransport,
}: UsageQueryRequest): Promise<DashboardBootPayload> {
  const scope = dataScopeFromCompatibilityLimit(loadLimit, historyScope, since, loadWindow);
  const sourceKey = payloadSourceKey(currentPayload);
  const queryKey = usageQueryKeys.snapshot(sourceKey, payloadSourceRevision(currentPayload), scope);

  if (!queryClient.getQueryData(queryKey) && payloadMatchesScope(currentPayload, scope)) {
    queryClient.setQueryData(queryKey, currentPayload);
  }
  if (refresh) {
    await queryClient.invalidateQueries({ queryKey, exact: true });
  }

  const cacheIdentity = usageSnapshotIdentity(currentPayload, scope);
  const payload = await queryClient.fetchQuery({
    queryKey,
    ...dashboardQueryOptions('snapshot'),
    queryFn: async ({ signal }) => {
      const cachedPayload = !refresh && cacheIdentity
        ? await snapshotStore.read(cacheIdentity)
        : null;
      if (cachedPayload) {
        onProgress?.({
          status: 'completed',
          phase: 'loading_rows',
          message: 'Loaded cached dashboard snapshot',
          completed: Number(cachedPayload.loaded_row_count ?? cachedPayload.rows?.length ?? 0),
          total: Number(cachedPayload.total_available_rows ?? cachedPayload.loaded_row_count ?? 0),
          percent: 100,
        });
        return cachedPayload;
      }
      const loadedPayload = await transport.load(currentPayload, {
        refresh,
        limit: requestLimitForDataScope(scope),
        includeArchived: scope.historyScope === 'all',
        loadWindow,
        since: scope.since,
        onProgress,
        signal,
      });
      const loadedIdentity = cacheIdentity
        ? {
            ...cacheIdentity,
            sourceRevision: String(loadedPayload.latest_refresh_at ?? cacheIdentity.sourceRevision),
          }
        : usageSnapshotIdentity(loadedPayload, scope);
      if (loadedIdentity) await snapshotStore.write(loadedIdentity, loadedPayload);
      return loadedPayload;
    },
    staleTime: refresh ? 0 : dashboardQueryPolicies.snapshot.staleTime,
  });
  writeDashboardRuntimeMetadata(metadataFromPayload(payload, scope));
  return payload;
}

function usageSnapshotIdentity(
  payload: DashboardBootPayload | null,
  scope: DataScope,
): UsageSnapshotIdentity | null {
  if (!payload?.api_token) return null;
  const sourceRevision = String(payload.latest_refresh_at ?? '');
  if (!sourceRevision) return null;
  return { sourceKey: payloadSourceKey(payload), sourceRevision, scope };
}

export async function cancelUsageQueries(queryClient = dashboardQueryClient): Promise<void> {
  await queryClient.cancelQueries({ queryKey: usageQueryKeys.all });
}

export function isUsageQueryCancelled(error: unknown): boolean {
  return isCancelledError(error) || isAbortError(error);
}

export function metadataFromPayload(payload: DashboardBootPayload, scope: DataScope): DashboardRuntimeMetadata {
  return {
    schema: 'codex-usage-dashboard-runtime-v1',
    sourceKey: payloadSourceKey(payload),
    sourceRevision: String(payload.latest_refresh_at ?? ''),
    scope,
    updatedAt: Date.now(),
  };
}

export function readDashboardRuntimeMetadata(storage = sessionStorageOrNull()): DashboardRuntimeMetadata | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(metadataStorageKey);
    if (!raw || raw.length > metadataMaxBytes) return null;
    const parsed = JSON.parse(raw) as Partial<DashboardRuntimeMetadata>;
    if (
      parsed.schema !== 'codex-usage-dashboard-runtime-v1' ||
      typeof parsed.sourceKey !== 'string' ||
      typeof parsed.sourceRevision !== 'string' ||
      typeof parsed.updatedAt !== 'number' ||
      !isDataScope(parsed.scope)
    ) {
      return null;
    }
    return parsed as DashboardRuntimeMetadata;
  } catch {
    return null;
  }
}

export function writeDashboardRuntimeMetadata(
  metadata: DashboardRuntimeMetadata,
  storage = sessionStorageOrNull(),
): void {
  if (!storage) return;
  try {
    const serialized = JSON.stringify(metadata);
    if (serialized.length <= metadataMaxBytes) storage.setItem(metadataStorageKey, serialized);
  } catch {
    // Storage can be disabled in private or embedded browser contexts.
  }
}

function payloadMatchesScope(payload: DashboardBootPayload | null, scope: DataScope): payload is DashboardBootPayload {
  if (!payload || !(payload.rows?.length ?? 0)) return false;
  const payloadLimit = loadLimitFromPayload(payload);
  const limitMatches = scope.limit === null ? payloadLimit === 0 : payloadLimit === scope.limit;
  const sinceMatches = (payload.since ?? null) === scope.since;
  const loadWindowMatches = currentLoadWindowFromPayload(payload) === scope.loadWindow;
  const payloadHistory = payload.include_archived || payload.history_scope === 'all-history' ? 'all' : 'active';
  return limitMatches && sinceMatches && loadWindowMatches && payloadHistory === scope.historyScope;
}

function payloadSourceKey(payload: DashboardBootPayload | null): string {
  const cacheAwarePayload = payload as (DashboardBootPayload & {
    payload_cache_key?: string;
    payload_cache_version?: number;
  }) | null;
  const version = Number(cacheAwarePayload?.payload_cache_version ?? 0);
  const key = String(cacheAwarePayload?.payload_cache_key ?? (payload?.api_token ? 'live' : 'static'));
  return `${version}:${key}`;
}

function payloadSourceRevision(payload: DashboardBootPayload | null): string {
  return String(payload?.latest_refresh_at ?? 'unversioned');
}

function isDataScope(value: unknown): value is DataScope {
  if (!value || typeof value !== 'object') return false;
  const scope = value as Partial<DataScope>;
  const limitValid = scope.limit === null || (typeof scope.limit === 'number' && Number.isFinite(scope.limit) && scope.limit > 0);
  const sinceValid = scope.since === null || typeof scope.since === 'string';
  const loadWindowValid = scope.loadWindow === 'day' || scope.loadWindow === 'week' || scope.loadWindow === 'rows' || scope.loadWindow === 'all';
  return limitValid && sinceValid && loadWindowValid && (scope.historyScope === 'active' || scope.historyScope === 'all');
}

function sessionStorageOrNull(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}
