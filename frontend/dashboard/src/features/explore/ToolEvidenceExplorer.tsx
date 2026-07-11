import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { Copy, Download, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  loadDiagnosticFactCalls,
  loadDiagnosticFactSource,
  type DiagnosticFactCallSortKey,
  type DiagnosticFactSortKey,
} from '../../api/diagnostics';
import type { CallRow, ContextRuntime } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { formatCompact, formatNumber, pct } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import { EvidenceGrid } from './EvidenceGrid';
import styles from './DiagnosticEvidenceExplorer.module.css';
import { toolEvidenceRows, type ToolEvidenceRow } from './diagnosticEvidence';
import { useEvidenceGridPreferences } from './useEvidenceGridPreferences';

const pageSize = 100;

const sortByColumn: Record<string, DiagnosticFactSortKey> = {
  name: 'fact',
  occurrences: 'occurrences',
  associatedCalls: 'calls',
  uncachedInputTokens: 'uncached',
  totalTokens: 'tokens',
  cachePct: 'cache',
  largestCallTokens: 'largest',
  latestEventTimestamp: 'time',
};

type ToolEvidenceExplorerProps = {
  contextRuntime: ContextRuntime;
  globalQuery: string;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
  sourceRevision: string;
  workspaceSwitcher: ReactNode;
};

