import { isViewId, type ViewId } from './navigation';
import { routeCatalog, routeDefinition } from './routeCatalog';
import type { HistoryScope } from '../data/dataScope';
import { normalizeDashboardRouteInput } from '../routes/legacyRouteAliases';

export type { HistoryScope } from '../data/dataScope';

function isCallReturnViewId(value: string | null): value is ViewId {
  return isViewId(value) && value !== 'call' && value !== 'evidence';
}

export function viewFromUrlParam(value: string | null, fallback: ViewId = 'home'): ViewId {
  return normalizeDashboardRouteInput(value)?.view
    ?? normalizeDashboardRouteInput(fallback)?.view
    ?? 'home';
}

export function callReturnViewFromSearch(search = window.location.search, fallback: ViewId = 'explore'): ViewId {
  const requestedView = new URLSearchParams(search).get('return');
  const normalizedView = viewFromUrlParam(requestedView, fallback);
  return isCallReturnViewId(normalizedView) ? normalizedView : fallback;
}

export function hasCallReturnViewParam(search = window.location.search): boolean {
  return new URLSearchParams(search).has('return');
}

export function callReturnViewLabel(view: ViewId): string {
  return routeDefinition(view).label;
}

export function historyScopeFromUrl(fallback: HistoryScope, search = window.location.search): HistoryScope {
  return new URLSearchParams(search).get('history') === 'all' ? 'all' : fallback;
}

export function historyScopeUrl(historyScope: HistoryScope, href = window.location.href): URL {
  const url = new URL(href);
  if (historyScope === 'all') {
    url.searchParams.set('history', 'all');
  } else {
    url.searchParams.delete('history');
  }
  return url;
}

export function clearInactiveViewSearchParams(url: URL, activeView: ViewId, preservedViews: ViewId | ViewId[] = []): void {
  const preservedViewSet = new Set([
    activeView,
    ...(Array.isArray(preservedViews) ? preservedViews : [preservedViews]),
  ]);
  const preservedNames = new Set(
    [...preservedViewSet].flatMap(view => routeDefinition(view).safeParams),
  );
  const routeScopedNames = new Set(routeCatalog.flatMap(route => route.safeParams));
  for (const name of routeScopedNames) {
    if (!preservedNames.has(name)) url.searchParams.delete(name);
  }
}

export function normalizeLegacyShellUrl(url: URL): boolean {
  const viewChanged = normalizeRouteParam(url, 'view');
  const returnChanged = normalizeRouteParam(url, 'return');
  return viewChanged || returnChanged;
}

function normalizeRouteParam(url: URL, key: 'view' | 'return'): boolean {
  const current = url.searchParams.get(key);
  const normalized = normalizeDashboardRouteInput(current);
  if (!normalized) return false;
  let changed = false;
  if (current !== normalized.view) {
    url.searchParams.set(key, normalized.view);
    changed = true;
  }
  for (const [name, value] of Object.entries(normalized.params)) {
    const targetName = key === 'return' ? `return_${name}` : name;
    if (url.searchParams.get(targetName) !== value) {
      url.searchParams.set(targetName, value);
      changed = true;
    }
  }
  return changed;
}
