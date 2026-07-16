import { useInfiniteQuery } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, ContextRuntime, DashboardModel, ThreadRow } from '../../api/types';
import { threadCallsInfiniteQueryOptions, threadsInfiniteQueryOptions } from '../../data/exploreQueries';
import { exploreWorkspaceUrl, type ExploreWorkspaceId } from '../explore/ExploreWorkspaceSwitcher';
import { useEvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { callCsvColumns, threadColumns } from '../shared/tables';
import {
  buildThreadsFilterSummary,
  normalizeThreadRiskFilter,
  type ThreadRiskFilter,
} from './threadFilterSummary';
import {
  buildThreadsViewLink,
  defaultThreadCallSortDirection,
  detailFirstSelectedThreadName,
  filterThreads,
  normalizeThreadCallSort,
  readInitialSelectedThreadParam,
  readThreadCallSortDirectionParam,
  readThreadCallSortParam,
  readThreadPageVisibleRowsParam,
  readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  sortThreads,
  threadsTablePageSize,
  type ThreadCallSortDirection,
  type ThreadCallSortKey,
} from './threadsUrlState';
import { threadSummaryToRow, type ExploreThreadRow } from './threadSummaryAdapter';
import { threadsEndpointState } from './threadsEndpointState';
import { buildCacheFrontierSpec, buildThreadLifecycleSpec } from './threadVisualizations';
import { compareCallTimeDescending, sortThreadCalls, threadLabelsMatch } from './threadAnalysis';
import { dedupeThreadCallPages, shouldFetchNextThreadCallPage } from './threadCallLoading';
import { ThreadsExplorerView, type ThreadEvidenceViewMode } from './ThreadsExplorerView';

type ThreadsPageProps = {
  model: DashboardModel;
  globalQuery: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  globalFilters?: ReactNode;
  contextRuntime: ContextRuntime;
  includeArchived?: boolean;
  sourceKey?: string;
  sourceRevision?: string;
  focusedEndpointsEnabled?: boolean;
  onNavigateView: (view: 'calls' | 'threads') => void;
};

export function threadsForCurrentUrl(threads: ThreadRow[], globalQuery = ''): ThreadRow[] {
  return sortThreads(
    filterThreads(threads, {
      globalQuery,
      localQuery: readThreadSearchParam('thread_q'),
      riskFilter: readThreadRiskParam(),
    }),
    readThreadSortingParam(),
  );
}

export function threadCallsForCurrentUrl(model: DashboardModel, globalQuery = ''): CallRow[] {
  return callsForThreadRows(model.calls, threadsForCurrentUrl(model.threads, globalQuery));
}

function callsForThreadRows(calls: CallRow[], threads: ThreadRow[]): CallRow[] {
  const threadOrder = new Map(threads.map((thread, index) => [thread.name, index]));
  const latestCallOrder = new Map(
    threads
      .filter(thread => thread.latestCallId)
      .map((thread, index) => [thread.latestCallId, index] as const),
  );
  const callOrder = new Map(calls.map((call, index) => [call.id, index]));
  return calls
    .filter(call => threadOrder.has(call.thread) || latestCallOrder.has(call.id))
    .sort(
      (left, right) =>
        (threadOrder.get(left.thread) ?? latestCallOrder.get(left.id) ?? 0) -
          (threadOrder.get(right.thread) ?? latestCallOrder.get(right.id) ?? 0) ||
        (callOrder.get(left.id) ?? 0) - (callOrder.get(right.id) ?? 0),
    );
}

export function ThreadsPage({
  model,
  globalQuery,
  onOpenInvestigator,
  onCopyCallLink,
  globalFilters,
  contextRuntime,
  includeArchived = false,
  sourceKey,
  sourceRevision = '',
  focusedEndpointsEnabled = import.meta.env.MODE !== 'test',
  onNavigateView,
}: ThreadsPageProps) {
  const shellI18n = useShellI18n();
  const [localQuery, setLocalQuery] = useState(() => readThreadSearchParam('thread_q'));
const [riskFilter, setRiskFilter] = useState<ThreadRiskFilter>(() => readThreadRiskParam());
  const [selectedThreadName, setSelectedThreadName] = useState<string | null>(() => readInitialSelectedThreadParam());
  const [threadSorting, setThreadSorting] = useState<SortingState>(() => readThreadSortingParam());
  const [visibleThreadRows, setVisibleThreadRows] = useState(() => readThreadPageVisibleRowsParam(threadsTablePageSize));
  const initialThreadCallSort = readThreadCallSortParam();
  const [threadCallSort, setThreadCallSort] = useState<ThreadCallSortKey>(() => initialThreadCallSort);
  const [threadCallSortDirection, setThreadCallSortDirection] = useState<ThreadCallSortDirection>(() =>
    readThreadCallSortDirectionParam(initialThreadCallSort),
  );
  const [exportStatus, setExportStatus] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [viewMode, setViewMode] = useState<ThreadEvidenceViewMode>('table');
  const gridPreferences = useEvidenceGridPreferences('codexUsageThreadsEvidenceGrid', {
    density: 'compact',
    columnVisibility: {},
  });
  const previousGlobalQueryRef = useRef(globalQuery);

  const endpointState = useMemo(
    () => threadsEndpointState({
      runtime: contextRuntime,
      enabled: focusedEndpointsEnabled,
      globalQuery,
      localQuery,
      riskFilter,
      sorting: threadSorting,
    }),
    [contextRuntime, focusedEndpointsEnabled, globalQuery, localQuery, riskFilter, threadSorting],
  );
  const focusedThreadsQuery = useInfiniteQuery({
    ...threadsInfiniteQueryOptions({
      runtime: contextRuntime,
      includeArchived,
      sourceKey,
      sourceRevision,
      query: endpointState.query,
      sort: endpointState.sort,
      direction: endpointState.direction,
      pageSize: threadsTablePageSize,
    }),
    enabled: endpointState.enabled,
    placeholderData: previous => previous,
  });
  const loadedThreadsByName = useMemo(() => new Map(model.threads.map(thread => [thread.name, thread])), [model.threads]);
  const focusedThreads = useMemo(
    () => focusedThreadsQuery.data?.pages.flatMap(page => page.rows.map(summary =>
      threadSummaryToRow(summary, loadedThreadsByName.get(summary.threadLabel) ?? loadedThreadsByName.get(summary.threadKey)),
    )) ?? [],
    [focusedThreadsQuery.data, loadedThreadsByName],
  );
  const usingFocusedThreads = endpointState.enabled && Boolean(focusedThreadsQuery.data);
  const sourceThreads = usingFocusedThreads ? focusedThreads : model.threads;
  const filteredThreads = useMemo(() => filterThreads(sourceThreads, { localQuery, globalQuery, riskFilter }), [
    globalQuery,
    localQuery,
    riskFilter,
    sourceThreads,
  ]);
  const sortedThreads = useMemo(() => sortThreads(filteredThreads, threadSorting), [filteredThreads, threadSorting]);
  const totalMatchedThreads = usingFocusedThreads
    ? focusedThreadsQuery.data?.pages[0]?.totalMatchedRows ?? sortedThreads.length
    : model.threads.length;
  const tableSubtitle = useMemo(
    () =>
      buildThreadsFilterSummary({
        shownCount: filteredThreads.length,
        totalCount: totalMatchedThreads,
        localQuery,
        globalQuery,
        riskFilter,
        selectedThreadName,
      }),
    [globalQuery, localQuery, riskFilter, selectedThreadName, sortedThreads.length, totalMatchedThreads],
  );
  const threadLeaderboardTitle = shellI18n.t('dashboard.top_threads_by_attention', 'Thread Leaderboard');
  const threadLeaderboardTableLabel = shellI18n.t('dashboard.top_threads_by_attention', 'Thread leaderboard');
  const selected =
    selectedThreadName === detailFirstSelectedThreadName
      ? sortedThreads[0] ?? null
      : sortedThreads.find(thread => thread.name === selectedThreadName) ?? null;
  const selectedThreadNameForUrl =
    selectedThreadName === detailFirstSelectedThreadName ? (selected?.name ?? null) : selectedThreadName;
  const localSelectedCalls = useMemo(() => {
    if (!selected) return [];
    return sortThreadCalls(
      model.calls.filter(call => threadLabelsMatch(call.thread, selected.name)),
      threadCallSort,
      threadCallSortDirection,
    );
  }, [model.calls, selected, threadCallSort, threadCallSortDirection]);
  const selectedThreadKey = (selected as ExploreThreadRow | null)?.threadKey || localSelectedCalls[0]?.threadKey || selected?.name || '';
  const selectedThreadQueryEnabled = focusedEndpointsEnabled
    && !contextRuntime.fileMode
    && Boolean(contextRuntime.apiToken)
    && Boolean(selectedThreadKey);
  const selectedThreadCallsQuery = useInfiniteQuery({
    ...threadCallsInfiniteQueryOptions({
      runtime: contextRuntime,
      includeArchived,
      sourceKey,
      sourceRevision,
      threadKey: selectedThreadKey,
      sort: threadCallSort === 'newest' ? 'time' : threadCallSort,
      direction: threadCallSortDirection,
    }),
    enabled: selectedThreadQueryEnabled,
  });
  const focusedCallPages = selectedThreadCallsQuery.data?.pages ?? [];
  const selectedCalls = useMemo(
    () => dedupeThreadCallPages(focusedCallPages, localSelectedCalls),
    [focusedCallPages, localSelectedCalls],
  );
  const selectedCallCount = selectedThreadCallsQuery.data?.pages[0]?.totalMatchedRows ?? selectedCalls.length;
  const threadTableColumns = threadColumns;
  const frontierSpec = useMemo(
    () => buildCacheFrontierSpec(sortedThreads, includeArchived ? 'all' : 'active', sourceRevision),
    [includeArchived, sortedThreads, sourceRevision],
  );
  const lifecycleThread = selected ?? sortedThreads[0] ?? null;
  const lifecycleCalls = selected ? selectedCalls : lifecycleThread
    ? model.calls.filter(call => threadLabelsMatch(call.thread, lifecycleThread.name)).sort(compareCallTimeDescending)
    : [];
  const lifecycleSpec = useMemo(
    () => buildThreadLifecycleSpec(lifecycleCalls, lifecycleThread?.name ?? '', includeArchived ? 'all' : 'active', sourceRevision),
    [includeArchived, lifecycleCalls, lifecycleThread?.name, sourceRevision],
  );

  useEffect(() => {
    if (previousGlobalQueryRef.current === globalQuery) return;
    previousGlobalQueryRef.current = globalQuery;
    setVisibleThreadRows(threadsTablePageSize);
  }, [globalQuery]);

  useEffect(() => {
    if (selectedThreadName === detailFirstSelectedThreadName && selectedThreadNameForUrl) {
      setSelectedThreadName(selectedThreadNameForUrl);
    }
  }, [selectedThreadName, selectedThreadNameForUrl]);

  useEffect(() => {
    const url = buildThreadsViewLink({
      localQuery,
      riskFilter,
      selectedThreadName: selectedThreadNameForUrl,
      sorting: threadSorting,
      visibleRowCount: visibleThreadRows,
threadCallSort,
threadCallSortDirection,
});
    if (url.toString() !== window.location.href) {
      window.history.replaceState(null, '', url);
    }
}, [localQuery, riskFilter, selectedThreadNameForUrl, threadCallSort, threadCallSortDirection, threadSorting, visibleThreadRows]);

  function exportThreads() {
    const exportRows = callsForThreadRows(model.calls, sortThreads(filteredThreads, threadSorting));
    downloadCsv(`codex-thread-filtered-calls-${csvDateStamp()}.csv`, rowsToCsv(exportRows, callCsvColumns));
    setExportStatus(`Exported ${exportRows.length} calls`);
  }

  function resetThreadTablePage() {
    setVisibleThreadRows(threadsTablePageSize);
  }

  function updateLocalQuery(value: string) {
    setLocalQuery(value);
    resetThreadTablePage();
  }

  function updateRiskFilter(value: string) {
    setRiskFilter(normalizeThreadRiskFilter(value));
    resetThreadTablePage();
  }

  function updateThreadSorting(updater: SortingState | ((old: SortingState) => SortingState)) {
    setThreadSorting(current => (typeof updater === 'function' ? updater(current) : updater));
    resetThreadTablePage();
  }

  function clearThreadFilters() {
    setLocalQuery('');
    setRiskFilter('all');
setSelectedThreadName(null);
setVisibleThreadRows(threadsTablePageSize);
setThreadCallSort('newest');
setThreadCallSortDirection(defaultThreadCallSortDirection('newest'));
    const url = buildThreadsViewLink({
      localQuery: '',
      riskFilter: 'all',
      selectedThreadName: null,
      sorting: threadSorting,
      visibleRowCount: threadsTablePageSize,
threadCallSort: 'newest',
threadCallSortDirection: defaultThreadCallSortDirection('newest'),
});
    window.history.replaceState(null, '', url);
    setFilterStatus('Thread filters cleared');
  }

  function toggleThread(threadName: string) {
    setSelectedThreadName(current => current === threadName ? null : threadName);
  }

function updateThreadCallSort(value: string) {
const nextSort = normalizeThreadCallSort(value);
setThreadCallSort(nextSort);
setThreadCallSortDirection(defaultThreadCallSortDirection(nextSort));
}

function updateThreadCallSortDirection(value: string) {
setThreadCallSortDirection(value === 'asc' ? 'asc' : 'desc');
}

  function selectExploreWorkspace(workspace: ExploreWorkspaceId) {
    if (workspace === 'threads') return;
    window.history.replaceState(null, '', exploreWorkspaceUrl(workspace));
    onNavigateView('calls');
  }

  const displayedThreads = usingFocusedThreads ? sortedThreads : sortedThreads.slice(0, visibleThreadRows);
  const canLoadMoreThreads = usingFocusedThreads
    ? Boolean(focusedThreadsQuery.hasNextPage)
    : displayedThreads.length < sortedThreads.length;

  useEffect(() => {
    if (endpointState.enabled && !focusedThreadsQuery.data) return;
    if (selectedThreadName && selectedThreadName !== detailFirstSelectedThreadName
      && !displayedThreads.some(thread => thread.name === selectedThreadName)) {
      setSelectedThreadName(null);
    }
  }, [displayedThreads, endpointState.enabled, focusedThreadsQuery.data, selectedThreadName]);

  useEffect(() => {
    if (!shouldFetchNextThreadCallPage({
      expanded: Boolean(selected),
      enabled: selectedThreadQueryEnabled,
      hasNextPage: Boolean(selectedThreadCallsQuery.hasNextPage),
      isFetchingNextPage: selectedThreadCallsQuery.isFetchingNextPage,
      isFetchNextPageError: selectedThreadCallsQuery.isFetchNextPageError,
    })) return;
    void selectedThreadCallsQuery.fetchNextPage();
  }, [
    selected,
    selectedThreadCallsQuery.data,
    selectedThreadCallsQuery.hasNextPage,
    selectedThreadQueryEnabled,
    selectedThreadCallsQuery.isFetchNextPageError,
    selectedThreadCallsQuery.isFetchingNextPage,
  ]);

  function loadMoreThreads() {
    if (usingFocusedThreads && focusedThreadsQuery.hasNextPage) {
      void focusedThreadsQuery.fetchNextPage();
      return;
    }
    setVisibleThreadRows(current => Math.min(current + threadsTablePageSize, sortedThreads.length));
  }

  function retrySelectedThreadCalls() {
    if (!selectedThreadCallsQuery.hasNextPage) return;
    void selectedThreadCallsQuery.fetchNextPage();
  }

  return (
    <ThreadsExplorerView
      globalFilters={globalFilters}
      localQuery={localQuery}
      riskFilter={riskFilter}
      exportDisabled={!filteredThreads.length}
      exportStatus={exportStatus}
      filterStatus={filterStatus}
      tableSubtitle={tableSubtitle}
      tableTitle={threadLeaderboardTitle}
      tableLabel={threadLeaderboardTableLabel}
      viewMode={viewMode}
      focusedState={{
        isFetching: focusedThreadsQuery.isFetching,
        isFetchingNextPage: focusedThreadsQuery.isFetchingNextPage,
        usingFocused: usingFocusedThreads,
        fallbackReason: endpointState.reason,
        error: focusedThreadsQuery.error ? queryErrorMessage(focusedThreadsQuery.error) : null,
      }}
      selectedCallsState={{
        isFetching: selectedThreadCallsQuery.isFetching,
        isFetchingNextPage: selectedThreadCallsQuery.isFetchingNextPage,
        isFetchNextPageError: selectedThreadCallsQuery.isFetchNextPageError,
        count: selectedCallCount,
        hydrated: Boolean(selectedThreadCallsQuery.data),
        error: selectedThreadCallsQuery.error ? queryErrorMessage(selectedThreadCallsQuery.error) : null,
      }}
      selectedCalls={selectedCalls}
      displayedThreads={displayedThreads}
      totalMatchedThreads={totalMatchedThreads}
      canLoadMoreThreads={canLoadMoreThreads}
      columns={threadTableColumns}
      sorting={threadSorting}
      gridPreferences={gridPreferences}
      selected={selected}
      frontierSpec={frontierSpec}
      lifecycleSpec={lifecycleSpec}
      callSort={threadCallSort}
      callSortDirection={threadCallSortDirection}
      onWorkspaceChange={selectExploreWorkspace}
      onExport={exportThreads}
      onClearFilters={clearThreadFilters}
      onLocalQueryChange={updateLocalQuery}
      onRiskFilterChange={updateRiskFilter}
      onViewModeChange={setViewMode}
      onSortingChange={updateThreadSorting}
      onToggleThread={toggleThread}
      onRetryCalls={retrySelectedThreadCalls}
      onLoadMoreThreads={loadMoreThreads}
      onCallSortChange={updateThreadCallSort}
      onCallSortDirectionChange={updateThreadCallSortDirection}
      onOpenInvestigator={onOpenInvestigator}
      onCopyCallLink={onCopyCallLink}
    />
  );
}

function queryErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
