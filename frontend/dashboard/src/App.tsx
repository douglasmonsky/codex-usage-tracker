import { QueryClientProvider } from '@tanstack/react-query';
import { ArrowUp, Copy, Download, RefreshCw, ShieldAlert, Terminal, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { currentViewCsvExport } from './app/currentViewExport';
import { errorMessage, refreshProgressLabel, type RefreshOptions } from './app/dashboardRefresh';
import { historyScopeFromPayload, historyScopeStatusLabel } from './app/historyScope';
import { createShellI18n, initialDashboardLanguage, storeDashboardLanguage } from './app/i18n';
import { LocalizedShellI18nProvider } from './app/DocumentLocalizationBridge';
import { modelWithLegacyShellFilters } from './app/legacyShellFilters';
import { navItems, secondaryNavItems, type ViewId } from './app/navigation';
import { routeDefinition } from './app/routeCatalog';
import { useConversationalReadiness, useExperimentalDashboardFeatures } from './app/dashboardHooks';
import { RowLimitControl } from './app/RowLimitControl';
import { ShellGlobalFilters } from './app/ShellGlobalFilters';
import {
  finiteRowLimitFallback,
  currentLoadWindowFromPayload,
  initialLoadWindowFromPayload,
  loadWindowLabel,
  loadLimitFromPayload,
  nextRowLoadLimit,
  normalizeRowLimit,
  readDataScopePreference,
  rowLimitSliderMaxValue,
  rowLoadStatusLabel,
  sinceForLoadWindow,
  storeDataScopePreference,
  type LoadWindow,
} from './app/rowLimit';
import {
  callReturnViewFromSearch,
  callReturnViewLabel,
  clearInactiveViewSearchParams,
  hasCallReturnViewParam,
  historyScopeFromUrl,
  historyScopeUrl,
  normalizeLegacyShellUrl,
  type HistoryScope,
  viewFromUrlParam,
} from './app/shellUrl';
import { modelFromBootPayload, readBootPayload, type RefreshProgressPayload } from './api/client';
import { clearDiagnosticApiCache } from './api/diagnostics';
import type { ContextRuntime, DashboardBootPayload, DashboardModel } from './api/types';
import {
  cancelUsageQueries,
  dashboardSourceIdentityFromPayload,
  dashboardQueryClient,
  isUsageQueryCancelled,
  queryUsageSnapshot,
} from './data/queryRuntime';
import { EnvironmentStatus } from './components/EnvironmentStatus';
import { copyText } from './features/shared/copyText';
import { downloadCsv } from './features/shared/exportCsv';
import { presetLabel } from './features/shared/investigationPresets';
import { DashboardRouteView } from './routes/DashboardRouteView';

const autoRefreshIntervalMs = 10_000;
const keyboardShortcutViews: Record<string, ViewId> = {
  '1': 'overview',
  '2': 'calls',
  '3': 'threads',
  '4': 'diagnostics',
};
export function shouldAutoRefreshUsageView(view: ViewId): boolean {
  return routeDefinition(view).capabilities.refresh;
}

function isKeyboardShortcutTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest('input, select, textarea, button, [contenteditable="true"]'));
}

