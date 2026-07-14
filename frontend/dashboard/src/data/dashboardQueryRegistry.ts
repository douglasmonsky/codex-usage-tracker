import type { DataScope, HistoryScope, LoadWindow } from './dataScope';

export type DashboardQueryModule =
  | 'usage-snapshot'
  | 'overview-summary'
  | 'overview-recommendations'
  | 'calls'
  | 'threads'
  | 'thread-calls'
  | 'investigator-agentic'
  | 'investigator-snapshot'
  | 'investigator-walk'
  | 'diagnostics-facts'
  | 'reports';

export type DashboardQuerySource = {
  sourceKey: string;
  sourceRevision: string;
};

export type DashboardQueryScope = Partial<DataScope> & {
  historyScope?: HistoryScope;
  loadWindow?: LoadWindow;
};

export type DashboardQueryDataClass =
  | 'snapshot'
  | 'aggregate'
  | 'detail'
  | 'heavyJob'
  | 'userAction';

export type DashboardModuleState = 'waiting' | 'loading' | 'ready' | 'updating' | 'error';

type DashboardQueryPolicy = {
  staleTime: number;
  gcTime: number;
  retry: number;
  refetchOnReconnect: false;
  refetchOnWindowFocus: false;
  cancellation: 'observer' | 'shared-job';
  persistedCache: 'aggregate-only' | 'none';
};

const standardGcTime = 15 * 60_000;
const standardStaleTime = 30_000;

export const dashboardQueryPolicies: Record<DashboardQueryDataClass, DashboardQueryPolicy> = {
  snapshot: queryPolicy({ persistedCache: 'aggregate-only' }),
  aggregate: queryPolicy({ persistedCache: 'aggregate-only' }),
  detail: queryPolicy(),
  heavyJob: queryPolicy({ cancellation: 'shared-job', staleTime: 1_000 }),
  userAction: queryPolicy({ retry: 0, staleTime: 0 }),
};

export function dashboardQuerySource({
  sourceKey,
  sourceRevision,
}: {
  sourceKey?: string | null;
  sourceRevision?: string | null;
}): DashboardQuerySource {
  return {
    sourceKey: normalizedIdentityPart(sourceKey, 'local-api'),
    sourceRevision: normalizedIdentityPart(sourceRevision, 'unversioned'),
  };
}

export function dashboardQueryKey(
  module: DashboardQueryModule,
  source: DashboardQuerySource,
  scope: DashboardQueryScope = {},
  ...parts: readonly unknown[]
) {
  return [
    'dashboard',
    module,
    source.sourceKey,
    source.sourceRevision,
    normalizedScope(scope),
    ...parts,
  ] as const;
}

export function dashboardQueryPrefix(module: DashboardQueryModule) {
  return ['dashboard', module] as const;
}

export function dashboardQueryOptions(dataClass: DashboardQueryDataClass) {
  const policy = dashboardQueryPolicies[dataClass];
  return {
    gcTime: policy.gcTime,
    refetchOnReconnect: policy.refetchOnReconnect,
    refetchOnWindowFocus: policy.refetchOnWindowFocus,
    retry: policy.retry,
    staleTime: policy.staleTime,
  };
}

export function deriveDashboardModuleState({
  enabled,
  hasData,
  isError,
  isFetching,
  isPending,
}: {
  enabled: boolean;
  hasData: boolean;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
}): DashboardModuleState {
  if (!enabled) return 'waiting';
  if (hasData) return isFetching ? 'updating' : 'ready';
  if (isError) return 'error';
  if (isFetching || isPending) return 'loading';
  return 'waiting';
}

export function dashboardModuleProgress(states: readonly DashboardModuleState[]) {
  const ready = states.filter(state => state === 'ready' || state === 'updating').length;
  const total = states.length;
  return {
    ready,
    total,
    percent: total === 0 ? 100 : Math.round((ready / total) * 100),
    loading: states.filter(state => state === 'loading').length,
    errors: states.filter(state => state === 'error').length,
  };
}

function normalizedScope(scope: DashboardQueryScope) {
  return {
    historyScope: scope.historyScope ?? 'active',
    loadWindow: scope.loadWindow ?? 'all',
    limit: scope.limit ?? null,
    since: scope.since ?? '',
  };
}

function normalizedIdentityPart(value: string | null | undefined, fallback: string): string {
  return value?.trim() || fallback;
}

function queryPolicy(overrides: Partial<DashboardQueryPolicy> = {}): DashboardQueryPolicy {
  return {
    staleTime: standardStaleTime,
    gcTime: standardGcTime,
    retry: 1,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
    cancellation: 'observer',
    persistedCache: 'none',
    ...overrides,
  };
}
