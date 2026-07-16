import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { Download } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import type { CallRow } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import { Button, StatusBadge } from '../../design';
import { EvidenceGrid } from '../explore/EvidenceGrid';
import { useEvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { formatCompact, formatNumber, pct } from '../shared/format';
import { callActionColumn, callColumns, callCsvColumns, callInvestigatorRowLabel } from '../shared/tables';
import { overviewCallsForQuery } from './overviewCalls';
import styles from './OverviewRecentCalls.module.css';

type OverviewRecentCallsProps = {
  calls: CallRow[];
  globalFilters?: ReactNode;
  globalQuery: string;
  loadedRowCount: number;
  totalAvailableRows: number;
  refreshing: boolean;
  canLoadMoreRows: boolean;
  onLoadMoreRows: () => void;
  onBrowseCalls: () => void;
  onOpenCall: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function OverviewRecentCalls(props: OverviewRecentCallsProps) {
  const [exportStatus, setExportStatus] = useState('');
  const shellI18n = useShellI18n();
  const loadMoreLabel = shellI18n.t('button.load_more', 'Load more');
  const visibleCalls = useMemo(
    () => overviewCallsForQuery(props.calls, props.globalQuery),
    [props.calls, props.globalQuery],
  );
  const columns = useMemo<Array<ColumnDef<CallRow, unknown>>>(() => [
    ...callColumns,
    callActionColumn({ onOpenInvestigator: props.onOpenCall, onCopyCallLink: props.onCopyCallLink }),
  ], [props.onCopyCallLink, props.onOpenCall]);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'time', desc: true }]);
  const gridPreferences = useEvidenceGridPreferences('codexUsageOverviewCallsEvidenceGrid', {
    density: 'compact',
    columnVisibility: {},
  });

  function exportCalls() {
    downloadCsv(`codex-overview-calls-${csvDateStamp()}.csv`, rowsToCsv(visibleCalls, callCsvColumns));
    setExportStatus(shellI18n.translateText(`Exported ${formatNumber(visibleCalls.length)} loaded calls`));
  }

  return (
    <section className={styles.section} aria-labelledby="overview-recent-calls-title">
      <div className={styles.header}>
        <div>
          <h2 id="overview-recent-calls-title">Calls</h2>
          <p>{shellI18n.translateText(`${formatNumber(visibleCalls.length)} matching calls with the same evidence fields as the Calls workspace.`)}</p>
        </div>
        <div className={styles.actions}>
          {exportStatus ? <StatusBadge tone="positive" role="status">{exportStatus}</StatusBadge> : null}
          <Button onClick={exportCalls} disabled={!visibleCalls.length}><Download /> Export</Button>
        </div>
      </div>
      {props.globalFilters}
      <div className={styles.tableSurface}>
        <EvidenceGrid
          ariaLabel="Overview calls"
          columns={columns}
          data={visibleCalls}
          identityColumnId="thread"
          lockedColumnIds={['investigate']}
          getRowId={call => call.id}
          mobile={{
            primary: call => call.thread,
            secondary: call => shellI18n.translateText(`${call.time} · ${call.model} · ${formatCompact(call.totalTokens)} tokens · ${pct(call.cachedPct)} cache`),
            actionLabel: call => callInvestigatorRowLabel(call),
          }}
          sorting={sorting}
          onSortingChange={setSorting}
          columnVisibility={gridPreferences.columnVisibility}
          onColumnVisibilityChange={gridPreferences.setColumnVisibility}
          density={gridPreferences.density}
          onDensityChange={gridPreferences.setDensity}
          onRestoreDefaults={gridPreferences.restoreDefaults}
          onRowActivate={call => props.onOpenCall(call.id)}
          activateOnClick
          viewportHeight={520}
          emptyLabel="No loaded calls match the current search."
        />
        <footer className={styles.footer}>
          <span>{shellI18n.translateText(`Loaded ${formatNumber(props.loadedRowCount)} of ${formatNumber(props.totalAvailableRows)} available calls`)}</span>
          <div className={styles.actions}>
            <Button aria-label="Load more recent calls" onClick={props.onLoadMoreRows} disabled={!props.canLoadMoreRows || props.refreshing}>{props.refreshing ? 'Loading...' : loadMoreLabel}</Button>
            <Button onClick={props.onBrowseCalls}>Browse all calls</Button>
          </div>
        </footer>
      </div>
    </section>
  );
}
