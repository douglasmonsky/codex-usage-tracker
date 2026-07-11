import { isCancelledError, QueryClient } from '@tanstack/react-query';

import {
  loadUsagePayload,
  type RefreshProgressPayload,
  type UsagePayloadRequest,
} from '../api/client';
import type { DashboardBootPayload } from '../api/types';
import {
  dataScopeFromCompatibilityLimit,
  loadLimitFromPayload,
  requestLimitForDataScope,
  type DataScope,
  type HistoryScope,
} from './dataScope';
import { isAbortError } from './httpTransportSupport';

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
  loadLimit: number;
  onProgress?: (progress: RefreshProgressPayload) => void;
  queryClient?: QueryClient;
  refresh?: boolean;
  transport?: UsageTransport;
};

const metadataStorageKey = 'codexUsageDashboardRuntimeMetadata';
const metadataMaxBytes = 2_048;
const usageStaleTimeMs = 30_000;

const usageQueryKeys = {
  all: ['usage'] as const,
  snapshot: (sourceKey: string, scope: DataScope) =>
    [...usageQueryKeys.all, 'snapshot', sourceKey, scope.historyScope, scope.limit] as const,
};

export function createDashboardQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 15 * 60_000,
        refetchOnReconnect: false,
        refetchOnWindowFocus: false,
        retry: 1,
        staleTime: usageStaleTimeMs,
      },
    },
  });
}

export const dashboardQueryClient = createDashboardQueryClient();

export async function queryUsageSnapshot({
  currentPayload,
  historyScope,
  loadLimit,
  onProgress,
  queryClient = dashboardQueryClient,
  refresh = false,
  transport = productionUsageTransport,
}: UsageQueryRequest): Promise<DashboardBootPayload> {
  const scope = dataScopeFromCompatibilityLimit(loadLimit, historyScope);
  const sourceKey = payloadSourceKey(currentPayload);
  const queryKey = usageQueryKeys.snapshot(sourceKey, scope);

  if (!queryClient.getQueryData(queryKey) && payloadMatchesScope(currentPayload, scope)) {
    queryClient.setQueryData(queryKey, currentPayload);
  }
  if (refresh) {
    await queryClient.invalidateQueries({ queryKey, exact: true });
  }

  const payload = await queryClient.fetchQuery({
    queryKey,
    queryFn: ({ signal }) =>
      transport.load(currentPayload, {
        refresh,
        limit: requestLimitForDataScope(scope),
        includeArchived: scope.historyScope === 'all',
        onProgress,
        signal,
      }),
    staleTime: refresh ? 0 : usageStaleTimeMs,
  });
  writeDashboardRuntimeMetadata(metadataFromPayload(payload, scope));
  return payload;
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
  const payloadHistory = payload.include_archived || payload.history_scope === 'all-history' ? 'all' : 'active';
  return limitMatches && payloadHistory === scope.historyScope;
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

function isDataScope(value: unknown): value is DataScope {
  if (!value || typeof value !== 'object') return false;
  const scope = value as Partial<DataScope>;
  const limitValid = scope.limit === null || (typeof scope.limit === 'number' && Number.isFinite(scope.limit) && scope.limit > 0);
  return limitValid && (scope.historyScope === 'active' || scope.historyScope === 'all');
}

function sessionStorageOrNull(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}
