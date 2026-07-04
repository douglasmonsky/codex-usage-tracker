import { ArrowUp, Copy, Download, RefreshCw, ShieldAlert, Terminal, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { currentViewCsvExport } from './app/currentViewExport';
import { historyScopeFromPayload, historyScopeStatusLabel } from './app/historyScope';
import { createShellI18n, initialDashboardLanguage, storeDashboardLanguage } from './app/i18n';
import { ShellI18nProvider } from './app/i18nContext';
import { modelWithLegacyShellFilters } from './app/legacyShellFilters';
import { navItems, secondaryNavItems, type ViewId } from './app/navigation';
import { ShellGlobalFilters } from './app/ShellGlobalFilters';
import {
  finiteRowLimitFallback,
  loadLimitFromPayload,
  nextRowLoadLimit,
  normalizeRowLimit,
  rowLimitMin,
  rowLimitNoCap,
  rowLimitSliderMaxValue,
  rowLimitStep,
  rowLimitSummaryLabel,
  rowLimitValueLabel,
  rowLoadStatusLabel,
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
import { loadUsagePayload, modelFromBootPayload, readBootPayload } from './api/client';
import { clearDiagnosticApiCache } from './api/diagnostics';
import type { ContextRuntime, DashboardBootPayload, DashboardModel } from './api/types';
import { EnvironmentStatus } from './components/EnvironmentStatus';
import { StatusBadge } from './components/StatusBadge';
import { CallInvestigatorPage } from './features/call-investigator/CallInvestigatorPage';
import { CacheContextPage } from './features/cache-context/CacheContextPage';
import { CallsPage } from './features/calls/CallsPage';
import { DiagnosticsPage } from './features/diagnostics/DiagnosticsPage';
import { InvestigatorPage } from './features/investigator/InvestigatorPage';
import { OverviewPage } from './features/overview/OverviewPage';
import { ReportsPage } from './features/reports/ReportsPage';
import { SettingsPage } from './features/settings/SettingsPage';
import { copyText } from './features/shared/copyText';
import { downloadCsv } from './features/shared/exportCsv';
import { presetLabel, type InvestigationPresetAction } from './features/shared/investigationPresets';
import { ThreadsPage } from './features/threads/ThreadsPage';
import { UsageDrainPage } from './features/usage-drain/UsageDrainPage';

type RefreshOptions = {
  loadLimit?: number;
  historyScope?: HistoryScope;
  refresh?: boolean;
};

const autoRefreshIntervalMs = 10_000;
const keyboardShortcutViews: Record<string, ViewId> = {
  '1': 'overview',
  '2': 'calls',
  '3': 'threads',
  '4': 'diagnostics',
};
const autoRefreshSkippedViews = new Set<ViewId>(['call', 'diagnostics']);

export function shouldAutoRefreshUsageView(view: ViewId): boolean {
  return !autoRefreshSkippedViews.has(view);
}

function isKeyboardShortcutTarget(target: EventTarget | null) {
if (!(target instanceof Element)) return false;
return Boolean(target.closest('input, select, textarea, button, [contenteditable="true"]'));
}

export function App() {
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
  const [refreshing, setRefreshing] = useState(false);
const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
const [showBackToTop, setShowBackToTop] = useState(false);
const [language, setLanguage] = useState(() => initialDashboardLanguage(initialPayload));
const initialLiveLoadAttempted = useRef(false);
 const [loadLimit, setLoadLimit] = useState(() => loadLimitFromPayload(initialPayload));
  const [pendingLoadLimit, setPendingLoadLimit] = useState(() => loadLimitFromPayload(initialPayload));
  const [historyScope, setHistoryScope] = useState<HistoryScope>(() => historyScopeFromUrl(historyScopeFromPayload(initialPayload)));
  const [contextApiEnabled, setContextApiEnabled] = useState(model.contextRuntime.contextApiEnabled);
const canUseLiveApi = Boolean(dashboardPayload?.api_token);
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
const pendingLoadLimitUncapped = pendingLoadLimit === rowLimitNoCap;
  const finitePendingLoadLimit = pendingLoadLimitUncapped
    ? finiteRowLimitFallback(loadLimit, dashboardPayload?.loaded_row_count)
    : pendingLoadLimit;
  const loadedRowCount = Math.max(0, Number(dashboardPayload?.loaded_row_count ?? dashboardPayload?.rows?.length ?? model.calls.length ?? 0));
  const totalAvailableRows = Math.max(0, Number(dashboardPayload?.total_available_rows ?? loadedRowCount));
  const rowLimitChanged = pendingLoadLimit !== loadLimit;
  const rowLimitSliderMax = rowLimitSliderMaxValue({
    currentLimit: loadLimit,
    loadedRows: loadedRowCount,
    pendingLimit: pendingLoadLimit,
  });
  const rowLimitSliderValue = pendingLoadLimitUncapped
    ? rowLimitSliderMax
    : Math.min(finitePendingLoadLimit, rowLimitSliderMax);
const hasMoreRows = !pendingLoadLimitUncapped && (Boolean(dashboardPayload?.has_more) || (totalAvailableRows > 0 && loadedRowCount < totalAvailableRows));
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
const rowLoadModeLabel = loadLimit === rowLimitNoCap ? 'All rows mode' : `Most recent ${loadLimit.toLocaleString()} calls`;
const rowLoadingLabel =
loadLimit === rowLimitNoCap || pendingLoadLimitUncapped
? 'Loading all rows...'
: `Loading ${finitePendingLoadLimit.toLocaleString()} rows...`;
const canLoadAllRows = canUseLiveApi && !refreshing && loadLimit !== rowLimitNoCap;
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
  replaceShellUrl(url);
}

function replaceShellUrl(url: URL) {
  window.history.replaceState(null, '', url);
  setLocationSearch(url.search);
}

useEffect(() => {
  const url = new URL(window.location.href);
  if (normalizeLegacyShellUrl(url)) {
    replaceShellUrl(url);
  }
}, []);

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
replaceShellUrl(url);
}

function openFindingInvestigator(rank: number) {
setActiveView('investigator');
setActivePreset('');
setActiveRecordId('');
const url = new URL(window.location.href);
url.searchParams.set('view', 'investigator');
url.searchParams.set('finding', String(rank));
url.searchParams.delete('preset');
clearInactiveViewSearchParams(url, 'investigator');
replaceShellUrl(url);
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

  function applyInvestigationPreset(action: InvestigationPresetAction) {
    setActiveView(action.view);
    setActivePreset(action.presetKey);
    setGlobalQuery(action.query ?? '');
    setActiveRecordId('');
const url = new URL(window.location.href);
url.searchParams.set('view', action.view);
url.searchParams.set('preset', action.presetKey);
clearInactiveViewSearchParams(url, action.view);
if (action.query) {
url.searchParams.set('q', action.query);
} else {
url.searchParams.delete('q');
}
replaceShellUrl(url);
}

async function refreshDashboard(options: RefreshOptions = {}) {
 if (refreshing) return;
 const nextLoadLimit = options.loadLimit ?? loadLimit;
 const nextHistoryScope = options.historyScope ?? historyScope;
 const shouldRefreshIndex = options.refresh ?? true;
 setRefreshing(true);
 setRefreshState(
 `${shouldRefreshIndex ? 'Refreshing' : 'Loading'} ${nextHistoryScope === 'all' ? 'all history' : 'active'} aggregate rows...`,
 );
 try {
 const payload = await loadUsagePayload(dashboardPayload, {
 refresh: shouldRefreshIndex,
 limit: nextLoadLimit,
 includeArchived: nextHistoryScope === 'all',
 });
    clearDiagnosticApiCache();
    setDashboardPayload(payload);
      setModel(modelFromBootPayload(payload));
      setContextApiEnabled(Boolean(payload.context_api_enabled));
      const appliedLoadLimit = loadLimitFromPayload(payload, nextLoadLimit);
      setLoadLimit(appliedLoadLimit);
      setPendingLoadLimit(appliedLoadLimit);
      setHistoryScope(historyScopeFromPayload(payload, nextHistoryScope));
      const loaded = payload.loaded_row_count ?? payload.rows?.length ?? 0;
      const total = payload.total_available_rows ?? loaded;
      setRefreshState(`Live refresh loaded ${loaded} of ${total} aggregate rows`);
} catch (error) {
const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
setRefreshState(`${errorMessage(error)} Stored snapshot kept at ${timestamp}`);
 } finally {
 setRefreshing(false);
 }
 }

useEffect(() => {
document.documentElement.lang = shellI18n.language;
document.documentElement.dir = shellI18n.direction;
}, [shellI18n.direction, shellI18n.language]);

useEffect(() => {
const availableRows = Number(dashboardPayload?.total_available_rows ?? 0);
 const hasLoadedRows = Boolean(dashboardPayload?.rows?.length);
 if (!canUseLiveApi || hasLoadedRows || availableRows <= 0 || refreshing || initialLiveLoadAttempted.current) {
 return;
 }
 initialLiveLoadAttempted.current = true;
 void refreshDashboard({ refresh: false });
 }, [canUseLiveApi, dashboardPayload, historyScope, loadLimit, refreshing]);

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
}, [autoRefreshEnabled, canAutoRefreshUsageRows, canUseLiveApi, dashboardPayload, historyScope, loadLimit, refreshing]);

