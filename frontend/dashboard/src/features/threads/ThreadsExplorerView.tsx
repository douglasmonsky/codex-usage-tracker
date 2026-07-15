import type { ColumnDef, OnChangeFn, SortingState } from '@tanstack/react-table';
import { Download, RotateCcw, Search } from 'lucide-react';
import type { Dispatch, ReactNode, SetStateAction } from 'react';
import type { CallRow, ThreadRow } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import { StatusBadge } from '../../components/StatusBadge';
import { PageLoadProgress, SegmentedControl } from '../../design';
import { Visualization, type VisualizationSpecV1 } from '../../visualization';
import { EvidenceGrid } from '../explore/EvidenceGrid';
import { ExploreWorkspaceSwitcher } from '../explore/ExploreWorkspaceSwitcher';
import type { EvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { formatCompact, pct } from '../shared/format';
import { threadInvestigatorRowLabel } from '../shared/tables';
import { ThreadInspector } from './ThreadInspector';
import type { ThreadRiskFilter } from './threadFilterSummary';
import { threadsTablePageSize, type ThreadCallSortDirection, type ThreadCallSortKey } from './threadsUrlState';
import styles from './ThreadsPage.module.css';

export type ThreadEvidenceViewMode = 'table' | 'frontier' | 'lifecycle';

type ThreadsExplorerViewProps = {
  globalFilters?: ReactNode;
  localQuery: string;
  riskFilter: ThreadRiskFilter;
  exportDisabled: boolean;
  exportStatus: string;
  filterStatus: string;
  tableSubtitle: string;
  tableTitle: string;
  tableLabel: string;
  viewMode: ThreadEvidenceViewMode;
  focusedState: {
    isFetching: boolean;
    isFetchingNextPage: boolean;
    usingFocused: boolean;
    fallbackReason: string;
    error: string | null;
  };
  selectedCallsState: { isFetching: boolean; count: number; hydrated: boolean; error: string | null };
  displayedThreads: ThreadRow[];
  totalMatchedThreads: number;
  canLoadMoreThreads: boolean;
  columns: Array<ColumnDef<ThreadRow, unknown>>;
  sorting: SortingState;
  gridPreferences: EvidenceGridPreferences;
  selected: ThreadRow | null;
  frontierSpec: VisualizationSpecV1;
  lifecycleSpec: VisualizationSpecV1;
  inspector: {
    selected: ThreadRow | null;
    calls: CallRow[];
    allCalls: CallRow[];
    totalCallCount: number;
    hasMoreCalls: boolean;
    isFetchingMoreCalls: boolean;
    callSort: ThreadCallSortKey;
    callSortDirection: ThreadCallSortDirection;
    visibleCallCount: number;
    onVisibleCallCountChange: Dispatch<SetStateAction<number>>;
    onLoadMoreCalls(): void;
  };
  onWorkspaceChange(workspace: 'calls' | 'tools' | 'files'): void;
  onExport(): void;
  onClearFilters(): void;
  onLocalQueryChange(value: string): void;
  onRiskFilterChange(value: string): void;
  onViewModeChange: Dispatch<SetStateAction<ThreadEvidenceViewMode>>;
  onSortingChange: OnChangeFn<SortingState>;
  onSelectThread(threadName: string): void;
  onActivateThread(thread: ThreadRow): void;
  onLoadMoreThreads(): void;
  onCallSortChange(value: string): void;
  onCallSortDirectionChange(value: string): void;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
};

export function ThreadsExplorerView({
  globalFilters,
  localQuery,
  riskFilter,
  exportDisabled,
  exportStatus,
  filterStatus,
  tableSubtitle,
  tableTitle,
  tableLabel,
  viewMode,
  focusedState,
  selectedCallsState,
  displayedThreads,
  totalMatchedThreads,
  canLoadMoreThreads,
  columns,
  sorting,
  gridPreferences,
  selected,
  frontierSpec,
  lifecycleSpec,
  inspector,
  onWorkspaceChange,
  onExport,
  onClearFilters,
  onLocalQueryChange,
  onRiskFilterChange,
  onViewModeChange,
  onSortingChange,
  onSelectThread,
  onActivateThread,
  onLoadMoreThreads,
  onCallSortChange,
  onCallSortDirectionChange,
  onOpenInvestigator,
  onCopyCallLink,
}: ThreadsExplorerViewProps) {
  const i18n = useShellI18n();
  return (
    <div className={`${styles.page} page-grid`}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Evidence explorer</p>
          <h1>Threads</h1>
          <p>Compare work units, follow lifecycle pressure, and open supporting calls without leaving the evidence surface.</p>
        </div>
        <div className={styles.headerActions}>
          <ExploreWorkspaceSwitcher current="threads" onValueChange={workspace => {
            if (workspace !== 'threads') onWorkspaceChange(workspace);
          }} />
          <button className="toolbar-button" type="button" onClick={onExport} disabled={exportDisabled}>
            <Download size={16} />
            Export thread calls
          </button>
          <button className="toolbar-button" type="button" aria-label="Reset thread view" onClick={onClearFilters}>
            <RotateCcw size={16} />
            Reset view
          </button>
        </div>
      </header>
      <PageLoadProgress
        active={focusedState.isFetching || selectedCallsState.isFetching}
        completed={Number(focusedState.usingFocused) + Number(selectedCallsState.hydrated)}
        total={2}
        label="Loading thread summaries and selected calls"
        error={focusedState.error ?? selectedCallsState.error}
        updating={focusedState.usingFocused || selectedCallsState.hydrated}
      />
      {globalFilters}
      <section className={styles.queryBar} aria-label="Thread filters">
        <label className="search-box">
          <span className="sr-only">Search threads</span>
          <Search size={16} aria-hidden="true" />
          <input
            value={localQuery}
            onChange={event => onLocalQueryChange(event.target.value)}
            placeholder="Search threads, risks, token totals..."
          />
        </label>
        <label className="filter-field">
          <span>Cold risk</span>
          <select value={riskFilter} onChange={event => onRiskFilterChange(event.target.value)}>
            <option value="all">All risks</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </label>
      </section>
      <div className={styles.tableHeading}>
        <div>
          <h2>{tableTitle}</h2>
          <p>{exportStatus || filterStatus || tableSubtitle}</p>
        </div>
        <div className={styles.tableActions}>
          <SegmentedControl
            label="Thread evidence view"
            value={viewMode}
            onValueChange={onViewModeChange}
            options={[
              { value: 'table', label: i18n.translateText('Table') },
              { value: 'frontier', label: 'Cache frontier' },
              { value: 'lifecycle', label: i18n.translateText('Lifecycle') },
            ]}
          />
          <StatusBadge
            label={focusedThreadsStatus(
              focusedState.isFetching,
              focusedState.usingFocused,
              focusedState.fallbackReason,
            )}
            tone={focusedState.usingFocused ? 'green' : 'blue'}
          />
          <StatusBadge
            label={selectedCallsState.isFetching
              ? 'Updating thread calls'
              : `${selectedCallsState.count.toLocaleString()} selected calls`}
            tone={selectedCallsState.hydrated ? 'green' : 'blue'}
          />
        </div>
      </div>
      <div className={styles.splitWorkspace}>
        <section className={styles.evidenceSurface} aria-label="Thread evidence">
          {viewMode === 'table' ? (
            <>
              <EvidenceGrid
                ariaLabel={tableLabel}
                columns={columns}
                data={displayedThreads}
                identityColumnId="name"
                lockedColumnIds={['investigate']}
                getRowId={thread => thread.name}
                mobile={{
                  primary: thread => thread.name,
                  secondary: thread => i18n.translateText(`${thread.turns} calls · ${formatCompact(thread.totalTokens)} tokens · ${pct(thread.cachePct)} cache`),
                  actionLabel: thread => threadInvestigatorRowLabel(thread),
                }}
                sorting={sorting}
                onSortingChange={onSortingChange}
                manualSorting
                columnVisibility={gridPreferences.columnVisibility}
                onColumnVisibilityChange={gridPreferences.setColumnVisibility}
                density={gridPreferences.density}
                onDensityChange={gridPreferences.setDensity}
                onRestoreDefaults={gridPreferences.restoreDefaults}
                selectedRowId={selected?.name}
                onRowSelect={thread => onSelectThread(thread.name)}
                onRowActivate={onActivateThread}
                viewportHeight={560}
              />
              <div className={styles.gridFooter} aria-live="polite">
                <span>
                  {i18n.translateText(`${displayedThreads.length.toLocaleString()} loaded / ${totalMatchedThreads.toLocaleString()} matched`)}
                </span>
                {canLoadMoreThreads ? (
                  <button
                    className="toolbar-button"
                    type="button"
                    onClick={onLoadMoreThreads}
                    disabled={focusedState.isFetchingNextPage}
                  >
                    {focusedState.isFetchingNextPage
                      ? 'Loading more...'
                      : `Load ${threadsTablePageSize.toLocaleString()} more`}
                  </button>
                ) : null}
              </div>
            </>
          ) : null}
          {viewMode === 'frontier' ? (
            <Visualization spec={frontierSpec} height={520} onSelectionChange={onSelectThread} />
          ) : null}
          {viewMode === 'lifecycle' ? (
            <Visualization spec={lifecycleSpec} height={520} onSelectionChange={onOpenInvestigator} />
          ) : null}
        </section>
        <ThreadInspector
          {...inspector}
          onCallSortChange={onCallSortChange}
          onCallSortDirectionChange={onCallSortDirectionChange}
          onOpenInvestigator={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
        />
      </div>
    </div>
  );
}

function focusedThreadsStatus(isFetching: boolean, usingFocused: boolean, fallbackReason: string): string {
  if (isFetching && usingFocused) return 'Updating focused threads';
  if (isFetching) return 'Loading focused threads';
  if (usingFocused) return 'Focused paged API';
  return fallbackReason || 'Stored snapshot';
}
