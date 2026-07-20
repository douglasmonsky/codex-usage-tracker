import { lazyRouteComponent } from '@tanstack/react-router';
import { Suspense, type ReactNode } from 'react';

import type { ContextRuntime, ConversationalReadiness, DashboardBootPayload, DashboardLanguage, DashboardModel } from '../api/types';
import type { HistoryScope, LoadWindow } from '../data/dataScope';
import type { DashboardSourceIdentity } from '../data/queryRuntime';
import type { DashboardViewId } from './dashboardSearch';

const OverviewPage = lazyRouteComponent(() => import('../features/overview/OverviewPage'), 'OverviewPage');
const InvestigatorPage = lazyRouteComponent(() => import('../features/investigator/InvestigatorPage'), 'InvestigatorPage');
const CompressionLabPage = lazyRouteComponent(() => import('../features/compression-lab/CompressionLabPage'), 'CompressionLabPage');
const ExploreRoutePage = lazyRouteComponent(() => import('../features/explore/ExploreRoutePage'), 'ExploreRoutePage');
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

const dashboardRouteComponents: Array<{
  id: DashboardViewId;
  component: { preload?: () => Promise<unknown> };
}> = [
  { id: 'overview', component: OverviewPage },
  { id: 'investigator', component: InvestigatorPage },
  { id: 'compression-lab', component: CompressionLabPage },
  { id: 'calls', component: ExploreRoutePage },
  { id: 'call', component: CallInvestigatorPage },
  { id: 'threads', component: ThreadsPage },
  { id: 'usage-drain', component: UsageDrainPage },
  { id: 'cache-context', component: CacheContextPage },
  { id: 'diagnostics', component: DiagnosticsPage },
  { id: 'reports', component: ReportsPage },
  { id: 'settings', component: SettingsPage },
];

export const dashboardRenderedViewIds: DashboardViewId[] = dashboardRouteComponents.map(route => route.id);

export async function preloadDashboardRouteViews() {
  await Promise.all(dashboardRouteComponents.map(route => route.component.preload?.()));
}

type DashboardRouteViewProps = {
  activePreset: string;
  activeRecordId: string;
  activeView: DashboardViewId;
  autoRefreshEnabled: boolean;
  applicationI18n: { language: string; direction: 'ltr' | 'rtl'; languages: DashboardLanguage[] };
  backFromCallInvestigator: () => void;
  callBackLabel: string;
  canLoadAllRows: boolean;
  canUseLiveApi: boolean;
  contextRuntime: ContextRuntime;
  conversationalAnalysis?: ConversationalReadiness;
  copyCallInvestigatorLink: (recordId: string) => void;
  dashboardPayload: DashboardBootPayload | null;
  globalFilters: ReactNode;
  globalQuery: string;
  hasMoreRows: boolean;
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  loadAllRows: () => void;
  loadedRowCount: number;
  loadLimit: number;
  loadMoreRows: () => void;
  scopeSince: string | null;
  model: DashboardModel;
  navigateView: (view: DashboardViewId) => void;
  onRefresh: () => void;
  openCallInvestigator: (recordId: string) => void;
  refreshing: boolean;
  refreshState: string;
  setShowExperimental: (showExperimental: boolean) => void;
  setContextApiEnabled: (enabled: boolean) => void;
  showExperimental: boolean;
  sourceIdentity: DashboardSourceIdentity;
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
    applicationI18n,
    backFromCallInvestigator,
    callBackLabel,
    canLoadAllRows,
    canUseLiveApi,
    contextRuntime,
    conversationalAnalysis,
    copyCallInvestigatorLink,
    dashboardPayload,
    globalFilters,
    globalQuery,
    hasMoreRows,
    historyScope,
    loadWindow,
    loadAllRows,
    loadedRowCount,
    loadLimit,
    loadMoreRows,
    scopeSince,
    model,
    navigateView,
    onRefresh,
    openCallInvestigator,
    refreshing,
    refreshState,
    setShowExperimental,
    setContextApiEnabled,
    showExperimental,
    sourceIdentity,
    totalAvailableRows,
  } = props;

  switch (activeView) {
    case 'overview':
      return (
        <OverviewPage
          conversationalAnalysis={conversationalAnalysis}
          model={model}
          contextRuntime={contextRuntime}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onRefresh={onRefresh}
          globalQuery={globalQuery}
          runtime={{ historyScope, loadLimit, loadWindow, loadedRowCount, scopeSince, totalAvailableRows }}
          refreshing={refreshing}
          canLoadMoreRows={canUseLiveApi && hasMoreRows}
          onLoadMoreRows={loadMoreRows}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          onNavigateView={navigateView}
          globalFilters={globalFilters}
        />
      );
    case 'investigator':
      return (
        <InvestigatorPage
          model={model}
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          onNavigateView={navigateView}
        />
      );
    case 'compression-lab':
      return (
        <CompressionLabPage
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          since={scopeSince}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
        />
      );
    case 'calls':
      return (
        <ExploreRoutePage
          model={model}
          globalQuery={globalQuery}
          activePreset={activePreset}
          onRefresh={onRefresh}
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          scopeSince={scopeSince}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onContextApiEnabledChange={setContextApiEnabled}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          onNavigateView={navigateView}
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
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onNavigateView={navigateView}
        />
      );
    case 'usage-drain':
      return (
        <UsageDrainPage
          model={model}
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          sourceRevision={sourceIdentity.sourceRevision}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
    case 'cache-context':
      return (
        <CacheContextPage
          model={model}
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          scopeSince={scopeSince}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
    case 'diagnostics':
      return (
        <DiagnosticsPage
          model={model}
          contextRuntime={contextRuntime}
          includeArchived={historyScope === 'all'}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
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
          refreshState={refreshState}
          includeArchived={historyScope === 'all'}
          loadWindow={loadWindow}
          loadLimit={loadLimit}
          sourceKey={sourceIdentity.sourceKey}
          sourceRevision={sourceIdentity.sourceRevision}
          onOpenInvestigator={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
        />
      );
    case 'settings':
      return (
        <SettingsPage
          conversationalAnalysis={conversationalAnalysis}
          model={model}
          payload={dashboardPayload}
          historyScope={historyScope}
          loadWindow={loadWindow}
          loadLimit={loadLimit}
          scopeSince={scopeSince}
          loadedRowCount={loadedRowCount}
          totalAvailableRows={totalAvailableRows}
          canUseLiveApi={canUseLiveApi}
          autoRefreshEnabled={autoRefreshEnabled}
          refreshState={refreshState}
          applicationI18n={applicationI18n}
          showExperimental={showExperimental}
          setShowExperimental={setShowExperimental}
        />
      );
    default:
      return assertNever(activeView);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled dashboard route: ${String(value)}`);
}

function DashboardViewPending({ activeView }: { activeView: DashboardViewId }) {
  return (
    <section aria-busy="true" aria-live="polite" className="route-state" role="status">
      Loading {activeView.replace('-', ' ')}...
    </section>
  );
}
