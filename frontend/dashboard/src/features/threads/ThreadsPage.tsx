import type { SortingState, VisibilityState } from '@tanstack/react-table';
import { Copy, Download, Filter, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, DashboardModel, ThreadRow } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { ColumnChooser } from '../../components/ColumnChooser';
import { DonutChart } from '../../charts/DonutChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import {
  CallSignalPucks,
  callCsvColumns,
  threadActionColumn,
  threadColumnChoices,
  threadColumns,
  threadInvestigatorRowLabel,
} from '../shared/tables';
import {
  buildThreadsFilterSummary,
  normalizeThreadRiskFilter,
  type ThreadRiskFilter,
} from './threadFilterSummary';
import {
  buildThreadsViewLink,
  detailFirstSelectedThreadName,
  filterThreads,
  normalizeThreadCallSort,
  readInitialSelectedThreadParam,
  readThreadCallPageVisibleRowsParam,
  readThreadCallSortParam,
  readThreadPageVisibleRowsParam,
  readThreadRiskParam,
  readThreadSearchParam,
  readThreadSortingParam,
  sortThreads,
  threadCallPageSize,
  threadsTablePageSize,
  type ThreadCallSortKey,
} from './threadsUrlState';

type ThreadsPageProps = {
  model: DashboardModel;
  globalQuery: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

type ThreadLifecycle = {
  firstExpensive: { call: CallRow; index: number } | null;
  largestJump: { call: CallRow; tokens: number } | null;
  cacheTrend: number | null;
  contextTrend: number | null;
  subagentBeforeSpike: boolean;
};
type ThreadRelationships = {
  parentThreadLabel: string;
  subagentCalls: number;
  autoReviewCalls: number;
  attachedCalls: number;
  spawnedThreads: number;
  spawnedChildCalls: number;
};
type ThreadStatus = {
  pricingStatus: string;
  creditStatus: string;
  cacheStatus: string;
  contextStatus: string;
  nextAction: string;
};
type ThreadImpact = {
  codexCredits: string;
  allowanceImpact: string;
  attentionScore: string;
  costPerCall: string;
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

export function ThreadsPage({ model, globalQuery, onOpenInvestigator, onCopyCallLink }: ThreadsPageProps) {
  const shellI18n = useShellI18n();
  const [localQuery, setLocalQuery] = useState(() => readThreadSearchParam('thread_q'));
const [riskFilter, setRiskFilter] = useState<ThreadRiskFilter>(() => readThreadRiskParam());
  const [selectedThreadName, setSelectedThreadName] = useState<string | null>(() => readInitialSelectedThreadParam());
  const [threadSorting, setThreadSorting] = useState<SortingState>(() => readThreadSortingParam());
  const [visibleThreadRows, setVisibleThreadRows] = useState(() => readThreadPageVisibleRowsParam(threadsTablePageSize));
  const [threadCallSort, setThreadCallSort] = useState<ThreadCallSortKey>(() => readThreadCallSortParam());
  const [visibleThreadCallCount, setVisibleThreadCallCount] = useState(() => readThreadCallPageVisibleRowsParam(threadCallPageSize));
  const [exportStatus, setExportStatus] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const searchInputRef = useRef<HTMLInputElement>(null);
  const previousGlobalQueryRef = useRef(globalQuery);

  const filteredThreads = useMemo(() => filterThreads(model.threads, { localQuery, globalQuery, riskFilter }), [
    globalQuery,
    localQuery,
    model.threads,
    riskFilter,
  ]);
  const tableSubtitle = useMemo(
    () =>
      buildThreadsFilterSummary({
        shownCount: filteredThreads.length,
        totalCount: model.threads.length,
        localQuery,
        globalQuery,
        riskFilter,
        selectedThreadName,
      }),
    [filteredThreads.length, globalQuery, localQuery, model.threads.length, riskFilter, selectedThreadName],
  );
  const threadLeaderboardTitle = shellI18n.t('dashboard.top_threads_by_attention', 'Thread Leaderboard');
  const threadLeaderboardTableLabel = shellI18n.t('dashboard.top_threads_by_attention', 'Thread leaderboard');
  const selected =
    selectedThreadName === detailFirstSelectedThreadName
      ? filteredThreads[0] ?? null
      : filteredThreads.find(thread => thread.name === selectedThreadName) ?? filteredThreads[0] ?? null;
  const selectedThreadNameForUrl =
    selectedThreadName === detailFirstSelectedThreadName ? (selected?.name ?? null) : selectedThreadName;
  const selectedCalls = useMemo(() => {
    if (!selected) return [];
    return model.calls.filter(call => threadLabelsMatch(call.thread, selected.name)).sort(compareCallTimeDescending);
  }, [model.calls, selected]);
  const previousSelectedThreadRef = useRef(selected?.name ?? '');
  const threadTableColumns = useMemo(
    () => [...threadColumns, threadActionColumn({ onOpenInvestigator, onCopyCallLink })],
    [onCopyCallLink, onOpenInvestigator],
  );

  useEffect(() => {
    const selectedName = selected?.name ?? '';
    if (previousSelectedThreadRef.current === selectedName) return;
    previousSelectedThreadRef.current = selectedName;
    setVisibleThreadCallCount(threadCallPageSize);
  }, [selected?.name]);

  useEffect(() => {
    if (previousGlobalQueryRef.current === globalQuery) return;
    previousGlobalQueryRef.current = globalQuery;
    setVisibleThreadRows(threadsTablePageSize);
    setVisibleThreadCallCount(threadCallPageSize);
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
      visibleThreadCallCount,
    });
    if (url.toString() !== window.location.href) {
      window.history.replaceState(null, '', url);
    }
  }, [localQuery, riskFilter, selectedThreadNameForUrl, threadCallSort, threadSorting, visibleThreadCallCount, visibleThreadRows]);

  function exportThreads() {
    const exportRows = callsForThreadRows(model.calls, sortThreads(filteredThreads, threadSorting));
    downloadCsv(`codex-thread-filtered-calls-${csvDateStamp()}.csv`, rowsToCsv(exportRows, callCsvColumns));
    setExportStatus(`Exported ${exportRows.length} calls`);
  }

  function focusFilters() {
    searchInputRef.current?.focus();
    setFilterStatus(`Filters ready for ${filteredThreads.length} grouped threads`);
  }

  function resetThreadTablePage() {
    setVisibleThreadRows(threadsTablePageSize);
    setVisibleThreadCallCount(threadCallPageSize);
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
    setVisibleThreadCallCount(threadCallPageSize);
    const url = buildThreadsViewLink({
      localQuery: '',
      riskFilter: 'all',
      selectedThreadName: null,
      sorting: threadSorting,
      visibleRowCount: threadsTablePageSize,
      threadCallSort: 'newest',
      visibleThreadCallCount: threadCallPageSize,
    });
    window.history.replaceState(null, '', url);
    setFilterStatus('Thread filters cleared');
  }

  function selectThread(threadName: string) {
    setSelectedThreadName(threadName);
    setVisibleThreadCallCount(threadCallPageSize);
  }

  function updateThreadCallSort(value: string) {
    setThreadCallSort(normalizeThreadCallSort(value));
    setVisibleThreadCallCount(threadCallPageSize);
  }

  function openThreadInvestigator(thread: ThreadRow) {
    if (thread.latestCallId) {
      onOpenInvestigator(thread.latestCallId);
    }
  }

  return (
    <div className="thread-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Thread Efficiency</h1>
          <p>Threads as units of work, with cost concentration and handoff signals.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={exportThreads} disabled={!filteredThreads.length}>
            <Download size={16} />
            Export calls
          </button>
<button className="toolbar-button" type="button" onClick={focusFilters}>
<Filter size={16} />
Filters
</button>
<button className="toolbar-button" type="button" aria-label="Clear thread filters" onClick={clearThreadFilters}>
<X size={16} />
Clear filters
</button>
<ColumnChooser
            label="Threads"
            columns={threadColumnChoices}
            open={columnsOpen}
            onOpenChange={setColumnsOpen}
            visibility={columnVisibility}
            onVisibilityChange={setColumnVisibility}
          />
        </div>
      </div>
      <div className="filter-row span-all">
        <label className="search-box">
          <span className="sr-only">Search threads</span>
<input ref={searchInputRef} value={localQuery} onChange={event => updateLocalQuery(event.target.value)} placeholder="Search threads, risks, token totals..." />
        </label>
        <label className="filter-field">
          <span>Cold risk</span>
<select value={riskFilter} onChange={event => updateRiskFilter(event.target.value)}>
            <option value="all">All risks</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </label>
      </div>
      <Panel title="Cost vs Turns" subtitle="Sorted by estimated cost">
        <BarChart
          data={filteredThreads.map(thread => ({
            label: thread.name,
            value: thread.cost,
            color: thread.cachePct < 20 ? '#ef4444' : thread.cachePct < 45 ? '#f59e0b' : '#16a34a',
          }))}
          valueLabel={money}
        />
      </Panel>
      <Panel
        title={threadLeaderboardTitle}
        subtitle={exportStatus || filterStatus || tableSubtitle}
        action={<StatusBadge label={globalQuery || localQuery ? 'Filtered' : 'Aggregate'} tone="blue" />}
      >
        <DataTable
columns={threadTableColumns}
data={filteredThreads}
compact
getRowId={thread => thread.name}
getRowActionLabel={threadInvestigatorRowLabel}
selectedRowId={selected?.name}
onRowSelect={thread => selectThread(thread.name)}
onRowActivate={openThreadInvestigator}
activateOnClick
selectOnHover
ariaLabel={threadLeaderboardTableLabel}
columnVisibility={columnVisibility}
onColumnVisibilityChange={setColumnVisibility}
sorting={threadSorting}
onSortingChange={updateThreadSorting}
visibleRowCount={visibleThreadRows}
onVisibleRowCountChange={setVisibleThreadRows}
/>
      </Panel>
<ThreadDetail
  selected={selected}
  calls={selectedCalls}
  allCalls={model.calls}
  callSort={threadCallSort}
  visibleCallCount={visibleThreadCallCount}
	  onCallSortChange={updateThreadCallSort}
	  onVisibleCallCountChange={setVisibleThreadCallCount}
	  onOpenInvestigator={onOpenInvestigator}
	  onCopyCallLink={onCopyCallLink}
	/>
    </div>
  );
}