export function ToolEvidenceExplorer({
  contextRuntime,
  globalQuery,
  onCopyCallLink,
  onOpenInvestigator,
  sourceRevision,
  workspaceSwitcher,
}: ToolEvidenceExplorerProps) {
  const [localQuery, setLocalQuery] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'uncachedInputTokens', desc: true }]);
  const [selectedId, setSelectedId] = useState('');
  const preferences = useEvidenceGridPreferences('codexUsageToolsEvidenceGrid', {
    density: 'compact',
    columnVisibility: {},
  });
  const canLoad = !contextRuntime.fileMode && Boolean(contextRuntime.apiToken);
  const sort = sortByColumn[sorting[0]?.id ?? ''] ?? 'uncached';
  const direction = sorting[0]?.desc === false ? 'asc' : 'desc';
  const query = useInfiniteQuery({
    queryKey: ['explore', 'tools', contextRuntime.apiToken, sourceRevision, sort, direction],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => loadDiagnosticFactSource('tools', contextRuntime, {
      limit: pageSize,
      offset: pageParam,
      sort,
      direction,
    }),
    getNextPageParam: (lastPage, pages) => {
      const loaded = pages.reduce((total, page) => total + (page.rows?.length ?? 0), 0);
      const matched = lastPage.total_matched_rows ?? loaded;
      return loaded < matched ? loaded : undefined;
    },
    enabled: canLoad,
    placeholderData: previous => previous,
  });
  const rows = useMemo(
    () => query.data?.pages.flatMap(page => toolEvidenceRows(page)) ?? [],
    [query.data],
  );
  const normalizedQuery = `${globalQuery} ${localQuery}`.trim().toLowerCase();
  const filteredRows = useMemo(
    () => normalizedQuery
      ? rows.filter(row => `${row.name} ${row.category} ${row.actionHint}`.toLowerCase().includes(normalizedQuery))
      : rows,
    [normalizedQuery, rows],
  );
  const selected = filteredRows.find(row => row.id === selectedId) ?? filteredRows[0] ?? null;
  const callsQuery = useQuery({
    queryKey: ['explore', 'tool-calls', contextRuntime.apiToken, sourceRevision, selected?.id],
    queryFn: () => loadDiagnosticFactCalls(selected!.source, contextRuntime, {
      limit: 25,
      sort: 'tokens' satisfies DiagnosticFactCallSortKey,
      direction: 'desc',
    }),
    enabled: canLoad && Boolean(selected),
    placeholderData: previous => previous,
  });
  const totalMatched = query.data?.pages.at(-1)?.total_matched_rows ?? rows.length;
  const columns = useMemo<Array<ColumnDef<ToolEvidenceRow, unknown>>>(() => [
    { accessorKey: 'name', header: 'Tool' },
    { accessorKey: 'category', header: 'Category' },
    { accessorKey: 'occurrences', header: 'Occurrences', cell: info => formatNumber(Number(info.getValue())) },
    { accessorKey: 'associatedCalls', header: 'Calls', cell: info => formatNumber(Number(info.getValue())) },
    { accessorKey: 'uncachedInputTokens', header: 'Uncached Input', cell: info => formatCompact(Number(info.getValue())) },
    { accessorKey: 'totalTokens', header: 'Total Tokens', cell: info => formatCompact(Number(info.getValue())) },
    { accessorKey: 'cachePct', header: 'Cache %', cell: info => pct(Number(info.getValue())) },
    { accessorKey: 'largestCallTokens', header: 'Largest Call', cell: info => formatCompact(Number(info.getValue())) },
    { accessorKey: 'latestEventTimestamp', header: 'Latest', cell: info => formatTimestamp(String(info.getValue())) },
    {
      id: 'actions',
      header: 'Investigate',
      enableSorting: false,
      cell: info => <RowActions row={info.row.original} onOpen={onOpenInvestigator} onCopy={onCopyCallLink} />,
    },
  ], [onCopyCallLink, onOpenInvestigator]);

  useEffect(() => {
    if (selected && selected.id !== selectedId) setSelectedId(selected.id);
  }, [selected, selectedId]);

  function exportRows() {
    downloadCsv(`codex-tool-evidence-${csvDateStamp()}.csv`, rowsToCsv(filteredRows, [
      { header: 'Tool', value: row => row.name },
      { header: 'Category', value: row => row.category },
      { header: 'Occurrences', value: row => row.occurrences },
      { header: 'Associated Calls', value: row => row.associatedCalls },
      { header: 'Uncached Input Tokens', value: row => row.uncachedInputTokens },
      { header: 'Total Tokens', value: row => row.totalTokens },
      { header: 'Cache Percent', value: row => row.cachePct },
    ]));
  }

  return (
    <div className={`${styles.page} page-grid`}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Evidence explorer</p>
          <h1>Tools</h1>
          <p>Rank tool and function activity by associated token pressure, then inspect the calls behind each pattern.</p>
        </div>
        <div className={styles.headerActions}>
          {workspaceSwitcher}
          <button className="toolbar-button" type="button" onClick={exportRows} disabled={!filteredRows.length}>
            <Download size={16} />Export
          </button>
        </div>
      </header>
      <section className={styles.queryBar} aria-label="Tool filters">
        <label className="search-box">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Search tool evidence</span>
          <input value={localQuery} onChange={event => setLocalQuery(event.target.value)} placeholder="Search tools, categories, and actions..." />
        </label>
      </section>
      <div className={styles.tableHeading}>
        <div><h2>Tool evidence</h2><p>{filteredRows.length.toLocaleString()} loaded / {totalMatched.toLocaleString()} matched</p></div>
        <StatusBadge label={toolStatus(canLoad, query.isFetching, Boolean(query.data), query.error)} tone={query.data ? 'green' : 'blue'} />
      </div>
      <div className={styles.splitWorkspace}>
        <main className={styles.evidenceSurface}>
          <EvidenceGrid
            ariaLabel="Tool evidence"
            columns={columns}
            data={filteredRows}
            identityColumnId="name"
            lockedColumnIds={['actions']}
            getRowId={row => row.id}
            mobile={{
              primary: row => row.name,
              secondary: row => `${formatCompact(row.uncachedInputTokens)} uncached · ${row.associatedCalls} calls · ${pct(row.cachePct)} cache`,
              actionLabel: row => `Inspect ${row.name} tool evidence`,
            }}
            sorting={sorting}
            onSortingChange={setSorting}
            manualSorting
            columnVisibility={preferences.columnVisibility}
            onColumnVisibilityChange={preferences.setColumnVisibility}
            density={preferences.density}
            onDensityChange={preferences.setDensity}
            onRestoreDefaults={preferences.restoreDefaults}
            selectedRowId={selected?.id}
            onRowSelect={row => setSelectedId(row.id)}
            onRowActivate={row => row.representativeRecordId && onOpenInvestigator(row.representativeRecordId)}
            selectOnHover
            viewportHeight={560}
            emptyLabel={canLoad ? 'No tool evidence matches the active filters.' : 'Tool evidence requires the localhost dashboard server.'}
          />
          <div className={styles.gridFooter} aria-live="polite">
            <span>{filteredRows.length.toLocaleString()} ranked tools</span>
            {query.hasNextPage ? (
              <button className="toolbar-button" type="button" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                {query.isFetchingNextPage ? 'Loading more...' : `Load ${pageSize} more`}
              </button>
            ) : null}
          </div>
        </main>
        <ToolInspector
          row={selected}
          calls={callsQuery.data?.calls ?? []}
          callsLoading={callsQuery.isFetching}
          onCopyCallLink={onCopyCallLink}
          onOpenInvestigator={onOpenInvestigator}
        />
      </div>
    </div>
  );
}

