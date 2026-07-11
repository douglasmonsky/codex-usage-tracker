import { lazyRouteComponent } from '@tanstack/react-router';
import { Suspense, type ReactNode } from 'react';

import type { ContextRuntime, DashboardBootPayload, DashboardModel } from '../api/types';
import type { HistoryScope } from '../data/dataScope';
import type { DashboardViewId } from './dashboardSearch';

const OverviewPage = lazyRouteComponent(() => import('../features/overview/OverviewPage'), 'OverviewPage');
const InvestigatorPage = lazyRouteComponent(() => import('../features/investigator/InvestigatorPage'), 'InvestigatorPage');
const CallsPage = lazyRouteComponent(() => import('../features/calls/CallsPage'), 'CallsPage');
const CallInvestigatorPage = lazyRouteComponent(
  () => import('../features/call-investigator/CallInvestigatorPage'),
  'CallInvestigatorPage',
);
const ThreadsPage = lazyRouteComponent(() => import('../features/threads/ThreadsPage'), 'ThreadsPage');
const UsageDrainPage = lazyRouteComponent(() => import('../features/usage-drain/UsageDrainPage'), 'UsageDrainPage');
const CacheContextPage = lazyRouteComponent(() => import('../features/cache-context/CacheContextPage'), 'CacheContextPage');
const DiagnosticsPage = lazyRouteComponent(() => import('../features/diagnostics/DiagnosticsPage'), 'DiagnosticsPage');
const ReportsPage = lazyRouteComponent(() => import('../features/reports/ReportsPage'), 'ReportsPage');
const SettingsPage = lazyRouteComponent(() => import('../features/settings/SettingsPage'), 'SettingsPage');

const dashboardRouteComponents = [
  OverviewPage,
  InvestigatorPage,
  CallsPage,
  CallInvestigatorPage,
  ThreadsPage,
  UsageDrainPage,
  CacheContextPage,
  DiagnosticsPage,
  ReportsPage,
  SettingsPage,
];

export async function preloadDashboardRouteViews() {
  await Promise.all(dashboardRouteComponents.map(component => component.preload?.()));
}

type DashboardRouteViewProps = {
  activePreset: string;
  activeRecordId: string;
  activeView: DashboardViewId;
  autoRefreshEnabled: boolean;
  backFromCallInvestigator: () => void;
  callBackLabel: string;
  canLoadAllRows: boolean;
  canUseLiveApi: boolean;
  contextRuntime: ContextRuntime;
  copyCallInvestigatorLink: (recordId: string) => void;
  dashboardPayload: DashboardBootPayload | null;
  globalFilters: ReactNode;
  globalQuery: string;
  hasMoreRows: boolean;
  historyScope: HistoryScope;
  loadAllRows: () => void;
  loadedRowCount: number;
  loadLimit: number;
  loadMoreRows: () => void;
  model: DashboardModel;
  navigateView: (view: DashboardViewId) => void;
  onRefresh: () => void;
  openCallInvestigator: (recordId: string) => void;
  openFindingInvestigator: (rank: number) => void;
  refreshing: boolean;
  refreshState: string;
  setContextApiEnabled: (enabled: boolean) => void;
  totalAvailableRows: number;
};

export function DashboardRouteView(props: DashboardRouteViewProps) {
  return (
    <Suspense fallback={<DashboardViewPending activeView={props.activeView} />}>
      {renderDashboardView(props)}
    </Suspense>
  );
}

function renderDashboardView(props: DashboardRouteViewProps) {
  const {
    activePreset,
    activeRecordId,
    activeView,
    autoRefreshEnabled,
    backFromCallInvestigator,
    callBackLabel,
    canLoadAllRows,
    canUseLiveApi,
    contextRuntime,
    copyCallInvestigatorLink,
    dashboardPayload,
    globalFilters,
    globalQuery,
    hasMoreRows,
    historyScope,
    loadAllRows,
    loadedRowCount,
    loadLimit,
    loadMoreRows,
    model,
    navigateView,
    onRefresh,
    openCallInvestigator,
    openFindingInvestigator,
    refreshing,
    refreshState,
    setContextApiEnabled,
    totalAvailableRows,
  } = props;

  switch (activeView) {
    case 'overview':
      return (
        <OverviewPage
          model={model}
          contextRuntime={contextRuntime}
          sourceRevision={String(dashboardPayload?.latest_refresh_at ?? '')}
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
          onNavigateView={navigateView}
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
      return <ThreadsPage model={model} globalQuery={globalQuery} onOpenInvestigator={openCallInvestigator} onCopyCallLink={copyCallInvestigatorLink} globalFilters={globalFilters} />;
    case 'usage-drain':
      return <UsageDrainPage model={model} onOpenInvestigator={openCallInvestigator} onCopyCallLink={copyCallInvestigatorLink} />;
    case 'cache-context':
      return <CacheContextPage model={model} onOpenInvestigator={openCallInvestigator} onCopyCallLink={copyCallInvestigatorLink} />;
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

function DashboardViewPending({ activeView }: { activeView: DashboardViewId }) {
  return (
    <section aria-busy="true" aria-live="polite" className="route-state" role="status">
      Loading {activeView.replace('-', ' ')}...
    </section>
  );
}
