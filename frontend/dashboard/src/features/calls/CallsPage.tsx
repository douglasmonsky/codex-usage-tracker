import {
  Activity,
  BarChart3,
  Copy,
  Database,
  Download,
  Filter,
  GitBranch,
LockKeyhole,
PanelRightClose,
PanelRightOpen,
RefreshCw,
  Search,
  ShieldCheck,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { ColumnDef, SortingState, VisibilityState } from '@tanstack/react-table';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import { enableContextApi, loadCallContext, type ContextRequestOptions } from '../../api/context';
import type { CallContextEntry, CallContextPayload, CallRow, ContextRuntime, DashboardModel } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { ColumnChooser } from '../../components/ColumnChooser';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { CallCacheDelta } from '../shared/CallCacheDelta';
import { CallDecisionCard } from '../shared/CallDecisionCard';
import { ContextAttributionModule } from '../shared/ContextAttributionModule';
import { ContextEntryMetadata } from '../shared/ContextEntryMetadata';
import { CallSourceMetadata } from '../shared/CallSourceMetadata';
import { TokenPricingBreakdown } from '../shared/TokenPricingBreakdown';
import { ThreadCallTimeline } from '../shared/ThreadCallTimeline';
import { cacheState, summarizeTopCounts } from '../shared/callPresentation';
import { copyText } from '../shared/copyText';
import {
  cachedCallContext,
  cachedContextEntryOpenKeys,
  cachedContextEntryShowAll,
  cachedContextEntryScrollTop,
  cachedContextOptions,
  contextEntryKey,
  rememberCallContext,
  rememberContextEntryOpen,
  rememberContextEntryShowAll,
  rememberContextEntryScrollTop,
  rememberContextOptions,
} from '../shared/contextEvidenceCache';
import {
  contextErrorMessage as errorMessage,
  contextEvidenceNotes,
  contextRuntimeMessage,
  defaultContextOptions,
  olderContextOptions,
  type ContextLoadState,
} from '../shared/contextEvidenceState';
import { uniqueSorted } from '../shared/filtering';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { presetLabel } from '../shared/investigationPresets';
import { CallSignalPucks, callActionColumn, callColumnChoices, callColumns, callCsvColumns, callInvestigatorRowLabel } from '../shared/tables';
import {
  buildCallsFilterSummary,
  sourceCoverageLabel,
  summarizeSourceCoverage,
  type CallsSortKey,
  type ConfidenceFilter,
  type SortDirection,
  type SourceFilter,
  type TimeFilter,
} from './callFilterSummary';
import {
  buildCallsViewLink,
  cleanCallsDateInput as cleanDateInput,
  coerceCallsSortKey,
  defaultCallsSortDirection,
  detailFirstSelectedCallId,
  readCallsSearchParam,
  readCallsSortKeyParam,
  readConfidenceFilterParam,
  readDateInputParam,
  readDensityParam,
  readInitialSelectedCallId,
  readPageVisibleRowsParam,
  readSortDirectionParam,
  readSourceFilterParam,
  readTimeFilterParam,
  type Density,
} from './callsUrlState';
import { callsDateRange, compareCallTimeDescending, filterCalls, sortCalls } from './callsFilterSort';

type CallsPageProps = {
  model: DashboardModel;
  globalQuery: string;
  activePreset: string;
  onRefresh: () => void;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

type DrillDownTab = 'summary' | 'tokens' | 'cache' | 'thread' | 'evidence';

export function callsForCurrentUrl(calls: CallRow[], globalQuery = '', activePreset = ''): CallRow[] {
  const sortKey = readCallsSortKeyParam();
  return sortCalls(
    filterCalls(calls, {
      globalQuery,
      localQuery: readCallsSearchParam('call_q'),
      modelFilter: readCallsSearchParam('model') || 'all',
      effortFilter: readCallsSearchParam('effort') || 'all',
      confidenceFilter: readConfidenceFilterParam(),
      sourceFilter: readSourceFilterParam(),
      timeFilter: readTimeFilterParam(),
      dateStart: readDateInputParam('from'),
      dateEnd: readDateInputParam('to'),
      activePreset,
    }),
    sortKey,
    readSortDirectionParam(sortKey),
  );
}

const callsDetailPanelStorageKey = 'codexUsageDetailPanel';

const drillDownTabs: Array<{ id: DrillDownTab; label: string; icon: LucideIcon }> = [
  { id: 'summary', label: 'Summary', icon: Activity },
  { id: 'tokens', label: 'Tokens', icon: BarChart3 },
  { id: 'cache', label: 'Cache', icon: Database },
  { id: 'thread', label: 'Thread', icon: GitBranch },
  { id: 'evidence', label: 'Evidence', icon: LockKeyhole },
];

const callsSortToColumnId: Record<CallsSortKey, string> = {
  time: 'time',
  duration: 'duration',
  gap: 'previousCallGap',
  attention: 'signal',
  thread: 'thread',
  initiator: 'initiator',
  model: 'model',
  effort: 'effort',
  total: 'totalTokens',
  cached: 'cachedInput',
  uncached: 'uncachedInput',
  output: 'output',
  reasoning: 'reasoningOutput',
  cost: 'cost',
  usage: 'credits',
  cache: 'cachedPct',
  context: 'contextWindowPct',
};
const callsColumnIdToSort = Object.fromEntries(
  Object.entries(callsSortToColumnId).map(([sortKey, columnId]) => [columnId, sortKey]),
) as Record<string, CallsSortKey>;
const callsTablePageSize = 250;

export function CallsPage({
  model,
  globalQuery,
  activePreset,
  onRefresh,
  contextRuntime,
  onContextApiEnabledChange,
  onOpenInvestigator,
  onCopyCallLink,
}: CallsPageProps) {
  const shellI18n = useShellI18n();
  const [localQuery, setLocalQuery] = useState(() => readCallsSearchParam('call_q'));
  const [modelFilter, setModelFilter] = useState(() => readCallsSearchParam('model') || 'all');
  const [effortFilter, setEffortFilter] = useState(() => readCallsSearchParam('effort') || 'all');
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>(() => readConfidenceFilterParam());
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>(() => readSourceFilterParam());
  const [timeFilter, setTimeFilter] = useState<TimeFilter>(() => readTimeFilterParam());
  const [dateStart, setDateStart] = useState(() => readDateInputParam('from'));
  const [dateEnd, setDateEnd] = useState(() => readDateInputParam('to'));
  const [sortKey, setSortKey] = useState<CallsSortKey>(() => readCallsSortKeyParam());
  const [sortDirection, setSortDirection] = useState<SortDirection>(() => readSortDirectionParam(readCallsSortKeyParam()));
  const [density, setDensity] = useState<Density>(() => readDensityParam());
  const initialSelectedCallId = readInitialSelectedCallId();
  const [selectedCallId, setSelectedCallId] = useState<string | null>(() => initialSelectedCallId);
  const [visibleCallRows, setVisibleCallRows] = useState(() => readPageVisibleRowsParam(callsTablePageSize));
  const [exportStatus, setExportStatus] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [detailsExpanded, setDetailsExpanded] = useState(() => readCallsDetailPanelPreference(Boolean(initialSelectedCallId)));
  const searchInputRef = useRef<HTMLInputElement>(null);
  const previousGlobalQueryRef = useRef(globalQuery);

const modelOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.model)), [model.calls]);
const effortOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.effort)), [model.calls]);
const sourceCoverage = useMemo(() => summarizeSourceCoverage(model.calls), [model.calls]);
const dateRangeStatus = useMemo(() => callsDateRange(timeFilter, dateStart, dateEnd, new Date()), [dateEnd, dateStart, timeFilter]);
const interactiveCallColumns = useMemo<Array<ColumnDef<CallRow>>>(
    () => [...callColumns, callActionColumn({ onOpenInvestigator, onCopyCallLink })],
    [onCopyCallLink, onOpenInvestigator],
  );
  const filteredCalls = useMemo(
    () =>
      filterCalls(model.calls, {
        globalQuery,
        localQuery,
        modelFilter,
        effortFilter,
        confidenceFilter,
        sourceFilter,
        timeFilter,
        dateStart,
        dateEnd,
        activePreset,
      }),
    [activePreset, confidenceFilter, dateEnd, dateStart, effortFilter, globalQuery, localQuery, model.calls, modelFilter, sourceFilter, timeFilter],
  );
  const sortedCalls = useMemo(
    () => sortCalls(filteredCalls, sortKey, sortDirection),
    [filteredCalls, sortDirection, sortKey],
  );
  const tableSubtitle = useMemo(
    () =>
      buildCallsFilterSummary({
        shownCount: sortedCalls.length,
        totalCount: model.calls.length,
        localQuery,
        globalQuery,
        modelFilter,
        effortFilter,
        confidenceFilter,
        sourceFilter,
        timeFilter,
        dateRangeStatus,
        activePresetLabel: activePreset ? presetLabel(activePreset) : '',
      }),
    [
      activePreset,
      confidenceFilter,
      dateRangeStatus,
      effortFilter,
      globalQuery,
      localQuery,
      model.calls.length,
      modelFilter,
      sortedCalls.length,
      sourceFilter,
      timeFilter,
    ],
  );
  const tableSorting = useMemo<SortingState>(
    () => [{ id: callsSortToColumnId[sortKey], desc: sortDirection === 'desc' }],
    [sortDirection, sortKey],
  );
  const selectedCall =
    selectedCallId === detailFirstSelectedCallId
      ? sortedCalls[0] ?? null
      : sortedCalls.find(call => call.id === selectedCallId) ?? sortedCalls[0] ?? null;
  const selectedRecordId =
    selectedCall && (selectedCall.id === selectedCallId || selectedCallId === detailFirstSelectedCallId)
      ? selectedCall.id
      : '';

  useEffect(() => {
    if (previousGlobalQueryRef.current === globalQuery) return;
    previousGlobalQueryRef.current = globalQuery;
    setVisibleCallRows(callsTablePageSize);
  }, [globalQuery]);

  useEffect(() => {
    if (selectedCallId === detailFirstSelectedCallId && selectedRecordId) {
      setSelectedCallId(selectedRecordId);
    }
  }, [selectedCallId, selectedRecordId]);

  useEffect(() => {
    const url = buildCallsViewLink({
      localQuery,
modelFilter,
effortFilter,
confidenceFilter,
sourceFilter,
timeFilter,
dateStart,
dateEnd,
sortKey,
sortDirection,
density,
selectedRecordId,
visibleRowCount: visibleCallRows,
pageSize: callsTablePageSize,
});
if (url.toString() !== window.location.href) {
window.history.replaceState(null, '', url);
}
}, [confidenceFilter, dateEnd, dateStart, density, effortFilter, localQuery, modelFilter, selectedRecordId, sortDirection, sortKey, sourceFilter, timeFilter, visibleCallRows]);

