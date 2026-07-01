import { RefreshCw, Terminal } from 'lucide-react';
import { useMemo, useState } from 'react';

import { isViewId, navItems, secondaryNavItems, type ViewId } from './app/navigation';
import { modelFromBootPayload, readBootPayload } from './api/client';
import { StatusBadge } from './components/StatusBadge';
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
  const [refreshState, setRefreshState] = useState('Stored snapshot loaded just now');

  function setView(view: ViewId) {
    setActiveView(view);
    const url = new URL(window.location.href);
    url.searchParams.set('view', view);
    window.history.replaceState(null, '', url);
  }

  function handleRefresh() {
    setRefreshState(`Manual refresh requested ${new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())}`);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <Terminal size={22} />
          </div>
          <div>
            <strong>Codex Usage Tracker</strong>
            <span>Local Telemetry Console</span>
          </div>
        </div>
        <div className="local-pill">
          <i />
          Local data only
        </div>
        <nav className="primary-nav" aria-label="Dashboard views">
          {navItems.map(item => {
            const Icon = item.icon;
            return (
              <button
                type="button"
                key={item.id}
                aria-pressed={activeView === item.id}
                className={activeView === item.id ? 'active' : ''}
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
              <button type="button" key={item.label}>
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
            <RefreshCw size={15} /> Refresh all
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <label className="global-search">
            <span className="sr-only">Search dashboard</span>
            <input placeholder="Search calls, threads, models, diagnostics..." />
          </label>
          <div className="topbar-actions">
            <StatusBadge label="Stored Snapshot" tone="blue" />
            <StatusBadge label="Live API" tone="green" />
            <button className="icon-button" type="button" onClick={handleRefresh} aria-label="Refresh dashboard">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        {renderView(activeView, model, handleRefresh, refreshState)}
      </main>
    </div>
  );
}

function renderView(
  activeView: ViewId,
  model: ReturnType<typeof modelFromBootPayload>,
  onRefresh: () => void,
  refreshState: string,
) {
  switch (activeView) {
    case 'overview':
      return <OverviewPage model={model} onRefresh={onRefresh} refreshState={refreshState} />;
    case 'investigator':
      return <InvestigatorPage model={model} />;
    case 'calls':
      return <CallsPage model={model} />;
    case 'threads':
      return <ThreadsPage model={model} />;
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
