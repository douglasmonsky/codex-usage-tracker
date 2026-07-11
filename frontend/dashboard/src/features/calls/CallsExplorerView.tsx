import type { ColumnDef, OnChangeFn, SortingState } from '@tanstack/react-table';
import { BarChart3, PanelRightClose, PanelRightOpen } from 'lucide-react';
import type { ReactNode } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, ContextRuntime, DashboardModel } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { EvidenceGrid } from '../explore/EvidenceGrid';
import type { EvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { formatCompact, money, pct } from '../shared/format';
import { presetLabel } from '../shared/investigationPresets';
import { callInvestigatorRowLabel } from '../shared/tables';
import { CallInspector } from './CallInspector';
import { CallsFilterBar, type CallsFilterBarProps } from './CallsFilterBar';
import { CallsPageHeader } from './CallsPageHeader';
import { callsTablePageSize } from './useCallsExplorerControls';
import styles from './CallsPage.module.css';

type CallsExplorerViewProps = {
  model: DashboardModel;
  header: {
    workspaceSwitcher?: ReactNode;
    canExport: boolean;
    onExport(): void;
    onCopyView(): void;
    onRefresh(): void;
  };
  filters: CallsFilterBarProps;
  table: {
    activePreset: string;
    exportStatus: string;
    filterStatus: string;
    subtitle: string;
    focused: boolean;
    focusedReason: string;
    isFetching: boolean;
    isFetchingNextPage: boolean;
    hasNextPage: boolean;
    detailsExpanded: boolean;
    calls: CallRow[];
    totalMatchedCalls: number;
    columns: Array<ColumnDef<CallRow, unknown>>;
    sorting: SortingState;
    gridPreferences: EvidenceGridPreferences;
    selectedCall: CallRow | null;
    onSortingChange: OnChangeFn<SortingState>;
    onSelectCall(recordId: string): void;
    onLoadMore(): void;
    onToggleDetails(): void;
  };
  inspector: {
    contextRuntime: ContextRuntime;
    includeArchived: boolean;
    sourceRevision: string;
    hydrateThreadCalls: boolean;
    onContextApiEnabledChange(enabled: boolean): void;
    onOpenInvestigator(recordId: string): void;
    onCopyCallLink(recordId: string): void;
  };
};

export function CallsExplorerView({ model, header, filters, table, inspector }: CallsExplorerViewProps) {
  const shellI18n = useShellI18n();
  const modelCallsTitle = shellI18n.t('dashboard.model_calls', 'Model Calls');
  const modelCallsAriaLabel = shellI18n.t('dashboard.model_calls', 'Model calls');
  return (
    <div className={`${styles.page} page-grid`}>
      <CallsPageHeader {...header} />
      <CallsFilterBar {...filters} />
      <div className={styles.tableHeading}>
        <div>
          <h2>{modelCallsTitle}</h2>
          <p>{table.exportStatus || table.filterStatus || table.subtitle}</p>
        </div>
        <div className={styles.tableActions}>
          <StatusBadge
            label={focusedCallsStatus(table.isFetching, table.focused, table.focusedReason)}
            tone={table.focused ? 'green' : 'blue'}
          />
          <StatusBadge
            label={table.activePreset ? `Preset: ${presetLabel(table.activePreset)}` : 'Raw context gated'}
            tone={table.activePreset ? 'green' : 'blue'}
          />
          <button
            className="toolbar-button"
            type="button"
            aria-expanded={table.detailsExpanded}
            onClick={table.onToggleDetails}
          >
            {table.detailsExpanded ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            {table.detailsExpanded
              ? shellI18n.t('button.hide_details', 'Hide details')
              : shellI18n.t('dashboard.call_details', 'Call Details')}
          </button>
        </div>
      </div>
      <div className={table.detailsExpanded ? 'table-detail-layout' : 'table-detail-layout detail-collapsed'}>
        <div className={styles.gridColumn}>
          <EvidenceGrid
            ariaLabel={modelCallsAriaLabel}
            columns={table.columns}
            data={table.calls}
            identityColumnId="thread"
            lockedColumnIds={['investigate']}
            getRowId={call => call.id}
            mobile={{
              primary: call => call.thread,
              secondary: call => `${call.time} · ${call.model} · ${formatCompact(call.totalTokens)} tokens · ${pct(call.cachedPct)} cache`,
              actionLabel: call => callInvestigatorRowLabel(call),
            }}
            sorting={table.sorting}
            onSortingChange={table.onSortingChange}
            manualSorting
            columnVisibility={table.gridPreferences.columnVisibility}
            onColumnVisibilityChange={table.gridPreferences.setColumnVisibility}
            density={table.gridPreferences.density}
            onDensityChange={table.gridPreferences.setDensity}
            onRestoreDefaults={table.gridPreferences.restoreDefaults}
            selectedRowId={table.selectedCall?.id}
            onRowSelect={call => table.onSelectCall(call.id)}
            onRowActivate={call => inspector.onOpenInvestigator(call.id)}
            activateOnClick
            selectOnHover
            viewportHeight={560}
            emptyLabel="No rows match current filters."
          />
          <div className={styles.gridFooter} aria-live="polite">
            <span>{table.calls.length.toLocaleString()} loaded / {table.totalMatchedCalls.toLocaleString()} matched</span>
            {table.focused && table.hasNextPage ? (
              <button
                className="toolbar-button"
                type="button"
                onClick={table.onLoadMore}
                disabled={table.isFetchingNextPage}
              >
                {table.isFetchingNextPage
                  ? 'Loading more...'
                  : `Load ${callsTablePageSize.toLocaleString()} more`}
              </button>
            ) : null}
          </div>
        </div>
        {table.detailsExpanded ? (
          <CallInspector
            call={table.selectedCall}
            calls={model.calls}
            {...inspector}
          />
        ) : null}
      </div>
      <details className={styles.patternsDisclosure}>
        <summary><BarChart3 size={17} />Usage patterns</summary>
        <div className="dashboard-grid three">
          <Panel title="Usage Over Time" subtitle="Tokens">
            <LineChart series={model.tokenSeries} yLabel="Tokens" height={220} />
          </Panel>
          <Panel title="Cost by Model" subtitle="Estimated USD">
            <BarChart data={model.modelCosts} valueLabel={money} />
          </Panel>
          <Panel title="Cache Hit Rate Over Time" subtitle="Daily">
            <LineChart
              series={model.cacheSeries}
              yLabel="Cache %"
              height={220}
              valueFormatter={value => `${value}%`}
            />
          </Panel>
        </div>
      </details>
    </div>
  );
}

function focusedCallsStatus(isFetching: boolean, usingFocused: boolean, fallbackReason: string): string {
  if (isFetching && usingFocused) return 'Updating focused rows';
  if (isFetching) return 'Loading focused rows';
  if (usingFocused) return 'Focused paged API';
  return fallbackReason || 'Stored snapshot';
}