function exportCalls() {
    downloadCsv(`codex-calls-${csvDateStamp()}.csv`, rowsToCsv(sortedCalls, callCsvColumns));
    setExportStatus(`Exported ${sortedCalls.length} calls`);
  }

  async function copyCallsViewLink() {
    try {
      const url = buildCallsViewLink({
        localQuery,
        modelFilter,
        effortFilter,
confidenceFilter,
sourceFilter,
timeFilter,
        dateStart,
        dateEnd,
          sortKey,
          sortDirection,
          density,
selectedRecordId,
visibleRowCount: visibleCallRows,
pageSize: callsTablePageSize,
});
      const copied = await copyText(url.toString());
      if (!copied) {
        throw new Error('Clipboard unavailable');
      }
      setExportStatus('Copied Calls view link');
    } catch {
      setExportStatus('Copy unavailable in browser');
    }
  }

  function focusFilters() {
    searchInputRef.current?.focus();
    setFilterStatus(`Filters ready for ${sortedCalls.length} calls`);
  }

  function resetCallTablePage() {
    setVisibleCallRows(callsTablePageSize);
  }

  function updateLocalQuery(value: string) {
    setLocalQuery(value);
    resetCallTablePage();
  }

  function updateModelFilter(value: string) {
    setModelFilter(value);
    resetCallTablePage();
  }

  function updateEffortFilter(value: string) {
    setEffortFilter(value);
    resetCallTablePage();
  }

  function updateConfidenceFilter(value: ConfidenceFilter) {
    setConfidenceFilter(value);
    resetCallTablePage();
  }

  function updateSourceFilter(value: SourceFilter) {
    setSourceFilter(value);
    resetCallTablePage();
  }

  function updateTimeFilter(value: TimeFilter) {
    setTimeFilter(value);
    resetCallTablePage();
  }

  function clearCallFilters() {
    setLocalQuery('');
    setModelFilter('all');
    setEffortFilter('all');
    setConfidenceFilter('all');
    setSourceFilter('all');
    setTimeFilter('all');
    setDateStart('');
    setDateEnd('');
    setSortKey('time');
    setSortDirection(defaultCallsSortDirection('time'));
setDensity('dense');
setSelectedCallId(null);
setVisibleCallRows(callsTablePageSize);
const url = buildCallsViewLink({
      localQuery: '',
      modelFilter: 'all',
      effortFilter: 'all',
      confidenceFilter: 'all',
      sourceFilter: 'all',
      timeFilter: 'all',
      dateStart: '',
      dateEnd: '',
sortKey: 'time',
sortDirection: defaultCallsSortDirection('time'),
density: 'dense',
selectedRecordId: '',
visibleRowCount: callsTablePageSize,
pageSize: callsTablePageSize,
});
window.history.replaceState(null, '', url);
setFilterStatus('Calls filters cleared');
}

