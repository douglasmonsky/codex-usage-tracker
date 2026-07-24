import { lazyRouteComponent } from '@tanstack/react-router';
import { Suspense, type ReactNode } from 'react';

import type { ContextRuntime, ConversationalReadiness, DashboardBootPayload, DashboardLanguage, DashboardModel, HomeSummaryPayload } from '../api/types';
import type { HistoryScope, LoadWindow } from '../data/dataScope';
import type { DashboardSourceIdentity } from '../data/queryRuntime';
import type { DashboardViewId } from './dashboardSearch';

const HomePage = lazyRouteComponent(() => import('../features/home/HomePage'), 'HomePage');
const LegacyWorkbenchNotice = lazyRouteComponent(
  () => import('../features/compatibility/LegacyWorkbenchNotice'),
  'LegacyWorkbenchNotice',
);
const ExplorePage = lazyRouteComponent(() => import('../features/explore/ExplorePage'), 'ExplorePage');
const CallInvestigatorPage = lazyRouteComponent(
  () => import('../features/call-investigator/CallInvestigatorPage'),
  'CallInvestigatorPage',
);
const EvidencePage = lazyRouteComponent(
  () => import('../features/evidence/EvidencePage'),
  'EvidencePage',
);
const UsageDrainPage = lazyRouteComponent(() => import('../features/usage-drain/UsageDrainPage'), 'UsageDrainPage');
const SettingsPage = lazyRouteComponent(() => import('../features/settings/SettingsPage'), 'SettingsPage');

const dashboardRouteComponents: Array<{
  id: DashboardViewId;
  component: { preload?: () => Promise<unknown> };
}> = [
  { id: 'home', component: HomePage },
  { id: 'explore', component: ExplorePage },
  { id: 'limits', component: UsageDrainPage },
  { id: 'evidence', component: EvidencePage },
  { id: 'overview', component: HomePage },
  { id: 'investigator', component: LegacyWorkbenchNotice },
  { id: 'compression-lab', component: LegacyWorkbenchNotice },
  { id: 'calls', component: ExplorePage },
  { id: 'call', component: CallInvestigatorPage },
  { id: 'threads', component: ExplorePage },
  { id: 'usage-drain', component: UsageDrainPage },
  { id: 'cache-context', component: LegacyWorkbenchNotice },
  { id: 'diagnostics', component: LegacyWorkbenchNotice },
  { id: 'reports', component: LegacyWorkbenchNotice },
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
  compatibilityLabs: readonly {
    id: string;
    label: string;
    maturity: string;
    lifecycle: string;
    replacementMcpOperation: string;
  }[];
  contextRuntime: ContextRuntime;
  conversationalAnalysis?: ConversationalReadiness;
  copyCallInvestigatorLink: (recordId: string) => void;
  dashboardPayload: DashboardBootPayload | null;
  globalFilters: ReactNode;
  globalQuery: string;
  hasMoreRows: boolean;
  historyScope: HistoryScope;
  homeSummary?: HomeSummaryPayload;
  homeStatusLoading: boolean;
  homeStatusError: string | null;
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
  refreshProgressPercent: number | null;
  refreshProgressText: string;
  refreshState: string;
  setShowExperimental: (showExperimental: boolean) => void;
  setContextApiEnabled: (enabled: boolean) => void;
  showExperimental: boolean;
  sourceIdentity: DashboardSourceIdentity;
  threadsModel: DashboardModel;
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
    canUseLiveApi,
    compatibilityLabs,
    contextRuntime,
    conversationalAnalysis,
    copyCallInvestigatorLink,
    dashboardPayload,
    globalFilters,
    globalQuery,
    historyScope,
    homeSummary,
    homeStatusLoading,
    homeStatusError,
    loadWindow,
    loadedRowCount,
    loadLimit,
    scopeSince,
    model,
    navigateView,
    onRefresh,
    openCallInvestigator,
    refreshing,
    refreshProgressPercent,
    refreshProgressText,
    refreshState,
    setShowExperimental,
    setContextApiEnabled,
    showExperimental,
    sourceIdentity,
    threadsModel,
    totalAvailableRows,
  } = props;

  const renderedView = renderedDashboardView(activeView);
  switch (renderedView) {
    case 'overview':
      return (
        <HomePage
          model={model}
          payload={dashboardPayload}
          summary={homeSummary}
          readiness={conversationalAnalysis}
          historyScope={historyScope}
          loadWindow={loadWindow}
          loadLimit={loadLimit}
          scopeSince={scopeSince}
          refreshing={refreshing}
          refreshProgressPercent={refreshProgressPercent}
          refreshProgressText={refreshProgressText}
          homeStatusLoading={homeStatusLoading}
          homeStatusError={homeStatusError}
          onRefresh={onRefresh}
          onNavigate={navigateView}
          onOpenCall={openCallInvestigator}
        />
      );
    case 'investigator':
    case 'compression-lab':
    case 'cache-context':
    case 'diagnostics':
    case 'reports':
      return (
        <LegacyWorkbenchNotice
          viewId={renderedView}
          onNavigate={navigateView}
        />
      );
    case 'explore':
    case 'calls':
    case 'threads':
      return (
        <ExplorePage
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
          globalFilters={globalFilters}
          threadsModel={threadsModel}
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
    case 'evidence':
      return (
        <EvidencePage
          model={model}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={setContextApiEnabled}
          onNavigateRecord={openCallInvestigator}
          onCopyCallLink={copyCallInvestigatorLink}
          callBackLabel={callBackLabel}
          onCallBack={backFromCallInvestigator}
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
          compatibilityLabs={compatibilityLabs}
          showExperimental={showExperimental}
          setShowExperimental={setShowExperimental}
        />
      );
    default:
      return assertNever(renderedView);
  }
}

type RenderedDashboardViewId = Exclude<
  DashboardViewId,
  'home' | 'limits'
>;

function renderedDashboardView(activeView: DashboardViewId): RenderedDashboardViewId {
  if (activeView === 'home') return 'overview';
  if (activeView === 'explore') return 'explore';
  if (activeView === 'limits') return 'usage-drain';
  return activeView;
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