function ToolInspector({
  row,
  calls,
  callsLoading,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  row: ToolEvidenceRow | null;
  calls: CallRow[];
  callsLoading: boolean;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  if (!row) return <aside className="side-panel"><Panel title="Tool inspector" subtitle="No evidence selected"><p className="empty-state">Select a tool row to inspect its aggregate evidence.</p></Panel></aside>;
  return (
    <aside className="side-panel">
      <Panel title="Tool inspector" subtitle={row.name}>
        <div className={styles.metricGrid}>
          <Metric label="Occurrences" value={formatNumber(row.occurrences)} />
          <Metric label="Associated calls" value={formatNumber(row.associatedCalls)} />
          <Metric label="Uncached input" value={formatCompact(row.uncachedInputTokens)} />
          <Metric label="Total tokens" value={formatCompact(row.totalTokens)} />
          <Metric label="Cache reuse" value={pct(row.cachePct)} />
          <Metric label="Largest call" value={formatCompact(row.largestCallTokens)} />
        </div>
        {row.actionHint ? <p className={styles.actionHint}>{row.actionHint}</p> : null}
        <div className={styles.inspectorActions}>
          <button className="primary-button" type="button" disabled={!row.representativeRecordId} onClick={() => onOpenInvestigator(row.representativeRecordId)}><Search size={16} />Open largest call</button>
          <button className="toolbar-button" type="button" disabled={!row.representativeRecordId} onClick={() => onCopyCallLink(row.representativeRecordId)}><Copy size={16} />Copy link</button>
        </div>
        <div className={styles.callLedger}>
          <div className="section-heading compact"><h3>Supporting calls</h3><span>{callsLoading ? 'Loading...' : `${calls.length} loaded`}</span></div>
          {calls.length ? calls.map(call => (
            <button key={call.id} type="button" onClick={() => onOpenInvestigator(call.id)}>
              <strong>{call.thread}</strong><span>{call.model} · {formatCompact(call.totalTokens)} tokens · {pct(call.cachedPct)} cache</span>
            </button>
          )) : <p className="empty-state">No supporting call rows are loaded for this tool fact.</p>}
        </div>
      </Panel>
    </aside>
  );
}

function RowActions({ row, onOpen, onCopy }: { row: ToolEvidenceRow; onOpen: (id: string) => void; onCopy: (id: string) => void }) {
  return (
    <div className="table-action-group">
      <button className="table-action-button" type="button" aria-label={`Open largest call for ${row.name}`} disabled={!row.representativeRecordId} onKeyDown={stopRowActionKeyDown} onClick={event => { event.stopPropagation(); onOpen(row.representativeRecordId); }}><Search size={14} />Open</button>
      <button className="table-action-button" type="button" aria-label={`Copy largest call link for ${row.name}`} disabled={!row.representativeRecordId} onKeyDown={stopRowActionKeyDown} onClick={event => { event.stopPropagation(); onCopy(row.representativeRecordId); }}><Copy size={14} />Copy</button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <span><strong>{value}</strong>{label}</span>;
}

function toolStatus(canLoad: boolean, fetching: boolean, loaded: boolean, error: Error | null): string {
  if (!canLoad) return 'Local server required';
  if (fetching && loaded) return 'Updating tool facts';
  if (fetching) return 'Loading tool facts';
  if (error) return 'Tool facts unavailable';
  return loaded ? 'Focused diagnostic API' : 'No tool facts loaded';
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value || '-' : date.toLocaleString();
}
