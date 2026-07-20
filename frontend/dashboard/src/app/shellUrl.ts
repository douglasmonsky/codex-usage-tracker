import { isViewId, type ViewId } from './navigation';
import { routeDefinition } from './routeCatalog';
import type { HistoryScope } from '../data/dataScope';

export type { HistoryScope } from '../data/dataScope';

function isCallReturnViewId(value: string | null): value is ViewId {
  return isViewId(value) && value !== 'call';
}

export function viewFromUrlParam(value: string | null, fallback: ViewId = 'overview'): ViewId {
  if (value === 'insights') return 'overview';
  return isViewId(value) ? value : fallback;
}

export function callReturnViewFromSearch(search = window.location.search, fallback: ViewId = 'calls'): ViewId {
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

const inactiveViewSearchParams: Partial<Record<ViewId, string[]>> = {
  investigator: ['finding'],
  threads: ['thread', 'thread_key', 'expand', 'threads', 'thread_q', 'risk', 'thread_call_sort', 'thread_call_page'],
  'cache-context': ['cache_thread'],
  reports: ['report'],
  'usage-drain': [
    'usage_plan',
    'usage_effort',
    'usage_subagents',
    'usage_sample',
    'usage_confidence',
    'limit_window',
    'limit_hypothesis',
  ],
  diagnostics: ['diagnostic_source', 'diagnostic_fact'],
  calls: ['explore', 'detail', 'call_q', 'source', 'sort', 'direction', 'density', 'page'],
  call: ['record', 'return', 'mode', 'max_entries', 'max_chars', 'include_tool_output', 'include_compaction_history'],
};

export function clearInactiveViewSearchParams(url: URL, activeView: ViewId, preservedViews: ViewId | ViewId[] = []): void {
  const preservedViewSet = new Set([activeView, ...(Array.isArray(preservedViews) ? preservedViews : [preservedViews])]);
  for (const [view, names] of Object.entries(inactiveViewSearchParams) as Array<[ViewId, string[]]>) {
    if (preservedViewSet.has(view)) continue;
    for (const name of names) {
      url.searchParams.delete(name);
    }
  }
}

export function normalizeLegacyShellUrl(url: URL): boolean {
  let changed = false;
  if (url.searchParams.get('view') === 'insights') {
    url.searchParams.set('view', 'overview');
    changed = true;
  }
  if (url.searchParams.get('return') === 'insights') {
    url.searchParams.set('return', 'overview');
    changed = true;
  }
  return changed;
}
