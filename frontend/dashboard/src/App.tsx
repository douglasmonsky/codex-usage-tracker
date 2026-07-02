import { RefreshCw, Terminal } from 'lucide-react';
import { useMemo, useState } from 'react';
import { isViewId, navItems, secondaryNavItems, type ViewId } from './app/navigation';
import { modelFromBootPayload, readBootPayload } from './api/client';
import type { ContextRuntime, DashboardModel } from './api/types';
import { StatusBadge } from './components/StatusBadge';
import { CallInvestigatorPage } from './features/call-investigator/CallInvestigatorPage';
import { CacheContextPage } from './features/cache-context/CacheContextPage';
import { CallsPage } from './features/calls/CallsPage';
import { DiagnosticsPage } from './features/diagnostics/DiagnosticsPage';
import { InvestigatorPage } from './features/investigator/InvestigatorPage';
import { OverviewPage } from './features/overview/OverviewPage';
import { ReportsPage } from './features/reports/ReportsPage';
import { SettingsPage } from './features/settings/SettingsPage';
import { ThreadsPage } from './features/threads/ThreadsPage';
import { UsageDrainPage } from './features/usage-drain/UsageDrainPage';

export function App() {
  const model = useMemo(() => modelFromBootPayload(readBootPayload()), []);
  const [activeView, setActiveView] = useState<ViewId>(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedView = params.get('view');
    return isViewId(requestedView) ? requestedView : 'overview';
  });
  const [activeRecordId, setActiveRecordId] = useState(
    () => new URLSearchParams(window.location.search).get('record') ?? '',
  );
  const [globalQuery, setGlobalQuery] = useState(() => new URLSearchParams(window.location.search).get('q') ?? '');
  const [refreshState, setRefreshState] = useState('Stored snapshot loaded just now');
  const [contextApiEnabled, setContextApiEnabled] = useState(model.contextRuntime.contextApiEnabled);
  const contextRuntime = useMemo<ContextRuntime>(
    () => ({ ...model.contextRuntime, contextApiEnabled }),
    [contextApiEnabled, model.contextRuntime],
  );

  function setView(view: ViewId) {
    setActiveView(view);
    const url = new URL(window.location.href);
    url.searchParams.set('view', view);
    if (view !== 'call') {
      url.searchParams.delete('record');
      setActiveRecordId('');
    }
    window.history.replaceState(null, '', url);
  }

  function openCallInvestigator(recordId: string) {
    setActiveView('call');
    setActiveRecordId(recordId);
    const url = new URL(window.location.href);
    url.searchParams.set('view', 'call');
    url.searchParams.set('record', recordId);
    window.history.replaceState(null, '', url);
  }

  function updateGlobalQuery(value: string) {
    setGlobalQuery(value);
    const url = new URL(window.location.href);
    if (value) {
      url.searchParams.set('q', value);
    } else {
      url.searchParams.delete('q');
    }
    window.history.replaceState(null, '', url);
  }

  function handleRefresh() {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setRefreshState(`Stored snapshot refreshed at ${timestamp}`);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Terminal size={22} />
          </div>
          <div>
            <strong>Codex Usage Tracker</strong>
            <span>Local telemetry console</span>
          </div>
        </div>
        <div className="local-pill">
          <span aria-hidden="true" />
          Local data only
        </div>
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
                <span>{item.label}</span>
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
          <small>{refreshState}</small>
          <button type="button" onClick={handleRefresh}>
            <RefreshCw size={15} />
            Refresh all
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <label className="global-search">
            <span className="sr-only">Search dashboard</span>
            <input
              aria-label="Search dashboard"
              value={globalQuery}
              onChange={event => updateGlobalQuery(event.target.value)}
              placeholder="Search calls, threads, models, diagnostics..."
            />
          </label>
          <div className="topbar-actions">
            <StatusBadge label="Stored Snapshot" tone="blue" />
            <StatusBadge label="Live API" tone="green" />
            <button className="icon-button" type="button" onClick={handleRefresh} aria-label="Refresh dashboard">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        {renderView(
          activeView,
          model,
          onRefresh,
          refreshState,
          globalQuery,
          activeRecordId,
          contextRuntime,
          setContextApiEnabled,
          openCallInvestigator,
          setView,
        )}
      </main>
    </div>
  );

  function onRefresh() {
    handleRefresh();
  }
}

function renderView(
  activeView: ViewId,
  model: DashboardModel,
  onRefresh: () => void,
  refreshState: string,
  globalQuery: string,
  activeRecordId: string,
  contextRuntime: ContextRuntime,
  setContextApiEnabled: (enabled: boolean) => void,
  openCallInvestigator: (recordId: string) => void,
  setView: (view: ViewId) => void,
) {
  switch (activeView) {
    case 'overview':
      return <OverviewPage model={model} onRefresh={onRefresh} refreshState={refreshState} globalQuery={globalQuery} />;
    case 'investigator':
      return <InvestigatorPage model={model} />;
    case 'calls':
      return (
        <CallsPage
          model={model}
          globalQuery={globalQuery}
          onRefresh={onRefresh}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={setContextApiEnabled}
          onOpenInvestigator={openCallInvestigator}
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
          onBackToCalls={() => setView('calls')}
        />
      );
    case 'threads':
      return <ThreadsPage model={model} globalQuery={globalQuery} />;
    case 'usage-drain':
      return <UsageDrainPage model={model} />;
    case 'cache-context':
      return <CacheContextPage model={model} />;
    case 'diagnostics':
      return <DiagnosticsPage model={model} />;
    case 'reports':
      return <ReportsPage model={model} />;
    case 'settings':
      return <SettingsPage />;
  }
}
