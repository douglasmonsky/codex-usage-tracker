import { useQuery } from '@tanstack/react-query';
import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { Copy, Download, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { loadDiagnosticSnapshot } from '../../api/diagnostics';
import type { ContextRuntime } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { formatCompact, formatNumber } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import styles from './DiagnosticEvidenceExplorer.module.css';
import { EvidenceGrid } from './EvidenceGrid';
import { fileEvidenceRows, type FileEvidenceRow } from './diagnosticEvidence';
import { useEvidenceGridPreferences } from './useEvidenceGridPreferences';

type FileEvidenceExplorerProps = {
  contextRuntime: ContextRuntime;
  globalQuery: string;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
  sourceRevision: string;
  workspaceSwitcher: ReactNode;
};

export function FileEvidenceExplorer({
  contextRuntime,
  globalQuery,
  onCopyCallLink,
  onOpenInvestigator,
  sourceRevision,
  workspaceSwitcher,
}: FileEvidenceExplorerProps) {
  const [localQuery, setLocalQuery] = useState('');
  const [sorting, setSorting] = useState<SortingState>([{ id: 'allocatedOutputTokens', desc: true }]);
  const [selectedId, setSelectedId] = useState('');
  const preferences = useEvidenceGridPreferences('codexUsageFilesEvidenceGrid', {
    density: 'compact',
    columnVisibility: {},
  });
  const canLoad = !contextRuntime.fileMode && Boolean(contextRuntime.apiToken);
  const readsQuery = useQuery({
    queryKey: ['explore', 'file-reads', contextRuntime.apiToken, sourceRevision],
    queryFn: () => loadDiagnosticSnapshot('fileReads', contextRuntime),
    enabled: canLoad,
    placeholderData: previous => previous,
  });
  const modificationsQuery = useQuery({
    queryKey: ['explore', 'file-modifications', contextRuntime.apiToken, sourceRevision],
    queryFn: () => loadDiagnosticSnapshot('fileModifications', contextRuntime),
    enabled: canLoad,
    placeholderData: previous => previous,
  });
  const rows = useMemo(
    () => fileEvidenceRows(readsQuery.data, modificationsQuery.data),
    [modificationsQuery.data, readsQuery.data],
  );
  const normalizedQuery = `${globalQuery} ${localQuery}`.trim().toLowerCase();
  const filteredRows = useMemo(
    () => normalizedQuery
      ? rows.filter(row => `${row.pathLabel} ${row.pathHash}`.toLowerCase().includes(normalizedQuery))
      : rows,
    [normalizedQuery, rows],
  );
  const selected = filteredRows.find(row => row.id === selectedId) ?? filteredRows[0] ?? null;
  const columns = useMemo<Array<ColumnDef<FileEvidenceRow, unknown>>>(() => [
    { accessorKey: 'pathLabel', header: 'File' },
    { accessorKey: 'pathHash', header: 'Path Hash' },
    { accessorKey: 'readEvents', header: 'Reads', cell: info => formatNumber(Number(info.getValue())) },
    { accessorKey: 'allocatedOutputTokens', header: 'Read Output', cell: info => formatCompact(Number(info.getValue())) },
    { accessorKey: 'modificationEvents', header: 'Modifications', cell: info => formatNumber(Number(info.getValue())) },
    {
      id: 'actions',
      header: 'Investigate',
      enableSorting: false,
      cell: info => <FileRowActions row={info.row.original} onOpen={onOpenInvestigator} onCopy={onCopyCallLink} />,
    },
  ], [onCopyCallLink, onOpenInvestigator]);

  useEffect(() => {
    if (selected && selected.id !== selectedId) setSelectedId(selected.id);
  }, [selected, selectedId]);

  function exportRows() {
    downloadCsv(`codex-file-evidence-${csvDateStamp()}.csv`, rowsToCsv(filteredRows, [
      { header: 'Path Label', value: row => row.pathLabel },
      { header: 'Path Hash', value: row => row.pathHash },
      { header: 'Read Events', value: row => row.readEvents },
      { header: 'Allocated Read Output Tokens', value: row => row.allocatedOutputTokens },
      { header: 'Modification Events', value: row => row.modificationEvents },
    ]));
  }

  const fetching = readsQuery.isFetching || modificationsQuery.isFetching;
  const error = readsQuery.error || modificationsQuery.error;
  const loaded = Boolean(readsQuery.data || modificationsQuery.data);

  return (
    <div className={`${styles.page} page-grid`}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Evidence explorer</p>
          <h1>Files</h1>
          <p>Find repeated reads and modifications using local aggregate path labels and stable path hashes.</p>
        </div>
        <div className={styles.headerActions}>
          {workspaceSwitcher}
          <button className="toolbar-button" type="button" onClick={exportRows} disabled={!filteredRows.length}>
            <Download size={16} />Export
          </button>
        </div>
      </header>
      <section className={styles.queryBar} aria-label="File filters">
        <label className="search-box">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Search file evidence</span>
          <input value={localQuery} onChange={event => setLocalQuery(event.target.value)} placeholder="Search path labels and exact path hashes..." />
        </label>
      </section>
      <div className={styles.tableHeading}>
        <div><h2>File evidence</h2><p>{filteredRows.length.toLocaleString()} aggregate paths from read and modification snapshots</p></div>
        <StatusBadge label={fileStatus(canLoad, fetching, loaded, error)} tone={loaded ? 'green' : 'blue'} />
      </div>
      <div className={styles.splitWorkspace}>
        <section className={styles.evidenceSurface} aria-label="File evidence results">
          <EvidenceGrid
            ariaLabel="File evidence"
            columns={columns}
            data={filteredRows}
            identityColumnId="pathLabel"
            lockedColumnIds={['actions']}
            getRowId={row => row.id}
            mobile={{
              primary: row => row.pathLabel,
              secondary: row => `${row.readEvents} reads · ${formatCompact(row.allocatedOutputTokens)} output · ${row.modificationEvents} modifications`,
              actionLabel: row => `Inspect ${row.pathLabel} file evidence`,
            }}
            sorting={sorting}
            onSortingChange={setSorting}
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
            emptyLabel={canLoad ? 'No file evidence is available in the stored diagnostic snapshots.' : 'File evidence requires the localhost dashboard server.'}
          />
          <div className={styles.gridFooter}><span>{filteredRows.length.toLocaleString()} ranked files</span></div>
        </section>
        <FileInspector row={selected} onCopyCallLink={onCopyCallLink} onOpenInvestigator={onOpenInvestigator} />
      </div>
    </div>
  );
}

function FileInspector({
  row,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  row: FileEvidenceRow | null;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  if (!row) return <aside className="side-panel"><Panel title="File inspector" subtitle="No evidence selected"><p className="empty-state">Select a file row to inspect its aggregate activity.</p></Panel></aside>;
  return (
    <aside className="side-panel">
      <Panel title="File inspector" subtitle={row.pathLabel}>
        <div className={styles.metricGrid}>
          <Metric label="Read events" value={formatNumber(row.readEvents)} />
          <Metric label="Read output" value={formatCompact(row.allocatedOutputTokens)} />
          <Metric label="Modifications" value={formatNumber(row.modificationEvents)} />
        </div>
        <dl className={styles.provenanceList}>
          <div><dt>Path hash</dt><dd>{row.pathHash || 'Unavailable'}</dd></div>
          <div><dt>Read evidence</dt><dd>{row.readRecordId || 'No representative call'}</dd></div>
          <div><dt>Modification evidence</dt><dd>{row.modificationRecordId || 'No representative call'}</dd></div>
        </dl>
        <p className={styles.actionHint}>Path hashes provide stable local identity for repeated rediscovery without placing raw file content in the aggregate response.</p>
        <div className={styles.inspectorActions}>
          <button className="primary-button" type="button" disabled={!row.representativeRecordId} onClick={() => onOpenInvestigator(row.representativeRecordId)}><Search size={16} />Open evidence call</button>
          <button className="toolbar-button" type="button" disabled={!row.representativeRecordId} onClick={() => onCopyCallLink(row.representativeRecordId)}><Copy size={16} />Copy link</button>
        </div>
      </Panel>
    </aside>
  );
}

function FileRowActions({ row, onOpen, onCopy }: { row: FileEvidenceRow; onOpen: (id: string) => void; onCopy: (id: string) => void }) {
  return (
    <div className="table-action-group">
      <button className="table-action-button" type="button" aria-label={`Open evidence call for ${row.pathLabel}`} disabled={!row.representativeRecordId} onKeyDown={stopRowActionKeyDown} onClick={event => { event.stopPropagation(); onOpen(row.representativeRecordId); }}><Search size={14} />Open</button>
      <button className="table-action-button" type="button" aria-label={`Copy evidence call link for ${row.pathLabel}`} disabled={!row.representativeRecordId} onKeyDown={stopRowActionKeyDown} onClick={event => { event.stopPropagation(); onCopy(row.representativeRecordId); }}><Copy size={14} />Copy</button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <span><strong>{value}</strong>{label}</span>;
}

function fileStatus(canLoad: boolean, fetching: boolean, loaded: boolean, error: Error | null): string {
  if (!canLoad) return 'Local server required';
  if (fetching && loaded) return 'Updating file snapshots';
  if (fetching) return 'Loading file snapshots';
  if (error) return 'File snapshots unavailable';
  return loaded ? 'Stored diagnostic snapshots' : 'No file snapshots loaded';
}