function toggleCallDetails() {
setDetailsExpanded(expanded => {
const nextExpanded = !expanded;
rememberCallsDetailPanelPreference(nextExpanded);
return nextExpanded;
});
  }

  function updateDateStart(value: string) {
    setDateStart(cleanDateInput(value));
    setTimeFilter('custom');
    resetCallTablePage();
  }

  function updateDateEnd(value: string) {
    setDateEnd(cleanDateInput(value));
    setTimeFilter('custom');
    resetCallTablePage();
  }

function updateSortKey(value: string) {
const nextSort = coerceCallsSortKey(value);
setSortKey(nextSort);
    setSortDirection(defaultCallsSortDirection(nextSort));
    resetCallTablePage();
  }

  function updateSortDirection(value: string) {
    setSortDirection(value === 'asc' ? 'asc' : 'desc');
    resetCallTablePage();
  }

  function updateTableSorting(updater: SortingState | ((old: SortingState) => SortingState)) {
    const nextSorting = typeof updater === 'function' ? updater(tableSorting) : updater;
    const nextSort = callsColumnIdToSort[nextSorting[0]?.id ?? ''] ?? 'time';
    const isChangingSortKey = nextSort !== sortKey;
    setSortKey(nextSort);
    setSortDirection(isChangingSortKey ? defaultCallsSortDirection(nextSort) : nextSorting[0]?.desc ? 'desc' : 'asc');
    resetCallTablePage();
  }

  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Calls</h1>
          <p>High-density analyst view model calls, cost, cache hits, duration.</p>
        </div>
        <div className="toolbar">
          <ColumnChooser
            label="Calls"
            columns={callColumnChoices}
            open={columnsOpen}
            onOpenChange={setColumnsOpen}
            visibility={columnVisibility}
            onVisibilityChange={setColumnVisibility}
          />
        <button className="toolbar-button" type="button" onClick={exportCalls} disabled={!sortedCalls.length}>
          <Download size={16} />
          Export
        </button>
        <button className="toolbar-button" type="button" onClick={copyCallsViewLink}>
          <Copy size={16} />
          Copy view
        </button>
        <button className="primary-button" type="button" onClick={onRefresh}>
          <RefreshCw size={16} />
          Refresh
          </button>
        </div>
      </div>
      <div className="dashboard-grid three">
        <Panel title="Usage Over Time" subtitle="Tokens">
          <LineChart series={model.tokenSeries} yLabel="Tokens" height={220} />
        </Panel>
        <Panel title="Cost by Model" subtitle="Estimated USD">
          <BarChart data={model.modelCosts} valueLabel={money} />
        </Panel>
        <Panel title="Cache Hit Rate Over Time" subtitle="Daily">
          <LineChart series={model.cacheSeries} yLabel="Cache %" height={220} valueFormatter={value => `${value}%`} />
        </Panel>
      </div>
      <div className="filter-row">
        <label className="search-box">
          <span className="sr-only">Search calls</span>
<input ref={searchInputRef} value={localQuery} onChange={event => updateLocalQuery(event.target.value)} placeholder="Search calls, cwd, projects, models..." />
        </label>
        <label className="filter-field">
          <span>Model</span>
