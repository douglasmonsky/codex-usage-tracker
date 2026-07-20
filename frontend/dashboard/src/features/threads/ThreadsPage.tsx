import { useInfiniteQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, ContextRuntime, DashboardModel, ThreadRow } from '../../api/types';
import { threadCallsInfiniteQueryOptions, threadsInfiniteQueryOptions } from '../../data/exploreQueries';
import { exploreWorkspaceUrl, type ExploreWorkspaceId } from '../explore/ExploreWorkspaceSwitcher';
import { useEvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { callCsvColumns, threadColumns } from '../shared/tables';
import { buildThreadsFilterSummary } from './threadFilterSummary';
import {
  buildThreadsViewLink,
  detailFirstSelectedThreadName,
  filterThreads,
  readInitialThreadSelector,
  readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  sortThreads,
  threadRowSelector,
  threadRowIdentity,
  threadSelectorIdentity,
  threadsTablePageSize,
  type ThreadSelector,
} from './threadsUrlState';
import { threadSummaryToRow } from './threadSummaryAdapter';
import { threadsEndpointState } from './threadsEndpointState';
import { buildCacheFrontierSpec, buildThreadLifecycleSpec } from './threadVisualizations';
import { compareCallTimeDescending, sortThreadCalls } from './threadAnalysis';
import { dedupeThreadCallPages } from './threadCallLoading';
import { ThreadsExplorerView } from './ThreadsExplorerView';
import { useThreadsPageControls } from './useThreadsPageControls';

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

const threadCallsPageSize = 100;
const threadDefaultColumnVisibility = {
  totalDuration: false,
  averageGap: false,
  initiatorSummary: false,
  modelSummary: false,
  effortSummary: false,
  cachedInput: false,
  uncachedInput: false,
  outputTokens: false,
  reasoningOutput: false,
  costPerCall: false,
  productivity: false,
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
  const threadOrder = new Map(threads.map((thread, index) => [threadSelectorIdentity(threadRowSelector(thread)), index]));
  const latestCallOrder = new Map(
    threads
      .filter(thread => thread.latestCallId)
      .map((thread, index) => [thread.latestCallId, index] as const),
  );
  const callOrder = new Map(calls.map((call, index) => [call.id, index]));
  return calls
    .filter(call => threadOrder.has(callIdentity(call)) || latestCallOrder.has(call.id))
    .sort(
      (left, right) =>
        (threadOrder.get(callIdentity(left)) ?? latestCallOrder.get(left.id) ?? 0) -
          (threadOrder.get(callIdentity(right)) ?? latestCallOrder.get(right.id) ?? 0) ||
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
  const {
    localQuery, riskFilter, selectedThreadName, threadSorting, visibleThreadRows,
    threadCallSort, threadCallSortDirection, exportStatus, filterStatus, viewMode,
    setSelectedThreadName, setVisibleThreadRows, setExportStatus, setViewMode,
    updateLocalQuery, updateRiskFilter, updateThreadSorting, clearThreadFilters,
    updateThreadCallSort, updateThreadCallSortDirection,
  } = useThreadsPageControls(globalQuery);
  const selectedThreadKind = useRef<ThreadSelector['kind']>(
    readInitialThreadSelector()?.kind ?? 'name',
  );
  const gridPreferences = useEvidenceGridPreferences('codexUsageThreadsEvidenceGridV2', {
    density: 'compact',
    columnVisibility: threadDefaultColumnVisibility,
  });

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
  const loadedThreadsByIdentity = useMemo(() => new Map(model.threads.flatMap(thread => [
    [threadSelectorIdentity(threadRowSelector(thread)), thread] as const,
    [`name:${thread.name}`, thread] as const,
  ])), [model.threads]);
  const focusedThreads = useMemo(
    () => focusedThreadsQuery.data?.pages.flatMap(page => page.rows.map(summary =>
      threadSummaryToRow(
        summary,
        loadedThreadsByIdentity.get(`key:${summary.threadKey}`)
          ?? loadedThreadsByIdentity.get(`name:${summary.threadLabel}`),
      ),
    )) ?? [],
    [focusedThreadsQuery.data, loadedThreadsByIdentity],
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
  const selected =
    selectedThreadName === detailFirstSelectedThreadName
      ? sortedThreads[0] ?? null
      : resolveSelectedThread(
        sortedThreads,
        selectedThreadName ? { kind: selectedThreadKind.current, value: selectedThreadName } : null,
      );
  const tableSubtitle = useMemo(
    () =>
      buildThreadsFilterSummary({
        shownCount: filteredThreads.length,
        totalCount: totalMatchedThreads,
        localQuery,
        globalQuery,
        riskFilter,
        selectedThreadName: selected?.name ?? selectedThreadName,
      }),
    [globalQuery, localQuery, riskFilter, selected, selectedThreadName, sortedThreads.length, totalMatchedThreads],
  );
  const threadLeaderboardTitle = shellI18n.t('dashboard.top_threads_by_attention', 'Thread Leaderboard');
  const threadLeaderboardTableLabel = shellI18n.t('dashboard.top_threads_by_attention', 'Thread leaderboard');
  const selectedThreadNameForUrl = selected?.name
    ?? (selectedThreadName === detailFirstSelectedThreadName ? null : selectedThreadName);
  const localSelectedCalls = useMemo(() => {
    if (!selected) return [];
    return sortThreadCalls(
      callsForThreadRow(model.calls, selected),
      threadCallSort,
      threadCallSortDirection,
    );
  }, [model.calls, selected, threadCallSort, threadCallSortDirection]);
  const selectedThreadKey = selected?.threadKey || localSelectedCalls[0]?.threadKey || '';
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
      pageSize: threadCallsPageSize,
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
  const frontierSpec = useMemo(() => {
    const spec = buildCacheFrontierSpec(sortedThreads, includeArchived ? 'all' : 'active', sourceRevision);
    return {
      ...spec,
      data: {
        ...spec.data,
        rows: spec.data.rows.map((row, index) => ({
          ...row,
          id: sortedThreads[index] ? threadRowIdentity(sortedThreads[index]) : row.id,
        })),
      },
    };
  }, [includeArchived, sortedThreads, sourceRevision]);
  const lifecycleThread = selected ?? sortedThreads[0] ?? null;
  const lifecycleCalls = selected ? selectedCalls : lifecycleThread
    ? callsForThreadRow(model.calls, lifecycleThread).sort(compareCallTimeDescending)
    : [];
  const lifecycleSpec = useMemo(
    () => buildThreadLifecycleSpec(lifecycleCalls, lifecycleThread?.name ?? '', includeArchived ? 'all' : 'active', sourceRevision),
    [includeArchived, lifecycleCalls, lifecycleThread?.name, sourceRevision],
  );

  useEffect(() => {
    if (!selected) return;
    const canonical = canonicalThreadSelector(selected);
    if (selectedThreadKind.current === canonical.kind && selectedThreadName === canonical.value) return;
    selectedThreadKind.current = canonical.kind;
    setSelectedThreadName(canonical.value);
  }, [selected, selectedThreadName, setSelectedThreadName]);

  useEffect(() => {
    const url = buildThreadsViewLink({
      localQuery,
      riskFilter,
      selectedThreadName: selectedThreadNameForUrl,
      selectedThreadKey: selectedThreadKey || null,
      sorting: threadSorting,
      visibleRowCount: visibleThreadRows,
threadCallSort,
threadCallSortDirection,
});
    if (url.toString() !== window.location.href) {
      window.history.replaceState(null, '', url);
    }
}, [localQuery, riskFilter, selectedThreadKey, selectedThreadNameForUrl, threadCallSort, threadCallSortDirection, threadSorting, visibleThreadRows]);

  function exportThreads() {
    const exportRows = callsForThreadRows(model.calls, sortThreads(filteredThreads, threadSorting));
    downloadCsv(`codex-thread-filtered-calls-${csvDateStamp()}.csv`, rowsToCsv(exportRows, callCsvColumns));
    setExportStatus(`Exported ${exportRows.length} calls`);
  }

  function selectExploreWorkspace(workspace: ExploreWorkspaceId) {
    if (workspace === 'threads') return;
    window.history.replaceState(null, '', buildThreadsDepartureUrl(workspace));
    onNavigateView('calls');
  }

  const displayedThreads = usingFocusedThreads ? sortedThreads : sortedThreads.slice(0, visibleThreadRows);
  const canLoadMoreThreads = usingFocusedThreads
    ? Boolean(focusedThreadsQuery.hasNextPage)
    : displayedThreads.length < sortedThreads.length;

  useEffect(() => {
    if (!endpointState.enabled
      || !focusedThreadsQuery.data
      || !selectedThreadName
      || selectedThreadName === detailFirstSelectedThreadName
      || selected
      || !focusedThreadsQuery.hasNextPage
      || focusedThreadsQuery.isFetchingNextPage
      || focusedThreadsQuery.isFetchNextPageError) return;
    void focusedThreadsQuery.fetchNextPage();
  }, [
    endpointState.enabled,
    focusedThreadsQuery.data,
    focusedThreadsQuery.hasNextPage,
    focusedThreadsQuery.isFetchNextPageError,
    focusedThreadsQuery.isFetchingNextPage,
    selected,
    selectedThreadName,
  ]);

  useEffect(() => {
    if (endpointState.enabled && (
      !focusedThreadsQuery.data
      || focusedThreadsQuery.isFetching
      || focusedThreadsQuery.isFetchingNextPage
      || focusedThreadsQuery.hasNextPage
    )) return;
    if (selectedThreadName && selectedThreadName !== detailFirstSelectedThreadName
      && !selected) {
      setSelectedThreadName(null);
    }
  }, [
    displayedThreads,
    endpointState.enabled,
    focusedThreadsQuery.data,
    focusedThreadsQuery.hasNextPage,
    focusedThreadsQuery.isFetching,
    focusedThreadsQuery.isFetchingNextPage,
    selectedThreadName,
    selected,
  ]);

  function toggleSelectedThread(selector: ThreadSelector) {
    const nextSelection = nextThreadSelection(selected, selector);
    if (!nextSelection) {
      setSelectedThreadName(null);
      return;
    }
    selectedThreadKind.current = nextSelection.kind;
    setSelectedThreadName(nextSelection.value);
  }

  function loadMoreThreads() {
    if (usingFocusedThreads && focusedThreadsQuery.hasNextPage) {
      void focusedThreadsQuery.fetchNextPage();
      return;
    }
    setVisibleThreadRows(current => Math.min(current + threadsTablePageSize, sortedThreads.length));
  }

  function retrySelectedThreadCalls() {
    if (selectedThreadCallsQuery.isFetchNextPageError) {
      void selectedThreadCallsQuery.fetchNextPage();
      return;
    }
    void selectedThreadCallsQuery.refetch();
  }

  function loadMoreSelectedThreadCalls() {
    if (!selectedThreadCallsQuery.hasNextPage || selectedThreadCallsQuery.isFetchingNextPage) return;
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
        canLoadMore: Boolean(selectedThreadCallsQuery.hasNextPage),
        count: selectedCallCount,
        hydrated: Boolean(selectedThreadCallsQuery.data),
        error: selectedThreadCallsQuery.error ? queryErrorMessage(selectedThreadCallsQuery.error) : null,
        initialError: selectedThreadCallsQuery.isError && !selectedThreadCallsQuery.data
          ? queryErrorMessage(selectedThreadCallsQuery.error)
          : null,
        storedSnapshot: Boolean(selectedCalls.length && !selectedThreadCallsQuery.data),
      }}
      selectedCalls={selectedCalls}
      callPageSize={threadCallsPageSize}
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
      onToggleThread={toggleSelectedThread}
      onRetryCalls={retrySelectedThreadCalls}
      onLoadMoreCalls={loadMoreSelectedThreadCalls}
      onLoadMoreThreads={loadMoreThreads}
      onCallSortChange={updateThreadCallSort}
      onCallSortDirectionChange={updateThreadCallSortDirection}
      onOpenInvestigator={onOpenInvestigator}
      onCopyCallLink={onCopyCallLink}
    />
  );
}

export function resolveSelectedThread(threads: ThreadRow[], selector: ThreadSelector | null): ThreadRow | null {
  if (!selector) return null;
  return selector.kind === 'key'
    ? threads.find(thread => thread.threadKey === selector.value) ?? null
    : threads.find(thread => thread.name === selector.value) ?? null;
}

export function canonicalThreadSelector(thread: ThreadRow): ThreadSelector {
  return threadRowSelector(thread);
}

export function callsForThreadRow(calls: CallRow[], thread: ThreadRow): CallRow[] {
  const identity = threadSelectorIdentity(threadRowSelector(thread));
  return calls.filter(call => callIdentity(call) === identity);
}

export function nextThreadSelection(
  selected: ThreadRow | null,
  activated: ThreadSelector,
): ThreadSelector | null {
  return selected
    && threadSelectorIdentity(threadRowSelector(selected)) === threadSelectorIdentity(activated)
    ? null
    : activated;
}

function callIdentity(call: CallRow): string {
  return threadSelectorIdentity(call.threadKey
    ? { kind: 'key', value: call.threadKey }
    : { kind: 'name', value: call.thread });
}

export function buildThreadsDepartureUrl(
  workspace: Exclude<ExploreWorkspaceId, 'threads'>,
  href = window.location.href,
): URL {
  const url = exploreWorkspaceUrl(workspace, href);
  url.searchParams.delete('thread_key');
  url.searchParams.delete('thread');
  return url;
}

function queryErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