useEffect(() => {
if (!autoRefreshEnabled || !canUseLiveApi || !canAutoRefreshUsageRows) return undefined;
function handleVisibilityChange() {
if (document.visibilityState === 'visible') {
void refreshDashboard();
}
}
document.addEventListener('visibilitychange', handleVisibilityChange);
return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
}, [autoRefreshEnabled, canAutoRefreshUsageRows, canUseLiveApi, dashboardPayload, historyScope, loadLimit, refreshing]);

function handleLoadLimitDraftChange(value: string) {
const trimmedValue = value.trim();
setPendingLoadLimit(normalizeRowLimit(trimmedValue === '' ? Number.NaN : Number(trimmedValue)));
}

function handleLoadLimitSliderChange(value: string) {
handleLoadLimitDraftChange(value);
}

function handleLoadLimitNoCapChange(enabled: boolean) {
setPendingLoadLimit(enabled ? rowLimitNoCap : finiteRowLimitFallback(loadLimit, dashboardPayload?.loaded_row_count));
}

function applyLoadLimitChange() {
void refreshDashboard({ loadLimit: pendingLoadLimit });
}

function loadAllRows() {
setPendingLoadLimit(rowLimitNoCap);
void refreshDashboard({ loadLimit: rowLimitNoCap });
}