<select value={modelFilter} onChange={event => updateModelFilter(event.target.value)}>
            <option value="all">All models</option>
            {modelOptions.map(option => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Effort</span>
<select value={effortFilter} onChange={event => updateEffortFilter(event.target.value)}>
            <option value="all">All effort</option>
            {effortOptions.map(option => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
        </select>
      </label>
      <label className="filter-field">
        <span>Confidence</span>
        <select
          aria-label="Confidence filter"
          value={confidenceFilter}
onChange={event => updateConfidenceFilter(event.target.value as ConfidenceFilter)}
        >
<option value="all">All confidence</option>
<option value="cost-exact">Exact cost</option>
<option value="cost-estimated">Estimated cost</option>
<option value="cost-unpriced">Unpriced cost</option>
<option value="credit-exact">Exact credit rate</option>
<option value="credit-estimated">Estimated credit mapping</option>
<option value="credit-override">User credit override</option>
<option value="credit-missing">Missing credit rate</option>
</select>
</label>
<label className="filter-field">
<span>Source</span>
<select aria-label="Source filter" value={sourceFilter} onChange={event => updateSourceFilter(event.target.value as SourceFilter)}>
<option value="all">All sources</option>
<option value="project">Project / cwd</option>
<option value="session">Session-linked</option>
<option value="git">Git metadata</option>
<option value="source-file">Source file</option>
<option value="missing">Missing source</option>
</select>
<span className="filter-status" data-state={sourceFilter === 'all' ? 'active' : 'filtered'} aria-live="polite">
{sourceCoverageLabel(sourceCoverage, sourceFilter)}
</span>
</label>
<label className="filter-field">
<span>Time</span>
<select aria-label="Time filter" value={timeFilter} onChange={event => updateTimeFilter(event.target.value as TimeFilter)}>
          <option value="all">All time</option>
          <option value="today">Today</option>
          <option value="this-week">This week</option>
          <option value="last-7-days">Last 7 days</option>
<option value="this-month">This month</option>
<option value="custom">Custom range</option>
</select>
{dateRangeStatus.active || dateRangeStatus.invalid ? (
<span className="filter-status" data-state={dateRangeStatus.invalid ? 'error' : 'active'} aria-live="polite">
{dateRangeStatus.label}
</span>
) : null}
</label>
      <label className="filter-field">
        <span>Start</span>
        <input aria-label="Start date" type="date" value={dateStart} onChange={event => updateDateStart(event.target.value)} />
      </label>
      <label className="filter-field">
        <span>End</span>
        <input aria-label="End date" type="date" value={dateEnd} onChange={event => updateDateEnd(event.target.value)} />
      </label>
      <label className="filter-field">
        <span>Sort</span>
        <select aria-label="Sort calls" value={sortKey} onChange={event => updateSortKey(event.target.value)}>
          <option value="time">Newest calls</option>
          <option value="duration">Longest duration</option>
          <option value="gap">Longest gap</option>
          <option value="attention">Needs attention</option>
          <option value="thread">Thread name</option>
          <option value="initiator">Initiated</option>
          <option value="model">Model</option>
          <option value="effort">Reasoning</option>
          <option value="total">Most tokens</option>
          <option value="cached">Cached</option>
          <option value="uncached">Uncached</option>
          <option value="output">Output</option>
          <option value="reasoning">Reasoning output</option>
          <option value="cost">Highest estimated cost</option>
          <option value="usage">Highest Codex credits</option>
          <option value="cache">Lowest cache ratio</option>
          <option value="context">Highest context use</option>
        </select>
      </label>
      <label className="filter-field">
        <span>Direction</span>
<select aria-label="Sort direction" value={sortDirection} onChange={event => updateSortDirection(event.target.value)}>
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
<button className="toolbar-button" type="button" onClick={focusFilters}>
<Filter size={16} />
More Filters
</button>
<button className="toolbar-button" type="button" onClick={clearCallFilters}>
<X size={16} />
Clear filters
</button>
<div className="density-toggle" aria-label="Density">
          <button type="button" className={density === 'dense' ? 'active' : ''} aria-pressed={density === 'dense'} onClick={() => setDensity('dense')}>
            Dense
          </button>
          <button type="button" className={density === 'roomy' ? 'active' : ''} aria-pressed={density === 'roomy'} onClick={() => setDensity('roomy')}>
            Roomy
          </button>
        </div>
      </div>
<div className={detailsExpanded ? 'table-detail-layout' : 'table-detail-layout detail-collapsed'}>
      <Panel
        title={shellI18n.t('dashboard.model_calls', 'Model Calls')}
        subtitle={exportStatus || filterStatus || tableSubtitle}
          action={
            <div className="panel-action-group">
              <StatusBadge
                label={activePreset ? `Preset: ${presetLabel(activePreset)}` : 'Raw context gated'}
                tone={activePreset ? 'green' : 'blue'}
              />
              <button className="toolbar-button" type="button" aria-expanded={detailsExpanded} onClick={toggleCallDetails}>
                {detailsExpanded ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
                {detailsExpanded ? shellI18n.t('button.hide_details', 'Hide details') : shellI18n.t('dashboard.call_details', 'Call Details')}
              </button>
            </div>
          }
        >
        <DataTable
          columns={interactiveCallColumns}
          data={sortedCalls}
            compact={density === 'dense'}
          getRowId={call => call.id}
          getRowActionLabel={call => callInvestigatorRowLabel(call)}
          selectedRowId={selectedCall?.id}
        onRowSelect={call => setSelectedCallId(call.id)}
        onRowActivate={call => onOpenInvestigator(call.id)}
        activateOnClick
        selectOnHover
        ariaLabel={shellI18n.t('dashboard.model_calls', 'Model calls')}
            columnVisibility={columnVisibility}
            onColumnVisibilityChange={setColumnVisibility}
            sorting={tableSorting}
            onSortingChange={updateTableSorting}
            manualSorting
            visibleRowCount={visibleCallRows}
            onVisibleRowCountChange={setVisibleCallRows}
          />
        </Panel>
{detailsExpanded ? <CallDrillDown
call={selectedCall}
calls={model.calls}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={onContextApiEnabledChange}
          onOpenInvestigator={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
        /> : null}
      </div>
    </div>
  );
}

function CallDrillDown({
  call,
  calls,
  contextRuntime,
  onContextApiEnabledChange,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow | null;
  calls: CallRow[];
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<DrillDownTab>('summary');
  const [copyStatus, setCopyStatus] = useState('');
  const threadCalls = useMemo(() => {
    if (!call) return [];
    return calls.filter(candidate => candidate.thread === call.thread).sort(compareCallTimeDescending);
  }, [call, calls]);

  if (!call) {
    return (
      <aside className="side-panel drilldown-panel">
        <Panel title="Call Drill-Down" subtitle="No matching call">
          <p className="empty-state">No aggregate row matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel drilldown-panel">
      <Panel title="Call Drill-Down" subtitle={`${call.thread} / ${call.model}`}>
        <div className="call-summary">
          <StatusBadge label="Aggregate only" tone="green" />
          <CallSignalPucks call={call} />
          <StatusBadge label="Raw context gated" tone="blue" />
          <span className="call-id">{call.id.slice(0, 12)}</span>
        </div>
        <div className="action-row">
<button className="toolbar-button" type="button" onClick={() => onOpenInvestigator(call.id)}>
<Search size={16} />
Open investigator
</button>
<button className="toolbar-button" type="button" onClick={() => copyInvestigatorLink(call, setCopyStatus)}>
<Copy size={16} />
Copy link
</button>
</div>
{copyStatus ? <p className="context-state-note">{copyStatus}</p> : null}
<div className="drilldown-tabs" role="tablist" aria-label="Call drill-down sections">
          {drillDownTabs.map(tab => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={selected}
                className={selected ? 'active' : ''}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="drilldown-tab-panel" role="tabpanel">
          {activeTab === 'summary' ? <SummaryTab call={call} /> : null}
          {activeTab === 'tokens' ? <TokensTab call={call} /> : null}
          {activeTab === 'cache' ? <CacheTab call={call} calls={threadCalls} /> : null}
          {activeTab === 'thread' ? (
            <ThreadTab
              call={call}
              calls={threadCalls}
              onOpenInvestigator={onOpenInvestigator}
              onCopyCallLink={onCopyCallLink}
            />
          ) : null}
          {activeTab === 'evidence' ? (
            <EvidenceTab
              key={call.id}
              call={call}
              contextRuntime={contextRuntime}
              onContextApiEnabledChange={onContextApiEnabledChange}
            />
          ) : null}
        </div>
      </Panel>
    </aside>
  );
}

function SummaryTab({ call }: { call: CallRow }) {
  return (
    <>
    <div className="drilldown-metric-grid">
      <DrillMetric label="Total tokens" value={formatNumber(call.totalTokens)} detail={`${formatCompact(call.input)} input`} />
      <DrillMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="fresh billed input" />
        <DrillMetric label="Cache hit rate" value={pct(call.cachedPct)} detail={cacheState(call)} />
        <DrillMetric label="Estimated cost" value={money(call.cost)} detail={call.pricingEstimated ? 'estimated pricing' : 'configured pricing'} />
        <DrillMetric label="Duration" value={call.duration} detail={call.fast ? 'fast candidate' : 'normal throughput'} />
<DrillMetric label="Usage credits" value={call.credits ? call.credits.toFixed(3) : '-'} detail={call.usageCreditConfidence} />
    </div>
    <CallDecisionCard call={call} />
    <CallSourceMetadata call={call} />
    <CallAccountingSnapshot call={call} />
    <TokenComposition call={call} />
    <CacheMiniChart call={call} />
      {call.recommendation ? (
        <div className="recommendation-box">
          <ShieldCheck size={16} />
          <p>{call.recommendation}</p>
        </div>
      ) : null}
    </>
  );
}

function CallAccountingSnapshot({ call }: { call: CallRow }) {
  return (
    <div className="composition-card accounting-snapshot-card">
      <div className="composition-head">
        <strong>Accounting Snapshot</strong>
        <span>pricing, credits, and cache savings</span>
      </div>
      <TokenPricingBreakdown call={call} />
    </div>
  );
}

function TokensTab({ call }: { call: CallRow }) {
  return (
    <>
<TokenComposition call={call} />
<TokenPricingBreakdown call={call} />
</>
);
}

function CacheTab({ call, calls }: { call: CallRow; calls: CallRow[] }) {
  return (
    <>
      <CacheMiniChart call={call} />
      <CallCacheDelta call={call} calls={calls} />
      <dl className="detail-list">
<DetailRow label="Cache state" value={cacheState(call)} />
<DetailRow label="Cache hit rate" value={pct(call.cachedPct)} />
<DetailRow label="Fresh share" value={pct(Math.max(100 - call.cachedPct, 0))} />
<DetailRow label="Signal" value={call.signal} />
</dl>
<p className="privacy-note">Use this readout to decide whether the aggregate call needs deeper raw-context investigation.</p>
</>
);
}

function ThreadTab({
  call,
  calls,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow;
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const totalTokens = calls.reduce((sum, row) => sum + row.totalTokens, 0);
  const totalCost = calls.reduce((sum, row) => sum + row.cost, 0);
  const averageCache = calls.reduce((sum, row) => sum + row.cachedPct, 0) / Math.max(calls.length, 1);
  const selectedIndex = Math.max(calls.findIndex(row => row.id === call.id), 0);
  const timelineCount = Math.min(Math.max(calls.length, 1), 5);
  const source = call.sourceFile ? `${call.sourceFile}${call.lineNumber ? `:${call.lineNumber}` : ''}` : 'Not available';

  return (
    <>
      <div className="drilldown-metric-grid">
        <DrillMetric label="Loaded thread calls" value={formatNumber(calls.length)} detail={`selected ${selectedIndex + 1} of ${calls.length}`} />
        <DrillMetric label="Thread tokens" value={formatCompact(totalTokens)} detail="loaded aggregate rows" />
        <DrillMetric label="Thread cost" value={money(totalCost)} detail="estimated aggregate" />
          <DrillMetric
            label="Avg cache"
            value={pct(averageCache)}
            detail={summarizeTopCounts(calls.map(row => row.model), { style: 'x', emptyLabel: 'no model mix' })}
          />
        <DrillMetric label="Context window" value={call.contextWindowPct === null ? '-' : pct(call.contextWindowPct)} detail={call.modelContextWindow ? `${formatCompact(call.modelContextWindow)} window` : 'not reported'} />
        <DrillMetric label="Parent thread" value={call.parentThread || '-'} detail={call.parentSessionId || 'no parent session'} />
      </div>
      <div className="composition-card">
        <div className="composition-head">
          <strong>Thread timeline</strong>
          <span>{timelineCount} nearby loaded calls</span>
        </div>
        <ThreadCallTimeline
          selectedCall={call}
          calls={calls}
          onOpenInvestigator={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
          copyAriaContext="side-panel thread call"
        />
      </div>
<div className="composition-card">
<div className="composition-head">
<strong>Call Narrative</strong>
<span>{call.initiatorConfidence || 'aggregate inference'}</span>
</div>
<dl className="detail-list compact">
<DetailRow label="Initiated by" value={call.initiator || 'unknown'} />
<DetailRow label="Initiator reason" value={call.initiatorReason || 'Not reported'} />
<DetailRow label="Parent thread" value={call.parentThread || 'None'} />
<DetailRow label="Parent session" value={call.parentSessionId || 'None'} />
<DetailRow label="Timestamp" value={call.time} />
<DetailRow label="Duration" value={call.duration} />
<DetailRow label="Previous gap" value={call.previousCallGap} />
</dl>
</div>
<dl className="detail-list">
<DetailRow label="Project" value={call.project || 'Unknown'} />
        <DetailRow label="Project path" value={call.projectRelativeCwd || call.cwd || '.'} />
        <DetailRow label="Source line" value={source} />
        <DetailRow label="Session" value={call.sessionId || 'Not available'} />
        <DetailRow label="Git branch" value={call.gitBranch || 'Unknown'} />
        <DetailRow label="Remote" value={call.gitRemoteLabel || call.gitRemoteHash || 'None'} />
      </dl>
    </>
  );
}

function EvidenceTab({
call,
  contextRuntime,
  onContextApiEnabledChange,
}: {
  call: CallRow;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
}) {
  const shellI18n = useShellI18n();
  const [options, setOptions] = useState(() => cachedContextOptions(call.id) ?? defaultContextOptions);
  const [contextState, setContextState] = useState<ContextLoadState>({ status: 'idle' });
  const canUseContextServer = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const canLoadContext = canUseContextServer && contextRuntime.contextApiEnabled;

  useEffect(() => {
    const cached = cachedCallContext(call.id, options);
    setContextState(cached ? { status: 'loaded', payload: cached } : { status: 'idle' });
  }, [call.id, options.includeCompactionHistory, options.includeToolOutput, options.maxChars, options.maxEntries, options.mode]);

  async function enableContextLoading() {
    setContextState({ status: 'loading', message: 'Enabling localhost context API...' });
    try {
      const enabled = await enableContextApi(contextRuntime);
      onContextApiEnabledChange(enabled);
      setContextState({
        status: 'idle',
        message: enabled ? 'Context API enabled. Load this call when ready.' : 'Context API did not enable.',
      });
    } catch (error) {
      setContextState({ status: 'error', message: errorMessage(error) });
    }
  }

  async function loadEvidence(nextOptions: ContextRequestOptions = options, message = 'Loading selected-turn evidence...') {
    rememberContextOptions(call.id, nextOptions);
    const cached = cachedCallContext(call.id, nextOptions);
    if (cached) {
      setContextState({ status: 'loaded', payload: cached });
      return;
    }
    setContextState({ status: 'loading', message });
    try {
      const payload = await loadCallContext(call.id, contextRuntime, nextOptions);
      rememberCallContext(call.id, nextOptions, payload);
      setContextState({ status: 'loaded', payload });
    } catch (error) {
      setContextState({ status: 'error', message: errorMessage(error) });
}
}

function loadFullAnalysis() {
const nextOptions: ContextRequestOptions = { ...options, mode: 'full' };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading full turn analysis...');
}

function loadOlderContext(payload: CallContextPayload) {
const nextOptions = olderContextOptions(payload, options);
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading older context...');
}

function loadToolOutput() {
const nextOptions: ContextRequestOptions = { ...options, includeToolOutput: true };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading omitted tool output...');
}

function loadCompactionHistory() {
const nextOptions: ContextRequestOptions = { ...options, includeCompactionHistory: true };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading compacted replacement...');
}

  function updateOption<K extends keyof ContextRequestOptions>(key: K, value: ContextRequestOptions[K]) {
    setOptions(current => {
      const next = { ...current, [key]: value };
      rememberContextOptions(call.id, next);
      return next;
    });
  }

  return (
    <>
      <div className="locked-context-card">
        <LockKeyhole size={20} />
        <div>
          <strong>Raw context is gated</strong>
          <p>{contextRuntimeMessage(contextRuntime)}</p>
        </div>
      </div>
      <dl className="detail-list">
        <DetailRow label="Record id" value={call.id} />
        <DetailRow label="Time" value={call.time} />
        <DetailRow label="Thread" value={call.thread} />
        <DetailRow label="Model" value={call.model} />
        <DetailRow label="Effort" value={call.effort} />
      </dl>
      <div className="context-action-grid">
        <button
          className="toolbar-button"
          type="button"
          onClick={enableContextLoading}
          disabled={!canUseContextServer || contextRuntime.contextApiEnabled || contextState.status === 'loading'}
        >
          {shellI18n.t('button.enable_context_loading', 'Enable context loading')}
        </button>
<button
className="primary-button"
type="button"
onClick={() => loadEvidence()}
disabled={!canLoadContext || contextState.status === 'loading'}
>
{shellI18n.t('button.show_turn_evidence', 'Show turn log evidence')}
</button>
<button
className="toolbar-button"
type="button"
onClick={loadFullAnalysis}
disabled={!canLoadContext || contextState.status === 'loading'}
>
{shellI18n.t('button.full_serialized_analysis', 'Run full serialized analysis')}
</button>
<label className="context-field">
<span>Mode</span>
<select
aria-label="Side panel context mode"
value={options.mode}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('mode', event.target.value === 'full' ? 'full' : 'quick')}
>
<option value="quick">Quick</option>
<option value="full">Full</option>
</select>
</label>
<label className="context-field">
<span>Entries</span>
<select
aria-label="Side panel context entries"
value={String(options.maxEntries)}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('maxEntries', Number(event.target.value))}
>
<option value="20">20</option>
<option value="50">50</option>
<option value="100">100</option>
<option value="0">All</option>
</select>
</label>
<label className="toggle-row">
<input
type="checkbox"
            checked={options.includeToolOutput}
            disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('includeToolOutput', event.target.checked)}
/>
{shellI18n.t('button.include_tool_output', 'Include tool output')}
</label>
<label className="toggle-row">
<input
type="checkbox"
checked={options.includeCompactionHistory}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('includeCompactionHistory', event.target.checked)}
/>
Include compaction history
</label>
<label className="toggle-row">
<input
type="checkbox"
            checked={options.maxChars === 0}
            disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('maxChars', event.target.checked ? 0 : defaultContextOptions.maxChars)}
          />
          {shellI18n.t('button.no_char_limit', 'No char limit')}
        </label>
      </div>
      {contextState.status === 'idle' && contextState.message ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'loading' ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'error' ? <p className="context-state-note error">{contextState.message}</p> : null}
      {contextState.status === 'loaded' ? (
        <ContextEvidence
          call={call}
          payload={contextState.payload}
          onLoadOlder={loadOlderContext}
          onRunFullAnalysis={loadFullAnalysis}
          onLoadCompactionHistory={loadCompactionHistory}
          onLoadToolOutput={loadToolOutput}
        />
      ) : null}
      <p className="privacy-note">
        Raw context is never embedded in the dashboard HTML. This view reads the selected local JSONL turn only after an explicit request.
      </p>
    </>
  );
}

function ContextEvidence({
call,
payload,
onLoadOlder,
onRunFullAnalysis,
onLoadCompactionHistory,
onLoadToolOutput,
}: {
call: CallRow;
payload: CallContextPayload;
onLoadOlder: (payload: CallContextPayload) => void;
onRunFullAnalysis: () => void;
onLoadCompactionHistory: () => void;
onLoadToolOutput: () => void;
}) {
const shellI18n = useShellI18n();
const entries = payload.entries ?? [];
const omitted = payload.omitted ?? {};
  const olderEntries = Number(omitted.older_entries ?? 0);
  const notes = contextEvidenceNotes(payload);
  const initialEntryLimit = 8;
  const recordId = call.id || String(payload.record_id ?? '');
  const [showAllEntries, setShowAllEntries] = useState(() => cachedContextEntryShowAll(recordId));
  const [openEntryKeys, setOpenEntryKeys] = useState<Set<string>>(() => cachedContextEntryOpenKeys(recordId, entries));
  useEffect(() => {
    setShowAllEntries(cachedContextEntryShowAll(recordId));
    setOpenEntryKeys(cachedContextEntryOpenKeys(recordId, entries));
  }, [
    entries.length,
    payload.context_mode,
    payload.include_compaction_history,
    payload.include_tool_output,
    payload.omitted?.max_chars,
    payload.omitted?.max_entries,
    payload.record_id,
    recordId,
  ]);
const visibleEntries = showAllEntries ? entries : entries.slice(0, initialEntryLimit);
const hiddenEntryCount = Math.max(entries.length - visibleEntries.length, 0);
function toggleShowAllEntries() {
setShowAllEntries(current => {
const next = !current;
rememberContextEntryShowAll(recordId, next);
return next;
});
}
function rememberEntryOpen(key: string, open: boolean) {
rememberContextEntryOpen(recordId, key, open);
setOpenEntryKeys(current => {
const next = new Set(current);
if (open) {
next.add(key);
} else {
next.delete(key);
}
return next;
});
}

return (
<div className="context-evidence">
<div className="context-evidence-summary">
<DrillMetric label="Entries" value={formatNumber(entries.length)} detail={String(payload.context_mode ?? 'quick')} />
<DrillMetric label="Visible chars" value={formatNumber(Number(payload.visible_char_count ?? 0))} detail="redacted local text" />
<DrillMetric label="Visible tokens" value={formatNumber(Number(payload.visible_token_estimate ?? 0))} detail="estimator" />
<DrillMetric label="Older omitted" value={formatNumber(olderEntries)} detail="entry budget" />
</div>
{notes.length ? <p className="context-note">{notes.join(' ')}</p> : null}
<ContextAttributionModule call={call} payload={payload} onRunFullAnalysis={onRunFullAnalysis} />
{olderEntries > 0 ? (
<div className="context-followup-actions">
<button className="toolbar-button" type="button" onClick={() => onLoadOlder(payload)}>
{shellI18n.t('button.load_older_context', 'Load older entries')}
</button>
</div>
) : null}
<div className="context-entry-list">
{visibleEntries.map((entry, index) => {
const key = contextEntryKey(entry, index);
return (
<details className="context-entry" key={key} open={openEntryKeys.has(key)} onToggle={event => rememberEntryOpen(key, event.currentTarget.open)}>
<summary className="context-entry-summary">
<div className="context-entry-meta">
<strong>{entry.label || entry.role || entry.type || `Entry ${index + 1}`}</strong>
<span>{entry.line_number ? `line ${entry.line_number}` : entry.timestamp || 'local evidence'}</span>
</div>
</summary>
<ContextEntryMetadata entry={entry} />
          {entry.tool_output_omitted ? (
            <div className="context-entry-actions">
              <button className="toolbar-button" type="button" onClick={onLoadToolOutput}>
{shellI18n.t('button.show_tool_output', 'Show tool output')}
</button>
</div>
) : null}
<ContextEntryCompaction entry={entry} onLoadCompactionHistory={onLoadCompactionHistory} />
<pre
ref={element => {
if (element) element.scrollTop = cachedContextEntryScrollTop(recordId, key);
}}
onScroll={event => rememberContextEntryScrollTop(recordId, key, event.currentTarget.scrollTop)}
>{entry.text || '[no visible text]'}</pre>
</details>
);
})}
{!entries.length ? <p className="empty-state">No visible evidence entries returned for this call.</p> : null}
</div>
{entries.length > initialEntryLimit ? (
<div className="context-followup-actions">
<button className="toolbar-button" type="button" onClick={toggleShowAllEntries}>
{showAllEntries
? `Show first ${formatNumber(initialEntryLimit)} entries`
: `Show all ${formatNumber(entries.length)} returned entries`}
</button>
{!showAllEntries ? <span className="context-entry-count-note">{formatNumber(hiddenEntryCount)} entries hidden in compact view</span> : null}
</div>
) : null}
</div>
);
}

function ContextEntryCompaction({
entry,
onLoadCompactionHistory,
}: {
entry: CallContextEntry;
onLoadCompactionHistory: () => void;
}) {
const shellI18n = useShellI18n();
const compaction = entry.compaction;
if (!compaction?.replacement_history_available) return null;
const replacementHistory = compaction.replacement_history ?? [];
const replacementCount = Number(compaction.replacement_entry_count ?? replacementHistory.length);

return (
<div className="context-entry-compaction">
<strong>Compaction detected</strong>
<span>{formatNumber(replacementCount)} replacement history entries available.</span>
{replacementHistory.length ? (
<div className="context-replacement-history" aria-label="Compacted replacement context">
{replacementHistory.map((item, index) => (
<div className="context-replacement-entry" key={`${item.label ?? 'replacement'}-${index}`}>
<strong>{item.label || `Replacement item ${index + 1}`}</strong>
<pre>{item.text || '[no visible replacement text]'}</pre>
</div>
))}
</div>
) : (
<div className="context-entry-actions">
<button className="toolbar-button" type="button" onClick={onLoadCompactionHistory}>
{shellI18n.t('button.show_compaction_history', 'Show compacted replacement')}
</button>
</div>
)}
</div>
);
}

function readCallsDetailPanelPreference(defaultExpanded = false): boolean {
  try {
    const storedValue = window.sessionStorage?.getItem(callsDetailPanelStorageKey);
    return storedValue ? storedValue === 'expanded' : defaultExpanded;
  } catch {
    return defaultExpanded;
  }
}

function rememberCallsDetailPanelPreference(expanded: boolean) {
  try {
    window.sessionStorage?.setItem(callsDetailPanelStorageKey, expanded ? 'expanded' : 'collapsed');
  } catch {
    // Session storage is optional; the visible toggle still works without persistence.
  }
}

function DrillMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <span className="drilldown-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TokenComposition({ call }: { call: CallRow }) {
  const cachedInput = Math.max(call.input - call.uncachedInput, 0);
  const segments = [
    { label: 'Cached input', value: cachedInput, color: '#2563eb' },
    { label: 'Uncached input', value: call.uncachedInput, color: '#f59e0b' },
    { label: 'Output', value: call.output, color: '#059669' },
    { label: 'Reasoning', value: call.reasoningOutput, color: '#7c3aed' },
  ].filter(segment => segment.value > 0);
  const total = Math.max(
    segments.reduce((sum, segment) => sum + segment.value, 0),
    1,
  );

  return (
    <div className="composition-card">
      <div className="composition-head">
        <strong>Token composition</strong>
        <span>{formatCompact(total)} visible tokens</span>
      </div>
      <div className="composition-bar" aria-label="Token composition">
        {segments.map(segment => (
          <i key={segment.label} style={{ width: `${Math.max(segment.value / total * 100, 3)}%`, background: segment.color }} />
        ))}
      </div>
      <div className="composition-legend">
        {segments.map(segment => (
          <span key={segment.label}>
            <i style={{ background: segment.color }} />
            {segment.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function CacheMiniChart({ call }: { call: CallRow }) {
  const bars = [
    { label: 'Cache', value: Math.min(Math.max(call.cachedPct, 0), 100), color: '#2563eb' },
    { label: 'Fresh', value: Math.min(Math.max(100 - call.cachedPct, 0), 100), color: '#f59e0b' },
    { label: 'Output', value: Math.min(Math.max(call.output / Math.max(call.totalTokens, 1) * 100, 0), 100), color: '#059669' },
  ];

  return (
    <div className="cache-mini-card">
      <div>
        <strong>Cache delta readout</strong>
        <span>{cacheState(call)}</span>
      </div>
      <div className="cache-bars" aria-label="Cache delta readout">
        {bars.map(bar => (
          <span key={bar.label}>
            <i style={{ height: `${Math.max(bar.value, 4)}%`, background: bar.color }} />
            <em>{bar.label}</em>
          </span>
        ))}
      </div>
    </div>
  );
}

async function copyInvestigatorLink(call: CallRow, setCopyStatus: (status: string) => void) {
  try {
const url = new URL(window.location.href);
url.searchParams.set('view', 'call');
url.searchParams.set('record', call.id);
url.searchParams.set('return', 'calls');
const copied = await copyText(url.toString());
if (!copied) {
throw new Error('Clipboard unavailable');
}
setCopyStatus('Copied investigator link');
} catch {
    setCopyStatus('Copy unavailable in this browser');
  }
}
