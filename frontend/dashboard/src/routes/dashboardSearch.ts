import { evidenceConsoleRouteIds, exploreModes, type ExploreMode } from './evidenceConsoleRoutes';
import {
  legacyCompatibilityRouteIds,
  normalizeDashboardRouteInput,
} from './legacyRouteAliases';

export const dashboardViewIds = [
  ...evidenceConsoleRouteIds,
  ...legacyCompatibilityRouteIds,
] as const;

export type DashboardViewId = (typeof dashboardViewIds)[number];
type DashboardHistoryScope = 'active' | 'all';

export type DashboardSearch = Record<string, unknown> & {
  view: DashboardViewId;
  history?: DashboardHistoryScope;
  kind?: 'call' | 'thread' | 'finding' | 'allowance' | 'analysis' | 'none';
  mode?: string;
  record?: string;
  return?: Exclude<DashboardViewId, 'call' | 'evidence'>;
  return_mode?: ExploreMode;
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
  fallback: DashboardViewId = 'home',
): DashboardViewId {
  return normalizeDashboardRouteInput(searchString(value))?.view
    ?? normalizeDashboardRouteInput(fallback)?.view
    ?? 'home';
}

export function validateDashboardSearch(input: Record<string, unknown>): DashboardSearch {
  const normalizedRoute = normalizeDashboardRouteInput(searchString(input.view))
    ?? { view: 'home' as const, params: {} };
  const search: DashboardSearch = {
    ...input,
    ...normalizedRoute.params,
    view: normalizedRoute.view,
  };
  assignOptionalString(search, 'record', input.record);
  assignOptionalString(search, 'q', input.q);
  assignOptionalString(search, 'preset', input.preset);

  const returnRoute = normalizeDashboardRouteInput(searchString(input.return));
  if (returnRoute && returnRoute.view !== 'evidence') {
    search.return = returnRoute.view;
    if (returnRoute.params.mode === 'calls' || returnRoute.params.mode === 'threads') {
      search.return_mode = returnRoute.params.mode;
    }
  } else {
    delete search.return;
    delete search.return_mode;
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

export function exploreModeFromSearch(search = window.location.search): ExploreMode {
  const params = new URLSearchParams(search);
  const legacyMode = normalizeDashboardRouteInput(params.get('view'))?.params.mode;
  if (legacyMode === 'calls' || legacyMode === 'threads') return legacyMode;
  const mode = params.get('mode');
  return (exploreModes as readonly string[]).includes(mode ?? '') ? mode as ExploreMode : 'calls';
}

export function evidenceKindFromSearch(
  search = window.location.search,
): NonNullable<DashboardSearch['kind']> {
  const kind = new URLSearchParams(search).get('kind');
  return kind === 'thread' || kind === 'finding' || kind === 'allowance' || kind === 'analysis'
    ? kind
    : kind === 'none'
      ? 'none'
      : 'call';
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
