import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useMemo, type ReactNode } from 'react';

import type { ContextRuntime, ConversationalReadiness, DashboardModel } from '../../api/types';
import type { LoadWindow } from '../../data/dataScope';
import {
  dashboardModuleProgress,
  deriveDashboardModuleState,
} from '../../data/dashboardQueryRegistry';
import { Button, PageLoadProgress, StatusBadge } from '../../design';
import {
  overviewRecommendationsQueryOptions,
  overviewSummaryQueryOptions,
  type OverviewEndpointBundle,
} from '../../data/overviewQueries';
import { Visualization } from '../../visualization';
import { OverviewMetrics } from './OverviewMetrics';
import styles from './OverviewPage.module.css';
import { OverviewRecentCalls } from './OverviewRecentCalls';
import { ConversationalAnalysisStatus } from '../shared/ConversationalAnalysisStatus';
import { buildOverviewViewModel } from './overviewModel';
import type { OverviewNavigationTarget } from './overviewNavigation';

export { overviewCallsForQuery } from './overviewCalls';

type OverviewRuntime = {
  historyScope: 'active' | 'all';
  loadLimit: number;
  loadWindow: LoadWindow;
  loadedRowCount: number;
  scopeSince: string | null;
  totalAvailableRows: number;
};

type OverviewPageProps = {
  conversationalAnalysis?: ConversationalReadiness;
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  sourceRevision: string;
  sourceKey?: string;
  onRefresh: () => void;
  globalQuery: string;
  runtime: OverviewRuntime;
  refreshing: boolean;
  canLoadMoreRows: boolean;
  onLoadMoreRows: () => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onNavigateView: (view: OverviewNavigationTarget) => void;
  focusedEndpointsEnabled?: boolean;
  globalFilters?: ReactNode;
};

export function OverviewPage(props: OverviewPageProps) {
  const focusedEndpointsEnabled = props.focusedEndpointsEnabled ?? import.meta.env.MODE !== 'test';
  const canUseFocusedEndpoints = focusedEndpointsEnabled && !props.contextRuntime.fileMode && Boolean(props.contextRuntime.apiToken);
  const queryRequest = {
    runtime: props.contextRuntime,
    includeArchived: props.runtime.historyScope === 'all',
    since: props.runtime.scopeSince ?? undefined,
    sourceRevision: props.sourceRevision,
    sourceKey: props.sourceKey,
  };
  const summaryQuery = useQuery({
    ...overviewSummaryQueryOptions(queryRequest),
    enabled: canUseFocusedEndpoints,
    placeholderData: previous => previous,
  });
  const recommendationsQuery = useQuery({
    ...overviewRecommendationsQueryOptions(queryRequest),
    enabled: canUseFocusedEndpoints,
    placeholderData: previous => previous,
  });
  const focusedData = useMemo<OverviewEndpointBundle | undefined>(() => (
    canUseFocusedEndpoints
      ? {
          summary: {
            data: summaryQuery.data ?? null,
            error: summaryQuery.error ? queryErrorMessage(summaryQuery.error) : null,
          },
          recommendations: {
            data: recommendationsQuery.data ?? null,
            error: recommendationsQuery.error ? queryErrorMessage(recommendationsQuery.error) : null,
          },
        }
      : undefined
  ), [
    canUseFocusedEndpoints,
    recommendationsQuery.data,
    recommendationsQuery.error,
    summaryQuery.data,
    summaryQuery.error,
  ]);
  const viewModel = useMemo(
    () => buildOverviewViewModel(props.model, focusedData, props.runtime.historyScope),
    [focusedData, props.model, props.runtime.historyScope],
  );
  const queryError = summaryQuery.error ?? recommendationsQuery.error;
  const endpointError = queryError
    ? queryErrorMessage(queryError)
    : focusedData?.summary.error || focusedData?.recommendations.error || null;
  const isFetching = summaryQuery.isFetching || recommendationsQuery.isFetching;
  const modules = [
    {
      label: 'Usage summary',
      status: deriveDashboardModuleState({
        enabled: canUseFocusedEndpoints,
        hasData: Boolean(summaryQuery.data),
        isError: summaryQuery.isError,
        isFetching: summaryQuery.isFetching,
        isPending: summaryQuery.isPending,
      }),
    },
    {
      label: 'Recommendations',
      status: deriveDashboardModuleState({
        enabled: canUseFocusedEndpoints,
        hasData: Boolean(recommendationsQuery.data),
        isError: recommendationsQuery.isError,
        isFetching: recommendationsQuery.isFetching,
        isPending: recommendationsQuery.isPending,
      }),
    },
  ];
  const progress = dashboardModuleProgress(modules.map(module => module.status));
  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Usage pulse</p><h1>Overview</h1><p>The important changes first, with direct paths into supporting evidence.</p></div>
        <div className={styles.headerActions}>
          <StatusBadge tone={endpointTone(focusedData, queryError, canUseFocusedEndpoints)}>{endpointLabel(isFetching, focusedData, queryError, canUseFocusedEndpoints)}</StatusBadge>
          <Button variant="primary" onClick={props.onRefresh} disabled={props.refreshing}><RefreshCw /> {props.refreshing ? 'Refreshing...' : 'Refresh data'}</Button>
        </div>
      </header>

      <PageLoadProgress
        active={canUseFocusedEndpoints && isFetching}
        completed={progress.ready}
        total={progress.total}
        label="Loading overview evidence"
        error={canUseFocusedEndpoints ? endpointError : null}
        modules={modules}
        updating={modules.some(module => module.status === 'updating')}
      />

      <ConversationalAnalysisStatus readiness={props.conversationalAnalysis} />

      <OverviewMetrics
        metrics={viewModel.metrics}
        loadedCalls={props.runtime.loadedRowCount}
        availableCalls={props.runtime.totalAvailableRows}
      />

      <div className={styles.analysisGrid}>
        <Visualization spec={viewModel.pulseSpec} height={280} />
        <Visualization spec={viewModel.tokenFlowSpec} height={320} />
      </div>

      <OverviewRecentCalls
        calls={props.model.calls}
        globalFilters={props.globalFilters}
        globalQuery={props.globalQuery}
        loadedRowCount={props.runtime.loadedRowCount}
        totalAvailableRows={props.runtime.totalAvailableRows}
        refreshing={props.refreshing}
        canLoadMoreRows={props.canLoadMoreRows}
        onLoadMoreRows={props.onLoadMoreRows}
        onBrowseCalls={() => props.onNavigateView('calls')}
        onOpenCall={props.onOpenInvestigator}
        onCopyCallLink={props.onCopyCallLink}
      />
    </div>
  );
}

function queryErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function endpointLabel(isFetching: boolean, data: OverviewEndpointBundle | undefined, error: Error | null, enabled: boolean): string {
  if (!enabled) return 'Stored snapshot';
  if (isFetching && (data?.summary.data || data?.recommendations.data)) return 'Updating evidence';
  if (isFetching) return 'Loading evidence';
  if (error) return 'Endpoint fallback';
  if (data?.summary.error || data?.recommendations.error) return 'Partial endpoint evidence';
  return 'Focused endpoints';
}

function endpointTone(data: OverviewEndpointBundle | undefined, error: Error | null, enabled: boolean): 'positive' | 'caution' | 'neutral' {
  if (!enabled) return 'neutral';
  return error && !data || data?.summary.error || data?.recommendations.error ? 'caution' : 'positive';
}
