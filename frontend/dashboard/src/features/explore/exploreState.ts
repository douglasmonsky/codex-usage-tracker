import type { ExploreMode } from '../../routes/evidenceConsoleRoutes';

export type { ExploreMode } from '../../routes/evidenceConsoleRoutes';

const modeStateParams = {
  calls: {
    sort: 'calls_sort',
    direction: 'calls_direction',
    page: 'calls_page',
  },
  threads: {
    sort: 'threads_sort',
    direction: 'threads_direction',
    page: 'threads_page',
  },
} as const satisfies Record<ExploreMode, Record<'sort' | 'direction' | 'page', string>>;

const activeControlParams = ['sort', 'direction', 'page'] as const;

export function readExploreMode(href = window.location.href): ExploreMode {
  const params = new URL(href).searchParams;
  const view = params.get('view');
  if (view === 'threads') return 'threads';
  if (view === 'calls') return 'calls';
  return params.get('mode') === 'threads' ? 'threads' : 'calls';
}

export function normalizeExploreUrl(href = window.location.href): URL {
  const url = new URL(href);
  url.searchParams.set('view', 'explore');
  url.searchParams.set('mode', readExploreMode(href));
  url.searchParams.delete('explore');
  return url;
}

export function buildExploreModeUrl(
  nextMode: ExploreMode,
  href = window.location.href,
): URL {
  const currentMode = readExploreMode(href);
  const url = normalizeExploreUrl(href);
  if (currentMode === nextMode) return url;

  saveActiveControls(url, currentMode);
  restoreActiveControls(url, nextMode);
  url.searchParams.set('mode', nextMode);
  return url;
}

function saveActiveControls(url: URL, mode: ExploreMode): void {
  for (const name of activeControlParams) {
    const value = url.searchParams.get(name);
    const savedName = modeStateParams[mode][name];
    if (value) url.searchParams.set(savedName, value);
    else url.searchParams.delete(savedName);
  }
}

function restoreActiveControls(url: URL, mode: ExploreMode): void {
  for (const name of activeControlParams) {
    const value = url.searchParams.get(modeStateParams[mode][name]);
    if (value) url.searchParams.set(name, value);
    else url.searchParams.delete(name);
  }
}