export function App() {
  const { showExperimental, setShowExperimental } = useExperimentalDashboardFeatures();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const initialPayload = useMemo(() => readBootPayload(), []);
  const [dashboardPayload, setDashboardPayload] = useState<DashboardBootPayload | null>(initialPayload);
  const [model, setModel] = useState<DashboardModel>(() => modelFromBootPayload(initialPayload));
const [activeView, setActiveView] = useState<ViewId>(() => {
  const params = new URLSearchParams(window.location.search);
  return viewFromUrlParam(params.get('view'));
});
  const [activeRecordId, setActiveRecordId] = useState(
    () => new URLSearchParams(window.location.search).get('record') ?? '',
);
const [callReturnView, setCallReturnView] = useState<ViewId>(() => callReturnViewFromSearch());
const [callReturnViewExplicit, setCallReturnViewExplicit] = useState(() => hasCallReturnViewParam());
const [globalQuery, setGlobalQuery] = useState(() => new URLSearchParams(window.location.search).get('q') ?? '');
const [activePreset, setActivePreset] = useState(() => new URLSearchParams(window.location.search).get('preset') ?? '');
  const [locationSearch, setLocationSearch] = useState(() => window.location.search);
  const [refreshState, setRefreshState] = useState('Stored snapshot loaded just now');
  const [refreshProgress, setRefreshProgress] = useState<RefreshProgressPayload | null>(null);
  const [refreshing, setRefreshing] = useState(false);
const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
const [showBackToTop, setShowBackToTop] = useState(false);
const [language, setLanguage] = useState(() => initialDashboardLanguage(initialPayload));
const initialLiveLoadAttempted = useRef(false);
 const [loadLimit, setLoadLimit] = useState(() => finiteRowLimitFallback(loadLimitFromPayload(initialPayload), 500));
  const [pendingLoadLimit, setPendingLoadLimit] = useState(() => finiteRowLimitFallback(loadLimitFromPayload(initialPayload), 500));
  const [loadWindow, setLoadWindow] = useState<LoadWindow>(() => initialLoadWindowFromPayload(initialPayload));
  const [historyScope, setHistoryScope] = useState<HistoryScope>(() => historyScopeFromUrl(historyScopeFromPayload(initialPayload)));
  const [contextApiEnabled, setContextApiEnabled] = useState(model.contextRuntime.contextApiEnabled);
const { canUseLiveApi, conversationalAnalysis } = useConversationalReadiness(initialPayload, dashboardPayload);
const sourceIdentity = useMemo(() => dashboardSourceIdentityFromPayload(dashboardPayload), [dashboardPayload]);
const shellI18n = useMemo(() => createShellI18n(dashboardPayload, language), [dashboardPayload, language]);
const contextRuntime = useMemo<ContextRuntime>(
() => ({ ...model.contextRuntime, contextApiEnabled }),
[contextApiEnabled, model.contextRuntime],
);
const legacyShellFilteredModel = useMemo(
() => modelWithLegacyShellFilters(model, historyScope, locationSearch),
[historyScope, locationSearch, model],
);
const scopedModel = activeView === 'calls' || activeView === 'call' ? model : legacyShellFilteredModel;
const canAutoRefreshUsageRows = shouldAutoRefreshUsageView(activeView);
  const finitePendingLoadLimit = finiteRowLimitFallback(pendingLoadLimit, loadLimit, 500);
  const loadedRowCount = Math.max(0, Number(dashboardPayload?.loaded_row_count ?? dashboardPayload?.rows?.length ?? model.calls.length ?? 0));
  const totalAvailableRows = Math.max(0, Number(dashboardPayload?.total_available_rows ?? loadedRowCount));
  const rowLimitChanged = pendingLoadLimit !== loadLimit;
  const rowLimitSliderMax = rowLimitSliderMaxValue({
    currentLimit: loadLimit,
    loadedRows: loadedRowCount,
    pendingLimit: pendingLoadLimit,
  });
  const rowLimitSliderValue = Math.min(finitePendingLoadLimit, rowLimitSliderMax);
const hasMoreRows = Boolean(dashboardPayload?.has_more) || (totalAvailableRows > 0 && loadedRowCount < totalAvailableRows);
  const nextLoadMoreLimit = nextRowLoadLimit({
    currentLimit: loadLimit,
    loadedRows: loadedRowCount,
    pendingLimit: pendingLoadLimit,
  });
const rowLoadStatus = rowLoadStatusLabel({
loadedRows: loadedRowCount,
limit: loadLimit,
totalRows: totalAvailableRows,
});
const rowLoadModeLabel = loadWindowLabel(loadWindow, loadLimit);
  const rowLoadingLabel = `Loading ${loadWindowLabel(loadWindow, finitePendingLoadLimit).toLowerCase()}...`;
  const refreshProgressPercent =
    refreshing && typeof refreshProgress?.percent === 'number'
      ? Math.max(0, Math.min(100, refreshProgress.percent))
      : null;
  const refreshProgressText = refreshProgress
    ? refreshProgressLabel(refreshProgress, historyScope)
    : rowLoadingLabel;
  const canLoadAllRows = canUseLiveApi && !refreshing && loadWindow !== 'all';
const historyScopeDetail = historyScopeStatusLabel({
historyScope,
activeRows: dashboardPayload?.active_available_rows,
allRows: dashboardPayload?.all_history_available_rows,
    archivedRows: dashboardPayload?.archived_available_rows,
  });

function setView(view: ViewId) {
    setActiveView(view);
    setActivePreset('');
  const url = new URL(window.location.href);
  url.searchParams.set('view', view);
  url.searchParams.delete('preset');
  clearInactiveViewSearchParams(url, view);
  if (view !== 'call') {
    setActiveRecordId('');
  }
  pushShellUrl(url);
}

function replaceShellUrl(url: URL) {
  window.history.replaceState(null, '', url);
  setLocationSearch(url.search);
}

function pushShellUrl(url: URL) {
  window.history.pushState(null, '', url);
  setLocationSearch(url.search);
}

useEffect(() => {
  const url = new URL(window.location.href);
  if (normalizeLegacyShellUrl(url)) {
    replaceShellUrl(url);
  }
}, []);

useEffect(() => {
  function hydrateShellFromLocation() {
    const search = window.location.search;
    const params = new URLSearchParams(search);
    setActiveView(viewFromUrlParam(params.get('view')));
    setActiveRecordId(params.get('record') ?? '');
    setCallReturnView(callReturnViewFromSearch(search));
    setCallReturnViewExplicit(hasCallReturnViewParam(search));
    setGlobalQuery(params.get('q') ?? '');
    setActivePreset(params.get('preset') ?? '');
    setHistoryScope(historyScopeFromUrl(historyScopeFromPayload(dashboardPayload), search));
    setLocationSearch(search);
  }

  window.addEventListener('popstate', hydrateShellFromLocation);
  return () => window.removeEventListener('popstate', hydrateShellFromLocation);
}, [dashboardPayload]);

  useEffect(() => {
    function handleKeyboardShortcut(event: KeyboardEvent) {
      if (isKeyboardShortcutTarget(event.target)) return;

      if (event.key === '/') {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }

      const nextView = keyboardShortcutViews[event.key];
      if (!nextView) return;

      event.preventDefault();
      setView(nextView);
    }

    window.addEventListener('keydown', handleKeyboardShortcut);
    return () => window.removeEventListener('keydown', handleKeyboardShortcut);
  }, []);

  useEffect(() => {
    function updateBackToTopVisibility() {
      setShowBackToTop(window.scrollY > 320);
    }

    updateBackToTopVisibility();
    window.addEventListener('scroll', updateBackToTopVisibility, { passive: true });
    return () => window.removeEventListener('scroll', updateBackToTopVisibility);
  }, []);

function openCallInvestigator(recordId: string) {
const returnView = activeView === 'call' ? callReturnView : activeView;
setCallReturnView(returnView);
setCallReturnViewExplicit(activeView === 'call' ? callReturnViewExplicit : true);
setActiveView('call');
setActiveRecordId(recordId);
const url = new URL(window.location.href);
clearInactiveViewSearchParams(url, activeView, activeView === 'call' ? callReturnView : []);
url.searchParams.set('view', 'call');
url.searchParams.set('record', recordId);
url.searchParams.set('return', returnView);
pushShellUrl(url);
}

function backFromCallInvestigator() {
setView(callReturnView);
}

  function updateGlobalQuery(value: string) {
    setGlobalQuery(value);
    setActivePreset('');
    const url = new URL(window.location.href);
    url.searchParams.delete('preset');
    if (value) {
      url.searchParams.set('q', value);
  } else {
    url.searchParams.delete('q');
  }
  replaceShellUrl(url);
}

async function refreshDashboard(options: RefreshOptions = {}) {
  if (refreshing) return;
  initialLiveLoadAttempted.current = true;
  const nextLoadLimit = options.loadLimit ?? loadLimit;
  const nextLoadWindow = options.loadWindow ?? loadWindow;
  const nextSince = sinceForLoadWindow(nextLoadWindow);
  const nextHistoryScope = options.historyScope ?? historyScope;
  const shouldRefreshIndex = options.refresh ?? true;
  const shouldShowProgress = Boolean(dashboardPayload?.refresh_jobs_available);
  setRefreshing(true);
  setRefreshProgress(
    shouldShowProgress
      ? {
          status: 'running',
          phase: shouldRefreshIndex ? 'refreshing_index' : 'loading_rows',
          message: `${shouldRefreshIndex ? 'Refreshing' : 'Loading'} ${loadWindowLabel(nextLoadWindow, nextLoadLimit)}`,
        }
      : null,
  );
  setRefreshState(
    `${shouldRefreshIndex ? 'Refreshing index for' : 'Loading'} ${loadWindowLabel(nextLoadWindow, nextLoadLimit)}...`,
  );
  let loadedFromCache = false;
  try {
    const payload = await queryUsageSnapshot({
      currentPayload: dashboardPayload,
      refresh: shouldRefreshIndex,
      loadLimit: nextLoadLimit,
      loadWindow: nextLoadWindow,
      since: nextSince,
      historyScope: nextHistoryScope,
      onProgress: progress => {
        loadedFromCache ||= progress.message === 'Loaded cached dashboard snapshot';
        setRefreshProgress(progress);
        setRefreshState(refreshProgressLabel(progress, nextHistoryScope));
      },
    });
    clearDiagnosticApiCache();
    setDashboardPayload(payload);
      setModel(modelFromBootPayload(payload));
      setContextApiEnabled(Boolean(payload.context_api_enabled));
    const appliedLoadLimit = nextLoadWindow === 'rows'
      ? finiteRowLimitFallback(loadLimitFromPayload(payload, nextLoadLimit), nextLoadLimit)
      : nextLoadLimit;
    setLoadLimit(appliedLoadLimit);
    setPendingLoadLimit(appliedLoadLimit);
    setLoadWindow(nextLoadWindow);
    const appliedHistoryScope = historyScopeFromPayload(payload, nextHistoryScope);
    setHistoryScope(appliedHistoryScope);
    storeDataScopePreference(appliedLoadLimit, appliedHistoryScope, nextLoadWindow);
    const loaded = payload.loaded_row_count ?? payload.rows?.length ?? 0;
    const total = payload.total_available_rows ?? loaded;
    setRefreshState(nextLoadWindow === 'rows'
      ? `${loadedFromCache ? 'Cache hit; l' : shouldRefreshIndex ? 'Refreshed index; l' : 'L'}oaded ${loaded.toLocaleString()} of ${total.toLocaleString()} calls from ${loadWindowLabel(nextLoadWindow, appliedLoadLimit)}`
      : `${loadedFromCache ? 'Cache hit; ' : shouldRefreshIndex ? 'Refreshed index; ' : ''}${loadWindowLabel(nextLoadWindow, appliedLoadLimit)} analysis ready across ${total.toLocaleString()} calls; ${loaded.toLocaleString()} detail rows cached`);
  } catch (error) {
    setRefreshProgress(null);
    if (isUsageQueryCancelled(error)) {
      setRefreshState('Refresh cancelled; stored snapshot remains visible');
      return;
    }
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setRefreshState(`${errorMessage(error)} Stored snapshot kept at ${timestamp}`);
  } finally {
    setRefreshProgress(null);
    setRefreshing(false);
  }
}

async function cancelDashboardRefresh() {
  await cancelUsageQueries();
  setRefreshProgress(null);
  setRefreshing(false);
  setRefreshState('Refresh cancelled; stored snapshot remains visible');
}

useEffect(() => {
document.documentElement.lang = shellI18n.language;
document.documentElement.dir = shellI18n.direction;
}, [shellI18n.direction, shellI18n.language]);

useEffect(() => {
  const availableRows = Number(dashboardPayload?.total_available_rows ?? 0);
  const loadedRows = Number(dashboardPayload?.loaded_row_count ?? dashboardPayload?.rows?.length ?? 0);
  const sessionSettings = readDataScopePreference();
  const nextHistoryScope = sessionSettings?.historyScope ?? historyScope;
  const nextLoadLimit = sessionSettings?.loadLimit ?? loadLimit;
  const nextLoadWindow = sessionSettings?.loadWindow ?? loadWindow;
  const payloadLoadWindow = currentLoadWindowFromPayload(dashboardPayload);
  const needsSessionRestore =
    nextHistoryScope !== historyScope ||
    nextLoadWindow !== payloadLoadWindow ||
    (nextLoadWindow === 'rows' && nextLoadLimit !== loadLimitFromPayload(dashboardPayload));
  const hasLoadedRows = loadedRows > 0;
  if (
    !canUseLiveApi ||
    (!needsSessionRestore && hasLoadedRows) ||
    (dashboardPayload?.shell_boot !== true && availableRows <= 0) ||
    refreshing ||
    initialLiveLoadAttempted.current
  ) {
    return;
  }
  initialLiveLoadAttempted.current = true;
  if (needsSessionRestore) {
    setHistoryScope(nextHistoryScope);
    setLoadLimit(nextLoadLimit);
    setPendingLoadLimit(nextLoadLimit);
    setLoadWindow(nextLoadWindow);
    replaceShellUrl(historyScopeUrl(nextHistoryScope));
  }
  void refreshDashboard({ refresh: false, historyScope: nextHistoryScope, loadLimit: nextLoadLimit, loadWindow: nextLoadWindow });
}, [canUseLiveApi, dashboardPayload, historyScope, loadLimit, loadWindow, refreshing]);

 useEffect(() => {
 if (!canUseLiveApi && autoRefreshEnabled) {
 setAutoRefreshEnabled(false);
    }
  }, [autoRefreshEnabled, canUseLiveApi]);

useEffect(() => {
if (!autoRefreshEnabled || !canUseLiveApi || !canAutoRefreshUsageRows) return undefined;
const intervalId = window.setInterval(() => {
void refreshDashboard();
}, autoRefreshIntervalMs);
return () => window.clearInterval(intervalId);
}, [autoRefreshEnabled, canAutoRefreshUsageRows, canUseLiveApi, dashboardPayload, historyScope, loadLimit, loadWindow, refreshing]);

useEffect(() => {
if (!autoRefreshEnabled || !canUseLiveApi || !canAutoRefreshUsageRows) return undefined;
function handleVisibilityChange() {
if (document.visibilityState === 'visible') {
void refreshDashboard();
}
}
document.addEventListener('visibilitychange', handleVisibilityChange);
return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
}, [autoRefreshEnabled, canAutoRefreshUsageRows, canUseLiveApi, dashboardPayload, historyScope, loadLimit, loadWindow, refreshing]);

function handleLoadLimitDraftChange(value: string) {
const trimmedValue = value.trim();
setPendingLoadLimit(Math.max(1, normalizeRowLimit(trimmedValue === '' ? Number.NaN : Number(trimmedValue))));
}

function handleLoadLimitSliderChange(value: string) {
handleLoadLimitDraftChange(value);
}

function applyLoadLimitChange() {
void refreshDashboard({ refresh: false, loadLimit: pendingLoadLimit, loadWindow: 'rows' });
}

function loadAllRows() {
void refreshDashboard({ refresh: false, loadWindow: 'all' });
}

function loadMoreRows() {
setPendingLoadLimit(nextLoadMoreLimit);
void refreshDashboard({ refresh: false, loadLimit: nextLoadMoreLimit, loadWindow });
}

function handleLoadWindowChange(nextLoadWindow: LoadWindow) {
  if (nextLoadWindow === loadWindow) return;
  void refreshDashboard({ refresh: false, loadWindow: nextLoadWindow });
}

function handleHistoryScopeChange(value: string) {
  const nextHistoryScope: HistoryScope = value === 'all' ? 'all' : 'active';
  setHistoryScope(nextHistoryScope);
  replaceShellUrl(historyScopeUrl(nextHistoryScope));
  void refreshDashboard({ refresh: false, historyScope: nextHistoryScope });
}

function handleAutoRefreshChange(enabled: boolean) {
setAutoRefreshEnabled(enabled);
if (enabled) {
if (!canAutoRefreshUsageRows) {
setRefreshState('Auto refresh pauses on this evidence-heavy view');
return;
}
setRefreshState(`Auto refresh every ${autoRefreshIntervalMs / 1000}s`);
void refreshDashboard();
} else {
      setRefreshState('Auto refresh paused');
    }
}

function handleLanguageChange(nextLanguage: string) {
  setLanguage(nextLanguage);
  storeDashboardLanguage(nextLanguage);
}

  async function copyCurrentViewLink() {
    try {
      const url = new URL(window.location.href);
      normalizeLegacyShellUrl(url);
      clearInactiveViewSearchParams(url, activeView, activeView === 'call' ? callReturnView : []);
      const copied = await copyText(url.toString());
      if (!copied) {
        throw new Error('Clipboard unavailable');
      }
      setRefreshState('Copied current view link');
    } catch {
      setRefreshState('Copy unavailable in browser');
    }
  }

  async function copyCallInvestigatorLink(recordId: string) {
    try {
      const url = new URL(window.location.href);
      clearInactiveViewSearchParams(url, activeView, activeView === 'call' ? callReturnView : []);
      const returnView = activeView === 'call' ? callReturnView : activeView;
      url.searchParams.set('view', 'call');
      url.searchParams.set('record', recordId);
url.searchParams.set('return', returnView);
const copied = await copyText(url.toString());
if (!copied) {
throw new Error('Clipboard unavailable');
}
setRefreshState('Copied call investigator link');
} catch {
setRefreshState('Copy unavailable in browser');
}
}

async function exportCurrentViewCsv() {
const exportSpec = await currentViewCsvExport(
activeView,
scopedModel,
      {
        contextRuntime,
        historyScope,
        loadWindow,
        loadLimit,
        scopeSince: dashboardPayload?.since ?? sinceForLoadWindow(loadWindow),
        loadedRowCount,
        totalAvailableRows,
        canUseLiveApi,
        autoRefreshEnabled,
        refreshState,
      },
      globalQuery,
      activePreset,
    );
    if (!exportSpec.rowCount) {
      setRefreshState(`No ${exportSpec.label} to export`);
      return;
    }
downloadCsv(exportSpec.filename, exportSpec.csv);
setRefreshState(`Exported ${exportSpec.rowCount} ${exportSpec.label}`);
}

function clearInvestigationPreset() {
    setActivePreset('');
  const url = new URL(window.location.href);
  url.searchParams.delete('preset');
  replaceShellUrl(url);
  setRefreshState('Investigation preset cleared');
}

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <LocalizedShellI18nProvider value={shellI18n}>
      <div className="app-shell" data-dashboard-localization-root>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Terminal size={22} />
          </div>
          <div>
            <strong>Codex Usage Tracker</strong>
            <span>{shellI18n.t('dashboard.eyebrow', 'Local telemetry console')}</span>
          </div>
        </div>
<div className="local-pill">
<span aria-hidden="true" />
Local data only
</div>
<EnvironmentStatus payload={dashboardPayload} canUseLiveApi={canUseLiveApi} shellI18n={shellI18n} />
<nav className="primary-nav" aria-label="Primary">
          {navItems.map(item => {
            const Icon = item.icon;
const selected = activeView === item.id || (activeView === 'call' && item.id === 'calls');
return (
              <button
                type="button"
                key={item.id}
                aria-pressed={selected}
                className={selected ? 'active' : ''}
                onClick={() => setView(item.id)}
              >
<Icon size={18} />
<span>{shellI18n.navLabel(item.id, item.label)}</span>
</button>
);
          })}
        </nav>
        <div className="secondary-block" role="group" aria-label="Quick Links">
          <span>Quick Links</span>
          {secondaryNavItems.map(item => {
            const Icon = item.icon;
            return (
              <button type="button" key={item.label} onClick={() => setView(item.target)}>
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </div>
      </aside>
      <main className="workspace">
        <div className="unofficial-banner" role="note" aria-label="Unofficial project notice">
          <ShieldAlert size={16} />
          <span>
            <strong>Unofficial project.</strong> Not made by, affiliated with, endorsed by, sponsored by, or
            supported by OpenAI.
          </span>
        </div>
        <header className="topbar" aria-label="Dashboard toolbar">
<label className="global-search">
<span className="sr-only">{shellI18n.t('filter.search', 'Search dashboard')}</span>
<input
ref={searchInputRef}
aria-label={shellI18n.t('filter.search', 'Search dashboard')}
value={globalQuery}
onChange={event => updateGlobalQuery(event.target.value)}
placeholder={shellI18n.t('filter.search_placeholder', 'Search calls, threads, models, diagnostics...')}
/>
</label>
<div className="topbar-actions">
<div className="topbar-scope-controls">
{shellI18n.languages.length > 1 ? (
<label className="topbar-select">
<span>{shellI18n.t('language.label', 'Language')}</span>
<select data-localization-skip="true" aria-label={shellI18n.t('language.label', 'Language')} value={shellI18n.language} onChange={event => handleLanguageChange(event.target.value)}>
{shellI18n.languages.map(languageOption => (
<option key={languageOption.code} value={languageOption.code}>
{languageOption.native_name || languageOption.english_name || languageOption.code}
</option>
))}
</select>
</label>
) : null}
<label className="topbar-select">
<span>{shellI18n.t('nav.history', 'History')}</span>
<select
aria-label="History scope"
              title={historyScopeDetail}
              value={historyScope}
              onChange={event => handleHistoryScopeChange(event.target.value)}
              disabled={refreshing || !canUseLiveApi}
>
<option value="active">{shellI18n.t('option.active_sessions_only', 'Active')}</option>
<option value="all">{shellI18n.t('option.all_history', 'All history')}</option>
</select>
<small className="sr-only">{historyScopeDetail}</small>
          </label>
          </div>
          <RowLimitControl
            canUseLiveApi={canUseLiveApi}
            finitePendingLoadLimit={finitePendingLoadLimit}
            hasMoreRows={hasMoreRows}
            loadLabel={shellI18n.t('nav.load', 'Load')}
            loadMoreLabel={shellI18n.t('button.load_more', 'Load more')}
            loadWindow={loadWindow}
            loadedRowCount={loadedRowCount}
            pendingLoadLimit={pendingLoadLimit}
            refreshProgressPercent={refreshProgressPercent}
            refreshProgressText={refreshProgressText}
            refreshing={refreshing}
            rowLimitChanged={rowLimitChanged}
            rowLimitSliderMax={rowLimitSliderMax}
            rowLimitSliderValue={rowLimitSliderValue}
            rowLoadModeLabel={rowLoadModeLabel}
            rowLoadStatus={rowLoadStatus}
            totalAvailableRows={totalAvailableRows}
            onApply={applyLoadLimitChange}
            onCancel={cancelDashboardRefresh}
            onDraftChange={handleLoadLimitDraftChange}
            onLoadMore={loadMoreRows}
            onSliderChange={handleLoadLimitSliderChange}
            onWindowChange={handleLoadWindowChange}
          />
        <div className="topbar-meta">
          <div className="topbar-statuses">
        {activePreset ? (
          <button className="toolbar-button" type="button" onClick={clearInvestigationPreset}>
            <X size={15} />
            {shellI18n.t('button.clear', 'Clear')} {presetLabel(activePreset)}
          </button>
        ) : null}
<label className="topbar-toggle">
          <input
            aria-label="Auto refresh"
            type="checkbox"
            checked={autoRefreshEnabled}
            onChange={event => handleAutoRefreshChange(event.target.checked)}
            disabled={refreshing || !canUseLiveApi}
/>
<span>Auto</span>
</label>
          </div>
          <div className="topbar-icon-actions">
<button className="icon-button" type="button" onClick={copyCurrentViewLink} aria-label={shellI18n.t('button.copy_link', 'Copy link')} title={shellI18n.t('button.copy_link', 'Copy link')}>
<Copy size={17} />
</button>
<button className="icon-button" type="button" onClick={exportCurrentViewCsv} aria-label={shellI18n.t('button.export_csv', 'Export CSV')} title={shellI18n.t('button.export_csv', 'Export CSV')}>
<Download size={17} />
</button>
<button className="icon-button" type="button" onClick={onRefresh} aria-label={shellI18n.t('button.refresh', 'Refresh')} title={shellI18n.t('button.refresh', 'Refresh')} disabled={refreshing}>
<RefreshCw size={17} />
</button>
          </div>
        </div>
      </div>
      </header>
      <p className="sr-only" role="status" aria-live="polite">{refreshState}</p>
      <DashboardRouteView
        activeView={activeView}
        model={scopedModel} navigateView={setView}
        onRefresh={onRefresh}
        refreshState={refreshState}
        globalQuery={globalQuery}
        activePreset={activePreset}
        activeRecordId={activeRecordId}
        contextRuntime={contextRuntime}
        setContextApiEnabled={setContextApiEnabled}
        openCallInvestigator={openCallInvestigator}
        copyCallInvestigatorLink={copyCallInvestigatorLink}
        callBackLabel={
          callReturnViewExplicit
            ? `Back to ${callReturnViewLabel(callReturnView)}`
            : shellI18n.t('button.back_to_dashboard', 'Back to dashboard')
        }
        backFromCallInvestigator={backFromCallInvestigator}
        dashboardPayload={dashboardPayload}
        conversationalAnalysis={conversationalAnalysis}
        sourceIdentity={sourceIdentity}
        historyScope={historyScope}
        loadWindow={loadWindow}
        scopeSince={dashboardPayload?.since ?? sinceForLoadWindow(loadWindow)}
        loadLimit={loadLimit}
        loadedRowCount={loadedRowCount}
        totalAvailableRows={totalAvailableRows}
        canUseLiveApi={canUseLiveApi}
        autoRefreshEnabled={autoRefreshEnabled} applicationI18n={shellI18n}
        showExperimental={showExperimental}
        setShowExperimental={setShowExperimental}
        refreshing={refreshing}
        hasMoreRows={hasMoreRows}
        canLoadAllRows={canLoadAllRows}
        loadMoreRows={loadMoreRows}
        loadAllRows={loadAllRows}
        globalFilters={
          <ShellGlobalFilters
            activeView={activeView}
            locationSearch={locationSearch}
            model={model}
            onUrlChange={replaceShellUrl}
          />
        }
      />
      </main>
      {showBackToTop ? (
        <button className="to-top-button" type="button" onClick={scrollToTop} aria-label="Back to top">
          <ArrowUp size={18} />
          {shellI18n.t('button.top', 'Top')}
        </button>
      ) : null}
      </div>
    </LocalizedShellI18nProvider>
  );

  function onRefresh() {
    void refreshDashboard();
  }
}

export function RoutedApp() {
  return (
    <QueryClientProvider client={dashboardQueryClient}>
      <App />
    </QueryClientProvider>
  );
}
