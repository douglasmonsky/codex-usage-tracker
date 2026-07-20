export const dashboardViewIds = [
  'overview',
  'investigator',
  'compression-lab',
  'calls',
  'call',
  'threads',
  'usage-drain',
  'cache-context',
  'diagnostics',
  'reports',
  'settings',
] as const;

export type DashboardViewId = (typeof dashboardViewIds)[number];
type DashboardHistoryScope = 'active' | 'all';

export type DashboardSearch = Record<string, unknown> & {
  view: DashboardViewId;
  history?: DashboardHistoryScope;
  record?: string;
  return?: Exclude<DashboardViewId, 'call'>;
  q?: string;
  preset?: string;
  finding?: number;
};

const dashboardViewIdSet = new Set<string>(dashboardViewIds);

export function isDashboardViewId(value: unknown): value is DashboardViewId {
  return typeof value === 'string' && dashboardViewIdSet.has(value);
}

export function normalizeDashboardView(
  value: unknown,
  fallback: DashboardViewId = 'overview',
): DashboardViewId {
  const candidate = searchString(value);
  if (candidate === 'insights') return 'overview';
  return isDashboardViewId(candidate) ? candidate : fallback;
}

export function validateDashboardSearch(input: Record<string, unknown>): DashboardSearch {
  const search: DashboardSearch = {
    ...input,
    view: normalizeDashboardView(input.view),
  };
  assignOptionalString(search, 'record', input.record);
  assignOptionalString(search, 'q', input.q);
  assignOptionalString(search, 'preset', input.preset);

  const returnView = normalizeDashboardView(input.return, 'calls');
  if (searchString(input.return) && returnView !== 'call') {
    search.return = returnView;
  } else {
    delete search.return;
  }

  const history = searchString(input.history);
  if (history === 'active' || history === 'all') {
    search.history = history;
  } else {
    delete search.history;
  }

  const finding = finiteInteger(input.finding);
  if (finding !== null && finding > 0) {
    search.finding = finding;
  } else {
    delete search.finding;
  }
  return search;
}

function assignOptionalString(
  search: Record<string, unknown>,
  key: 'record' | 'q' | 'preset',
  value: unknown,
): void {
  const normalized = searchString(value);
  if (normalized) search[key] = normalized;
  else delete search[key];
}

function searchString(value: unknown): string {
  if (Array.isArray(value)) return searchString(value[0]);
  return typeof value === 'string' ? value.trim() : '';
}

function finiteInteger(value: unknown): number | null {
  const normalized = Array.isArray(value) ? value[0] : value;
  const parsed = typeof normalized === 'number' ? normalized : Number.parseInt(searchString(normalized), 10);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}