function ThreadDetail({
  selected,
  calls,
  allCalls,
  callSort,
  visibleCallCount,
onCallSortChange,
onVisibleCallCountChange,
onOpenInvestigator,
onCopyCallLink,
}: {
selected: ThreadRow | null;
calls: CallRow[];
allCalls: CallRow[];
callSort: ThreadCallSortKey;
visibleCallCount: number;
onCallSortChange(value: string): void;
onVisibleCallCountChange(count: number | ((current: number) => number)): void;
onOpenInvestigator(recordId: string): void;
onCopyCallLink(recordId: string): void;
}) {
  const shellI18n = useShellI18n();
  const sortedCalls = useMemo(() => sortThreadCalls(calls, callSort), [calls, callSort]);
  const lifecycle = useMemo(() => computeThreadLifecycle(calls, selected?.name ?? ''), [calls, selected?.name]);
  const status = useMemo(() => computeThreadStatus(calls, selected, lifecycle), [calls, lifecycle, selected]);
  const relationships = useMemo(
    () => computeThreadRelationships(calls, allCalls, selected?.name ?? ''),
    [allCalls, calls, selected?.name],
  );
  const efficiencySignalCount = useMemo(() => countThreadEfficiencySignals(calls), [calls]);
  const impact = useMemo(
    () => computeThreadImpact(selected, status, relationships, efficiencySignalCount),
    [efficiencySignalCount, relationships, selected, status],
  );
  const visibleCalls = sortedCalls.slice(0, visibleCallCount);
const hiddenCallCount = Math.max(sortedCalls.length - visibleCalls.length, 0);

if (!selected) {
return (
<aside className="side-panel">
        <Panel title="Selected Thread" subtitle="No matching thread">
          <p className="empty-state">No grouped thread matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel">
      <Panel title="Selected Thread" subtitle={selected.name}>
        <div className="detail-stat-grid vertical">
          <span>
            <strong>{selected.turns}</strong>
            Turns visible
          </span>
          <span>
            <strong>{money(selected.cost)}</strong>
            Estimated cost
          </span>
          <span>
            <strong>{pct(selected.cachePct)}</strong>
            Cache hit rate
          </span>
          <span>
            <strong>{formatCompact(selected.totalTokens)}</strong>
            Total tokens
          </span>
          <span>
            <strong>{selected.totalDuration}</strong>
            Total duration
          </span>
          <span>
            <strong>{selected.averageGap}</strong>
            Average gap
          </span>
          <span>
            <strong>{selected.initiatorSummary}</strong>
            Initiated by
          </span>
          <span>
            <strong>{selected.modelSummary}</strong>
            Models
          </span>
          <span>
            <strong>{selected.effortSummary}</strong>
            Effort mix
          </span>
          <span>
            <strong>{formatCompact(selected.cachedInput)} / {formatCompact(selected.uncachedInput)}</strong>
            Cached / uncached input
          </span>
          <span>
            <strong>{formatCompact(selected.reasoningOutput)}</strong>
            Reasoning output
          </span>
          <span>
            <strong>{selected.contextPct == null ? '-' : pct(selected.contextPct)}</strong>
            Peak context
          </span>
        </div>
        <DonutChart
          centerLabel="Risk Mix"
          data={[
            { label: 'Cold risk', value: selected.coldResumeRisk === 'High' ? 55 : selected.coldResumeRisk === 'Medium' ? 35 : 15, color: '#f59e0b' },
            { label: 'Cache reuse', value: selected.cachePct, color: '#2563eb' },
            { label: 'Productivity', value: selected.productivity, color: '#059669' },
          ]}
        />
        <div className="thread-status-card">
          <div className="section-heading compact">
            <h3>Thread Status</h3>
            <span>{status.nextAction}</span>
          </div>
          <div className="status-thread-grid">
            <span>
              <strong>{status.pricingStatus}</strong>
              Pricing status
            </span>
            <span>
              <strong>{status.creditStatus}</strong>
              Credit status
            </span>
            <span>
              <strong>{status.cacheStatus}</strong>
              Cache ratio
            </span>
            <span>
              <strong>{status.contextStatus}</strong>
              Max context use
            </span>
<span>
<strong>{status.nextAction}</strong>
{shellI18n.t('detail.next_action', 'Next action')}
</span>
          </div>
        </div>
        {impact ? (
          <div className="thread-impact-card">
            <div className="section-heading compact">
              <h3>Thread Impact</h3>
              <span>{impact.allowanceImpact}</span>
            </div>
            <div className="impact-thread-grid">
              <span>
                <strong>{impact.codexCredits}</strong>
                Codex credits
              </span>
              <span>
                <strong>{impact.allowanceImpact}</strong>
                Allowance impact
              </span>
              <span>
                <strong>{impact.attentionScore}</strong>
                Attention score
              </span>
              <span>
                <strong>{impact.costPerCall}</strong>
                Cost per call
              </span>
            </div>
          </div>
        ) : null}
        <div className="thread-lifecycle-card">
          <div className="section-heading compact">
            <h3>Thread Lifecycle</h3>
            <span>{lifecycle.subagentBeforeSpike ? 'Subagent before spike' : 'Aggregate trend'}</span>
          </div>
          <div className="lifecycle-grid">
            <span>
              <strong>
                {lifecycle.firstExpensive
                  ? `${lifecycle.firstExpensive.call.time} · Call ${lifecycle.firstExpensive.index + 1}`
                  : 'None'}
              </strong>
              First expensive turn
            </span>
            <span>
              <strong>
                {lifecycle.largestJump
                  ? `${formatCompact(lifecycle.largestJump.tokens)} at ${lifecycle.largestJump.call.time}`
                  : 'None'}
              </strong>
              Largest token jump
            </span>
            <span>
              <strong>{formatTrendPct(lifecycle.cacheTrend)}</strong>
              Cache trend
            </span>
            <span>
              <strong>{formatTrendPct(lifecycle.contextTrend)}</strong>
              Context trend
            </span>
          </div>
        </div>
        <div className="thread-relationships-card">
          <div className="section-heading compact">
            <h3>Relationships</h3>
            <span>{relationships.spawnedThreads ? `${relationships.spawnedThreads} spawned` : 'Loaded aggregate links'}</span>
          </div>
          <div className="relationship-grid">
            <span>
              <strong>{relationships.parentThreadLabel || 'None'}</strong>
              Spawned from
            </span>
            <span>
              <strong>{relationships.subagentCalls}</strong>
              Subagent calls
            </span>
            <span>
              <strong>{relationships.autoReviewCalls}</strong>
              Auto-review calls
            </span>
            <span>
              <strong>{relationships.attachedCalls}</strong>
              Attached calls
            </span>
            <span>
              <strong>{relationships.spawnedThreads}</strong>
              Spawned threads
            </span>
            <span>
              <strong>{relationships.spawnedChildCalls}</strong>
              Spawned child calls
            </span>
          </div>
        </div>
        <div className="thread-secondary-card">
          <div className="section-heading compact">
            <h3>Thread Fields</h3>
            <span>{efficiencySignalCount ? `${efficiencySignalCount} signals` : 'Aggregate summary'}</span>
          </div>
          <div className="secondary-thread-grid">
            <span>
              <strong>{selected.latestActivity}</strong>
              Latest activity
            </span>
            <span>
              <strong>{formatCompact(selected.totalTokens)}</strong>
              Total tokens
            </span>
            <span>
              <strong>{calls.length}</strong>
              Loaded calls
            </span>
            <span>
              <strong>{efficiencySignalCount}</strong>
              Efficiency signals
            </span>
            <span>
              <strong>{selected.modelSummary}</strong>
              Model mix
            </span>
            <span>
              <strong>{selected.effortSummary}</strong>
              Effort mix
            </span>
          </div>
        </div>
        <div className="thread-call-list">
	          <div className="section-heading compact">
	            <h3>Thread Calls</h3>
	            <span>{sortedCalls.length ? `${visibleCalls.length} of ${sortedCalls.length} loaded` : 'No loaded calls'}</span>
	          </div>
	          {sortedCalls.length ? (
            <>
              <div className="thread-call-controls">
                <label className="mini-select-field">
                  <span>Sort calls</span>
                  <select
                    aria-label="Sort thread calls"
value={callSort}
onChange={event => onCallSortChange(event.target.value)}
                  >
                    <option value="newest">Newest</option>
                    <option value="tokens">Most tokens</option>
                    <option value="cost">Highest cost</option>
                    <option value="cache">Lowest cache</option>
                  </select>
                </label>
              </div>
	            <ol className="thread-mini-timeline">
	              {visibleCalls.map(call => (
	                  <li
	                    key={call.id}
	                    className="thread-call-row has-row-action"
	                    tabIndex={0}
	                    aria-label={`Open investigator for thread call ${call.thread} ${call.model}`}
	                    onClick={() => onOpenInvestigator(call.id)}
	                    onKeyDown={event => {
	                      if (event.key === 'Enter' || event.key === ' ') {
	                        event.preventDefault();
	                        onOpenInvestigator(call.id);
	                      }
	                    }}
	                  >
<span>{call.time}</span>
<strong>{call.model} / {call.effort}</strong>
<em>
{formatCompact(call.totalTokens)} tokens - {pct(call.cachedPct)} cache - {money(call.cost)}
</em>
                <div className="thread-call-flags">
                  <CallSignalPucks call={call} />
                  <span>Context {formatCallContextUse(call)}</span>
                  <span>{callPricingStatusText(call)}</span>
                </div>
                <div className="thread-call-meta">
                  <span>{call.duration}</span>
                  <span>Prev {call.previousCallGap}</span>
                  <span>{call.initiator || 'unknown'} initiated</span>
                  <span>{formatCredits(call.credits)}</span>
                </div>
{call.recommendation ? <p className="thread-call-recommendation">{call.recommendation}</p> : null}
<div className="thread-context-bar" aria-label={`Context use ${formatCallContextUse(call)}`}>
<span className={timelineSeverityClass(call.contextWindowPct)} style={{ width: timelineWidth(call.contextWindowPct) }} />
</div>
<div className="thread-call-actions table-action-group">
<button
className="table-action-button"
type="button"
aria-label={`Open investigator for thread call ${call.thread} ${call.model}`}
onClick={event => {
event.stopPropagation();
onOpenInvestigator(call.id);
}}
>
<Search size={14} />
Open
</button>
<button
className="table-action-button"
type="button"
aria-label={`Copy link for thread call ${call.thread} ${call.model}`}
onClick={event => {
event.stopPropagation();
onCopyCallLink(call.id);
}}
>
<Copy size={14} />
Copy
</button>
</div>
	                </li>
	              ))}
	            </ol>
              <div className="thread-call-pager">
                <button
                  className="toolbar-button"
                  type="button"
onClick={() => onVisibleCallCountChange(current => Math.min(current + threadCallPageSize, sortedCalls.length))}
                  disabled={!hiddenCallCount}
                >
                  Load more
                </button>
                {visibleCallCount > threadCallPageSize ? (
<button className="toolbar-button" type="button" onClick={() => onVisibleCallCountChange(threadCallPageSize)}>
                    Show first {threadCallPageSize}
                  </button>
                ) : null}
                <span>{hiddenCallCount ? `${hiddenCallCount} more available` : 'All loaded calls visible'}</span>
              </div>
            </>
	          ) : (
	            <p className="empty-state">No loaded aggregate call rows belong to this thread.</p>
	          )}
        </div>
      </Panel>
    </aside>
  );
}

function compareCallTimeDescending(left: CallRow, right: CallRow): number {
  return callTimestamp(right) - callTimestamp(left);
}

function callTimestamp(call: CallRow): number {
  const parsed = Date.parse(call.rawTime || call.time);
  return Number.isFinite(parsed) ? parsed : 0;
}

function sortThreadCalls(calls: CallRow[], sortKey: ThreadCallSortKey): CallRow[] {
return [...calls].sort((left, right) => {
if (sortKey === 'tokens') return right.totalTokens - left.totalTokens || compareCallTimeDescending(left, right);
if (sortKey === 'cost') return right.cost - left.cost || compareCallTimeDescending(left, right);
if (sortKey === 'cache') return left.cachedPct - right.cachedPct || compareCallTimeDescending(left, right);
return compareCallTimeDescending(left, right);
});
}

function threadLabelsMatch(callThread: string, threadName: string): boolean {
const callLabel = callThread.trim();
const summaryLabel = threadName.trim();
return callLabel === summaryLabel || callLabel.startsWith(summaryLabel) || summaryLabel.startsWith(callLabel);
}

function computeThreadLifecycle(calls: CallRow[], selectedThreadName: string): ThreadLifecycle {
  const chronologicalCalls = [...calls].sort((left, right) => callTimestamp(left) - callTimestamp(right));
  let largestJump: ThreadLifecycle['largestJump'] = null;
  let firstExpensive: ThreadLifecycle['firstExpensive'] = null;
  let subagentBeforeSpike = false;

  chronologicalCalls.forEach((call, index) => {
    if (!largestJump || call.totalTokens > largestJump.tokens) {
      largestJump = { call, tokens: call.totalTokens };
      subagentBeforeSpike = chronologicalCalls.slice(0, index).some(candidate => isSubagentCall(candidate, selectedThreadName));
    }
    if (!firstExpensive && (call.cost >= 1 || (call.contextWindowPct ?? 0) >= 60)) {
      firstExpensive = { call, index };
    }
  });

  return {
    firstExpensive,
    largestJump,
    cacheTrend: trendBetween(chronologicalCalls.map(call => call.cachedPct)),
    contextTrend: trendBetween(chronologicalCalls.map(call => call.contextWindowPct).filter((value): value is number => value !== null)),
    subagentBeforeSpike,
  };
}

function computeThreadRelationships(
  calls: CallRow[],
  allCalls: CallRow[],
  selectedThreadName: string,
): ThreadRelationships {
  const parentThreadLabel = dominantParentThread(calls, selectedThreadName);
  const childCalls = allCalls.filter(call => call.parentThread.trim() === selectedThreadName && call.thread !== selectedThreadName);
  return {
    parentThreadLabel,
    subagentCalls: calls.filter(call => isSubagentCall(call, selectedThreadName)).length,
    autoReviewCalls: calls.filter(isAutoReviewCall).length,
    attachedCalls: calls.filter(call => Boolean(call.parentThread.trim() && call.parentThread.trim() !== selectedThreadName)).length,
    spawnedThreads: new Set(childCalls.map(call => call.thread).filter(Boolean)).size,
    spawnedChildCalls: childCalls.length,
  };
}

function dominantParentThread(calls: CallRow[], selectedThreadName: string): string {
  const counts = new Map<string, number>();
  calls.forEach(call => {
    const parentThread = call.parentThread.trim();
    if (!parentThread || parentThread === selectedThreadName) return;
    counts.set(parentThread, (counts.get(parentThread) ?? 0) + 1);
  });
  return [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0] ?? '';
}

function isSubagentCall(call: CallRow, selectedThreadName: string): boolean {
  const parentThread = call.parentThread.trim();
  return Boolean(parentThread && parentThread !== selectedThreadName) || call.initiator.toLowerCase().includes('subagent');
}

function isAutoReviewCall(call: CallRow): boolean {
  const model = call.model.toLowerCase();
  const initiator = call.initiator.toLowerCase();
  return model.includes('auto-review') || initiator.includes('auto-review');
}

function countThreadEfficiencySignals(calls: CallRow[]): number {
  return calls.filter(call => {
    const signal = call.signal.trim().toLowerCase();
    return Boolean((signal && signal !== 'aggregate') || call.recommendation.trim());
  }).length;
}

function computeThreadStatus(calls: CallRow[], selected: ThreadRow | null, lifecycle: ThreadLifecycle): ThreadStatus {
  return {
    pricingStatus: threadPricingStatus(calls),
    creditStatus: threadCreditStatus(calls),
    cacheStatus: selected ? pct(selected.cachePct) : '-',
    contextStatus: selected?.contextPct == null ? '-' : pct(selected.contextPct),
    nextAction: threadNextAction(selected, lifecycle),
  };
}

function computeThreadImpact(
  selected: ThreadRow | null,
  status: ThreadStatus,
  relationships: ThreadRelationships,
  signalCount: number,
): ThreadImpact | null {
  if (!selected) return null;
  const attentionScore = threadAttentionScore(selected, status, relationships, signalCount);
  return {
    codexCredits: `${formatCredits(selected.credits)} (${status.creditStatus})`,
    allowanceImpact: `${formatCredits(selected.credits)} counted`,
    attentionScore: formatNumber(attentionScore),
    costPerCall: money(selected.costPerCall),
  };
}

function threadAttentionScore(
  selected: ThreadRow,
  status: ThreadStatus,
  relationships: ThreadRelationships,
  signalCount: number,
): number {
  const contextRatio = (selected.contextPct ?? 0) / 100;
  const cacheRatio = selected.cachePct / 100;
  const pricingScore = status.pricingStatus === 'No price'
    ? 36
    : status.pricingStatus === 'Estimated' || status.pricingStatus === 'Mixed'
      ? 18
      : 0;
  const relationScore = relationships.subagentCalls * 4 + relationships.autoReviewCalls * 6 + relationships.attachedCalls * 3;
  return Math.round(
    clamp(selected.cost * 24, 0, 72)
      + clamp(selected.totalTokens / 3500, 0, 42)
      + clamp((0.55 - cacheRatio) * 70, 0, 38)
      + clamp(contextRatio * 45, 0, 45)
      + pricingScore
      + clamp(selected.credits * 2.4, 0, 72)
      + relationScore
      + signalCount * 10,
  );
}

function formatCredits(value: number): string {
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)} credits`;
}

function formatCallContextUse(call: CallRow): string {
  return call.contextWindowPct == null ? '-' : pct(call.contextWindowPct);
}

function callPricingStatusText(call: CallRow): string {
  if (call.cost <= 0) return 'No configured price';
  return call.pricingEstimated ? 'Best-guess estimate' : 'Configured price';
}

function timelineSeverityClass(value: number | null): string {
  if (value == null) return 'low';
  if (value >= 65) return 'high';
  if (value >= 35) return 'medium';
  return 'low';
}

function timelineWidth(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '0%';
  return `${Math.round(clamp(value, 0, 100))}%`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function threadPricingStatus(calls: CallRow[]): string {
  if (!calls.length) return 'Unknown';
  const pricedCalls = calls.filter(call => call.cost > 0);
  const estimatedCalls = calls.filter(call => call.pricingEstimated);
  if (!pricedCalls.length) return 'No price';
  if (estimatedCalls.length === calls.length) return 'Estimated';
  if (estimatedCalls.length > 0 || pricedCalls.length < calls.length) return 'Mixed';
  return 'Configured';
}

function threadCreditStatus(calls: CallRow[]): string {
  if (!calls.length) return 'Unknown';
  const ratedCalls = calls.filter(call => call.credits > 0);
  const estimatedCalls = calls.filter(call => call.usageCreditConfidence.trim().toLowerCase() === 'estimated');
  if (!ratedCalls.length) return 'No mapped rate';
  if (estimatedCalls.length === calls.length) return 'Estimated mapping';
  if (estimatedCalls.length > 0 || ratedCalls.length < calls.length) return 'Mixed';
  return 'Official match';
}

function threadNextAction(selected: ThreadRow | null, lifecycle: ThreadLifecycle): string {
  if (lifecycle.contextTrend !== null && lifecycle.contextTrend >= 20) return 'Review context growth';
  if (lifecycle.cacheTrend !== null && lifecycle.cacheTrend <= -25) return 'Check cache drop';
  if (lifecycle.subagentBeforeSpike) return 'Compare subagent calls';
  if (selected && ((selected.contextPct ?? 0) >= 60 || selected.cachePct < 30)) return 'Inspect thread timeline';
  return 'Review recommendations';
}

function trendBetween(values: number[]): number | null {
  if (values.length < 2) return null;
  return values[values.length - 1] - values[0];
}

function formatTrendPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '-';
  return `${value >= 0 ? '+' : ''}${pct(value)}`;
}
