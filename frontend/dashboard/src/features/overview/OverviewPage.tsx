import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useMemo, type ReactNode } from 'react';

import type { ContextRuntime, DashboardModel } from '../../api/types';
import type { LoadWindow } from '../../data/dataScope';
import { Button, StatusBadge } from '../../design';
import { overviewQueryOptions, type OverviewEndpointBundle } from '../../data/overviewQueries';
import { Visualization } from '../../visualization';
import { OverviewMetrics } from './OverviewMetrics';
import styles from './OverviewPage.module.css';
import { OverviewRecentCalls } from './OverviewRecentCalls';
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
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  sourceRevision: string;
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
  const focusedQuery = useQuery({
    ...overviewQueryOptions({
      runtime: props.contextRuntime,
      includeArchived: props.runtime.historyScope === 'all',
      since: props.runtime.scopeSince ?? undefined,
      sourceRevision: props.sourceRevision,
    }),
    enabled: canUseFocusedEndpoints,
    placeholderData: previous => previous,
  });
  const viewModel = useMemo(
    () => buildOverviewViewModel(props.model, focusedQuery.data, props.runtime.historyScope),
    [focusedQuery.data, props.model, props.runtime.historyScope],
  );
  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Usage pulse</p><h1>Overview</h1><p>The important changes first, with direct paths into supporting evidence.</p></div>
        <div className={styles.headerActions}>
          <StatusBadge tone={endpointTone(focusedQuery.data, focusedQuery.error, canUseFocusedEndpoints)}>{endpointLabel(focusedQuery.isFetching, focusedQuery.data, focusedQuery.error, canUseFocusedEndpoints)}</StatusBadge>
          <Button variant="primary" onClick={props.onRefresh} disabled={props.refreshing}><RefreshCw /> {props.refreshing ? 'Refreshing...' : 'Refresh data'}</Button>
        </div>
      </header>

      <OverviewMetrics
        metrics={viewModel.metrics}
        loadedCalls={props.runtime.loadedRowCount}
        availableCalls={props.runtime.totalAvailableRows}
      />

      <div className={styles.analysisGrid}>
        <Visualization spec={viewModel.pulseSpec} height={280} />
        <Visualization spec={viewModel.tokenFlowSpec} height={280} />
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

function endpointLabel(isFetching: boolean, data: OverviewEndpointBundle | undefined, error: Error | null, enabled: boolean): string {
  if (!enabled) return 'Stored snapshot';
  if (isFetching && data) return 'Updating evidence';
  if (isFetching) return 'Loading evidence';
  if (error) return 'Endpoint fallback';
  if (data?.summary.error || data?.recommendations.error) return 'Partial endpoint evidence';
  return 'Focused endpoints';
}

function endpointTone(data: OverviewEndpointBundle | undefined, error: Error | null, enabled: boolean): 'positive' | 'caution' | 'neutral' {
  if (!enabled) return 'neutral';
  return error && !data || data?.summary.error || data?.recommendations.error ? 'caution' : 'positive';
}
