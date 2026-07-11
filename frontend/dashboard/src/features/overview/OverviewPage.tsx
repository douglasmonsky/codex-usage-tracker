import { useQuery } from '@tanstack/react-query';
import { ArrowRight, RefreshCw } from 'lucide-react';
import { useMemo, type ReactNode } from 'react';

import type { ContextRuntime, DashboardModel } from '../../api/types';
import { Button, StatusBadge } from '../../design';
import { overviewQueryOptions, type OverviewEndpointBundle } from '../../data/overviewQueries';
import { Visualization } from '../../visualization';
import { OverviewFindingRail } from './OverviewFindingRail';
import { OverviewMetrics } from './OverviewMetrics';
import styles from './OverviewPage.module.css';
import { OverviewRecentCalls } from './OverviewRecentCalls';
import { buildOverviewViewModel, type OverviewFindingView } from './overviewModel';
import type { OverviewNavigationTarget } from './overviewNavigation';

export { overviewCallsForQuery } from './overviewCalls';

type OverviewRuntime = {
  historyScope: 'active' | 'all';
  loadLimit: number;
  loadedRowCount: number;
  totalAvailableRows: number;
};

type OverviewPageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  sourceRevision: string;
  onRefresh: () => void;
  refreshState: string;
  globalQuery: string;
  runtime: OverviewRuntime;
  refreshing: boolean;
  canLoadMoreRows: boolean;
  canLoadAllRows: boolean;
  onLoadMoreRows: () => void;
  onLoadAllRows: () => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onOpenFinding: (rank: number) => void;
  onNavigateView: (view: OverviewNavigationTarget) => void;
  focusedEndpointsEnabled?: boolean;
  globalFilters?: ReactNode;
};

export function OverviewPage(props: OverviewPageProps) {
  const focusedEndpointsEnabled = props.focusedEndpointsEnabled ?? import.meta.env.MODE !== 'test';
  const canUseFocusedEndpoints = focusedEndpointsEnabled && !props.contextRuntime.fileMode && Boolean(props.contextRuntime.apiToken);
  const since = earliestLoadedDate(props.model);
  const focusedQuery = useQuery({
    ...overviewQueryOptions({
      runtime: props.contextRuntime,
      includeArchived: props.runtime.historyScope === 'all',
      since,
      sourceRevision: props.sourceRevision,
    }),
    enabled: canUseFocusedEndpoints,
    placeholderData: previous => previous,
  });
  const viewModel = useMemo(
    () => buildOverviewViewModel(props.model, focusedQuery.data, props.runtime.historyScope),
    [focusedQuery.data, props.model, props.runtime.historyScope],
  );
  const topFinding = viewModel.findings[0];

  function openFinding(finding: OverviewFindingView) {
    if (finding.recordId) props.onOpenInvestigator(finding.recordId);
    else if (finding.legacyRank) props.onOpenFinding(finding.legacyRank);
    else props.onNavigateView('investigator');
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Usage pulse</p><h1>Overview</h1><p>The important changes first, with direct paths into supporting evidence.</p></div>
        <div className={styles.headerActions}>
          <StatusBadge tone={endpointTone(focusedQuery.data, focusedQuery.error, canUseFocusedEndpoints)}>{endpointLabel(focusedQuery.isFetching, focusedQuery.data, focusedQuery.error, canUseFocusedEndpoints)}</StatusBadge>
          <Button variant="primary" onClick={props.onRefresh} disabled={props.refreshing}><RefreshCw /> {props.refreshing ? 'Refreshing...' : 'Refresh data'}</Button>
        </div>
      </header>

      <section className={styles.answerBand} data-tone={viewModel.answer.tone} aria-labelledby="overview-answer-title">
        <div>
          <p className={styles.answerLabel}>Highest-priority answer</p>
          <h2 id="overview-answer-title">{viewModel.answer.title}</h2>
          <p>{viewModel.answer.detail}</p>
          <strong className={styles.nextAction}>Next action: {viewModel.answer.action}</strong>
        </div>
        <div className={styles.answerActions}>
          <span><strong>{topFinding?.evidenceGrade ?? 'Baseline'}</strong><small>{topFinding ? supportingCallsLabel(topFinding.supportCount) : props.refreshState}</small></span>
          <Button variant="primary" onClick={() => topFinding ? openFinding(topFinding) : props.onNavigateView('investigator')}>Inspect evidence <ArrowRight /></Button>
        </div>
      </section>

      <OverviewMetrics metrics={viewModel.metrics} availableCalls={props.runtime.totalAvailableRows} />

      <div className={styles.analysisGrid}>
        <Visualization spec={viewModel.pulseSpec} height={280} />
        <OverviewFindingRail findings={viewModel.findings} onOpenFinding={openFinding} onNavigateView={props.onNavigateView} />
      </div>

      <Visualization spec={viewModel.tokenFlowSpec} height={290} />

      <OverviewRecentCalls
        calls={props.model.calls}
        globalFilters={props.globalFilters}
        globalQuery={props.globalQuery}
        loadedRowCount={props.runtime.loadedRowCount}
        totalAvailableRows={props.runtime.totalAvailableRows}
        refreshing={props.refreshing}
        canLoadMoreRows={props.canLoadMoreRows}
        canLoadAllRows={props.canLoadAllRows}
        onLoadMoreRows={props.onLoadMoreRows}
        onLoadAllRows={props.onLoadAllRows}
        onOpenCall={props.onOpenInvestigator}
        onCopyCallLink={props.onCopyCallLink}
      />
    </div>
  );
}

function earliestLoadedDate(model: DashboardModel): string | undefined {
  const timestamps = model.calls.map(call => Date.parse(call.eventTimestamp)).filter(Number.isFinite);
  if (!timestamps.length) return undefined;
  return new Date(Math.min(...timestamps)).toISOString().slice(0, 10);
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

function supportingCallsLabel(count: number): string {
  return count === 1 ? '1 supporting call' : `${count} supporting calls`;
}