function loadMoreRows() {
if (pendingLoadLimitUncapped) return;
setPendingLoadLimit(nextLoadMoreLimit);
void refreshDashboard({ loadLimit: nextLoadMoreLimit });
}

function handleHistoryScopeChange(value: string) {
  const nextHistoryScope: HistoryScope = value === 'all' ? 'all' : 'active';
  setHistoryScope(nextHistoryScope);
  replaceShellUrl(historyScopeUrl(nextHistoryScope));
  void refreshDashboard({ historyScope: nextHistoryScope });
}

function handleAutoRefreshChange(enabled: boolean) {
setAutoRefreshEnabled(enabled);
if (enabled) {
if (!canAutoRefreshUsageRows) {
setRefreshState('Auto refresh pauses on Call Investigator and Diagnostics');
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

function exportCurrentViewCsv() {
const exportSpec = currentViewCsvExport(
activeView,
scopedModel,
      {
        contextRuntime,
        historyScope,
        loadLimit,
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
    <ShellI18nProvider value={shellI18n}>
      <div className="app-shell">
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
        <div className="secondary-block">
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
        <div className="status-card">
          <span>Data Snapshot</span>
          <strong>Current</strong>
          <small>
            {historyScope === 'all' ? 'All history' : 'Active history'} - {rowLimitSummaryLabel(loadLimit)}
          </small>
          <small>{refreshState}</small>
          <button type="button" onClick={onRefresh} disabled={refreshing} aria-label="Refresh all dashboard data">
            <RefreshCw size={15} />
            {refreshing ? `${shellI18n.t('button.refresh', 'Refresh')}...` : shellI18n.t('button.refresh', 'Refresh')}
          </button>
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
        <header className="topbar">
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
{shellI18n.languages.length > 1 ? (
<label className="topbar-select">
<span>{shellI18n.t('language.label', 'Language')}</span>
<select aria-label={shellI18n.t('language.label', 'Language')} value={shellI18n.language} onChange={event => handleLanguageChange(event.target.value)}>
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
              value={historyScope}
              onChange={event => handleHistoryScopeChange(event.target.value)}
              disabled={refreshing || !canUseLiveApi}
>
<option value="active">{shellI18n.t('option.active_sessions_only', 'Active')}</option>
<option value="all">{shellI18n.t('option.all_history', 'All history')}</option>
</select>
<small>{historyScopeDetail}</small>
          </label>
            <div className="row-limit-control" aria-label="Row limit control">
              <div className="row-limit-heading">
<span>Rows loaded</span>
<strong>{rowLimitValueLabel(pendingLoadLimit)}</strong>
</div>
<div className={`row-limit-status${refreshing ? ' is-loading' : ''}`} role="status" aria-live="polite">
{refreshing ? (
<>
<span className="row-loading-dot" aria-hidden="true" />
<span>{rowLoadingLabel}</span>
</>
) : (
<>
<span>{rowLoadModeLabel}</span>
<span>{rowLoadStatus}</span>
</>
)}
</div>
<div className="row-limit-range-meta">
                <span>Quick range</span>
              <span>{pendingLoadLimitUncapped ? 'No cap enabled' : 'No fixed max'}</span>
              </div>
              <input
                aria-label="Rows to load slider"
                aria-valuetext={
                  pendingLoadLimitUncapped
                ? 'No row cap; move slider or type a count to restore a finite limit'
                : `${finitePendingLoadLimit.toLocaleString()} rows; slider expands as needed, or type any count`
                }
                type="range"
                min={rowLimitMin}
                max={rowLimitSliderMax}
                step={rowLimitStep}
                value={rowLimitSliderValue}
onChange={event => handleLoadLimitSliderChange(event.target.value)}
disabled={refreshing || !canUseLiveApi}
/>
              <div className="row-limit-entry">
                <input
                  aria-label="Rows to load"
                type="number"
                min={rowLimitNoCap}
                step={rowLimitStep}
                value={pendingLoadLimit}
                onChange={event => handleLoadLimitDraftChange(event.target.value)}
                aria-describedby="row-limit-entry-help"
                disabled={refreshing || !canUseLiveApi}
              />
                <label className="row-limit-no-cap">
                  <input
                    aria-label="No row cap"
                    type="checkbox"
                    checked={pendingLoadLimitUncapped}
                    onChange={event => handleLoadLimitNoCapChange(event.target.checked)}
                    disabled={refreshing || !canUseLiveApi}
                  />
                <span>No cap</span>
              </label>
                <button type="button" onClick={applyLoadLimitChange} disabled={refreshing || !canUseLiveApi || !rowLimitChanged}>
              {pendingLoadLimitUncapped ? 'Load all' : shellI18n.t('nav.load', 'Load')}
</button>
</div>
<button className="row-limit-load-all" type="button" onClick={loadAllRows} disabled={!canLoadAllRows}>
Load all rows
</button>
<p id="row-limit-entry-help" className="row-limit-hint">
Use Load all rows for the full history, or type any finite row count.
</p>
              <div className="row-limit-load-more">
                <span>{rowLoadStatus}</span>
<button type="button" onClick={loadMoreRows} disabled={refreshing || !canUseLiveApi || !hasMoreRows}>
              {shellI18n.t('button.load_more', 'Load more')}
                </button>
              </div>
            </div>
        {activePreset ? (
          <button className="toolbar-button" type="button" onClick={clearInvestigationPreset}>
            <X size={15} />
            {shellI18n.t('button.clear', 'Clear')} {presetLabel(activePreset)}
          </button>
        ) : null}
        <StatusBadge label="Stored Snapshot" tone="blue" />
          <StatusBadge
            label={dashboardPayload?.api_token ? `${shellI18n.t('badge.live', 'Live')} API` : shellI18n.t('status.static', 'Static')}
            tone={dashboardPayload?.api_token ? 'green' : 'orange'}
          />
<label className="topbar-toggle">
          <input
            aria-label="Auto refresh"
            type="checkbox"
            checked={autoRefreshEnabled}
            onChange={event => handleAutoRefreshChange(event.target.checked)}
            disabled={refreshing || !canUseLiveApi}
/>
<span>{shellI18n.t('nav.live', 'Live')}</span>
</label>
<button className="icon-button" type="button" onClick={copyCurrentViewLink} aria-label={shellI18n.t('button.copy_link', 'Copy link')}>
<Copy size={17} />
</button>
<button className="icon-button" type="button" onClick={exportCurrentViewCsv} aria-label={shellI18n.t('button.export_csv', 'Export CSV')}>
<Download size={17} />
</button>
<button className="icon-button" type="button" onClick={onRefresh} aria-label={shellI18n.t('button.refresh', 'Refresh')} disabled={refreshing}>
<RefreshCw size={17} />
</button>
          </div>
      </header>
      {renderView(
        activeView,
        scopedModel,
          onRefresh,
          refreshState,
          globalQuery,
          activePreset,
          activeRecordId,
          contextRuntime,
          setContextApiEnabled,
openCallInvestigator,
copyCallInvestigatorLink,
openFindingInvestigator,
applyInvestigationPreset,
callReturnViewExplicit
  ? `Back to ${callReturnViewLabel(callReturnView)}`
  : shellI18n.t('button.back_to_dashboard', 'Back to dashboard'),
backFromCallInvestigator,
 dashboardPayload,
 historyScope,
 loadLimit,
 loadedRowCount,
 totalAvailableRows,
 canUseLiveApi,
 autoRefreshEnabled,
 refreshing,
 hasMoreRows,
 canLoadAllRows,
 loadMoreRows,
 loadAllRows,
 <ShellGlobalFilters activeView={activeView} locationSearch={locationSearch} model={model} onUrlChange={replaceShellUrl} />,
)}
      </main>
      {showBackToTop ? (
        <button className="to-top-button" type="button" onClick={scrollToTop} aria-label="Back to top">
          <ArrowUp size={18} />
          {shellI18n.t('button.top', 'Top')}
        </button>
      ) : null}
      </div>
    </ShellI18nProvider>
  );

  function onRefresh() {
    void refreshDashboard();
  }
}

function renderView(
  activeView: ViewId,
  model: DashboardModel,
  onRefresh: () => void,
  refreshState: string,
  globalQuery: string,
  activePreset: string,
  activeRecordId: string,
  contextRuntime: ContextRuntime,
  setContextApiEnabled: (enabled: boolean) => void,
openCallInvestigator: (recordId: string) => void,
copyCallInvestigatorLink: (recordId: string) => void,
openFindingInvestigator: (rank: number) => void,
_applyInvestigationPreset: (action: InvestigationPresetAction) => void,
  callBackLabel: string,
  backFromCallInvestigator: () => void,
  dashboardPayload: DashboardBootPayload | null,
  historyScope: HistoryScope,
  loadLimit: number,
 loadedRowCount: number,
 totalAvailableRows: number,
 canUseLiveApi: boolean,
 autoRefreshEnabled: boolean,
 refreshing: boolean,
 hasMoreRows: boolean,
 canLoadAllRows: boolean,
 loadMoreRows: () => void,
 loadAllRows: () => void,
 globalFilters: ReactNode,
) {
  switch (activeView) {
    case 'overview':
      return (
        <OverviewPage
          model={model}
          onRefresh={onRefresh}
        refreshState={refreshState}
        globalQuery={globalQuery}
        runtime={{ historyScope, loadLimit, loadedRowCount, totalAvailableRows }}
        refreshing={refreshing}
        canLoadMoreRows={canUseLiveApi && hasMoreRows}
        canLoadAllRows={canLoadAllRows}
        onLoadMoreRows={loadMoreRows}
        onLoadAllRows={loadAllRows}
	onOpenInvestigator={openCallInvestigator}
	onCopyCallLink={copyCallInvestigatorLink}
	onOpenFinding={openFindingInvestigator}
	globalFilters={globalFilters}
/>
      );
    case 'investigator':
      return <InvestigatorPage model={model} onOpenInvestigator={openCallInvestigator} onCopyCallLink={copyCallInvestigatorLink} />;
    case 'calls':
      return (
        <CallsPage
          model={model}
          globalQuery={globalQuery}
          activePreset={activePreset}
          onRefresh={onRefresh}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={setContextApiEnabled}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
    case 'call':
      return (
        <CallInvestigatorPage
          model={model}
          recordId={activeRecordId}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={setContextApiEnabled}
          onNavigateRecord={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          onBackToCalls={backFromCallInvestigator}
          backLabel={callBackLabel}
        />
      );
    case 'threads':
      return (
        <ThreadsPage
          model={model}
          globalQuery={globalQuery}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          globalFilters={globalFilters}
        />
      );
    case 'usage-drain':
      return <UsageDrainPage model={model} onOpenInvestigator={openCallInvestigator} onCopyCallLink={copyCallInvestigatorLink} />;
    case 'cache-context':
      return (
        <CacheContextPage
          model={model}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
    case 'diagnostics':
      return (
        <DiagnosticsPage
          model={model}
          contextRuntime={contextRuntime}
          rowLoadControls={{
            loadedRowCount,
            totalAvailableRows,
            canLoadMoreRows: canUseLiveApi && hasMoreRows,
            canLoadAllRows,
            refreshing,
            onLoadMoreRows: loadMoreRows,
            onLoadAllRows: loadAllRows,
          }}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          globalFilters={globalFilters}
        />
      );
    case 'reports':
      return (
        <ReportsPage
          model={model}
          onRefresh={onRefresh}
          refreshState={refreshState}
          includeArchived={historyScope === 'all'}
          loadLimit={loadLimit}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
case 'settings':
return (
<SettingsPage
          model={model}
          payload={dashboardPayload}
          historyScope={historyScope}
          loadLimit={loadLimit}
          loadedRowCount={loadedRowCount}
          totalAvailableRows={totalAvailableRows}
          canUseLiveApi={canUseLiveApi}
          autoRefreshEnabled={autoRefreshEnabled}
          refreshState={refreshState}
        />
);
}
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
