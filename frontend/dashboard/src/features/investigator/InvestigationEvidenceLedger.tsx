import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { ArrowUpRight, Copy } from 'lucide-react';
import { useMemo, useState } from 'react';

import { IconButton, StatusBadge } from '../../design';
import { EvidenceGrid } from '../explore/EvidenceGrid';
import { useEvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { formatCompact } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import type { InvestigationEvidenceRow } from './investigationModel';

type InvestigationEvidenceLedgerProps = {
  findingTitle: string;
  rows: InvestigationEvidenceRow[];
  onOpenCall: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onOpenThread: (thread: string) => void;
};

export function InvestigationEvidenceLedger({
  findingTitle,
  rows,
  onOpenCall,
  onCopyCallLink,
  onOpenThread,
}: InvestigationEvidenceLedgerProps) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'tokens', desc: true }]);
  const preferences = useEvidenceGridPreferences('codexUsageInvestigationLedger', {
    density: 'compact',
    columnVisibility: { detail: false, source: false },
  });
  const columns = useMemo<Array<ColumnDef<InvestigationEvidenceRow, unknown>>>(() => [
    { accessorKey: 'thread', header: 'Thread', size: 220 },
    { accessorKey: 'pattern', header: 'Pattern', size: 160 },
    {
      accessorKey: 'events',
      header: 'Events',
      size: 90,
      cell: info => <span className="num">{Number(info.getValue()).toLocaleString()}</span>,
    },
    {
      accessorKey: 'tokens',
      header: 'Tokens',
      size: 110,
      cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
    },
    {
      accessorKey: 'confidence',
      header: 'Confidence',
      size: 120,
      cell: info => {
        const confidence = String(info.getValue()) as InvestigationEvidenceRow['confidence'];
        return <StatusBadge tone={confidence === 'high' ? 'positive' : confidence === 'medium' ? 'caution' : 'neutral'}>{confidence}</StatusBadge>;
      },
    },
    { accessorKey: 'value', header: 'Evidence', size: 220 },
    { accessorKey: 'detail', header: 'Detail', size: 210 },
    { accessorKey: 'source', header: 'Source', size: 190 },
    {
      id: 'open',
      header: 'Open',
      size: 116,
      enableSorting: false,
      cell: info => {
        const row = info.row.original;
        const label = row.recordId ? 'Open call' : row.thread !== 'Aggregate' ? 'Open thread' : 'No linked record';
        return (
          <div className="table-action-group">
            <IconButton
              disabled={!row.recordId && row.thread === 'Aggregate'}
              aria-label={`${label} for ${row.pattern}`}
              title={label}
              onKeyDown={stopRowActionKeyDown}
              onClick={event => {
                event.stopPropagation();
                activateEvidence(row, onOpenCall, onOpenThread);
              }}
            >
              <ArrowUpRight />
            </IconButton>
            {row.recordId ? (
              <IconButton
                aria-label={`Copy call link for ${row.pattern}`}
                title="Copy call link"
                onKeyDown={stopRowActionKeyDown}
                onClick={event => {
                  event.stopPropagation();
                  onCopyCallLink(row.recordId);
                }}
              >
                <Copy />
              </IconButton>
            ) : null}
          </div>
        );
      },
    },
  ], [onCopyCallLink, onOpenCall, onOpenThread]);

  return (
    <EvidenceGrid
      ariaLabel={`Evidence ledger for ${findingTitle}`}
      columns={columns}
      data={rows}
      identityColumnId="thread"
      lockedColumnIds={['open']}
      getRowId={row => row.id}
      mobile={{
        primary: row => row.thread,
        secondary: row => `${row.pattern} · ${row.events.toLocaleString()} events · ${formatCompact(row.tokens)} tokens`,
        actionLabel: row => row.recordId ? `Open call evidence for ${row.pattern}` : `Open thread evidence for ${row.pattern}`,
      }}
      sorting={sorting}
      onSortingChange={setSorting}
      columnVisibility={preferences.columnVisibility}
      onColumnVisibilityChange={preferences.setColumnVisibility}
      density={preferences.density}
      onDensityChange={preferences.setDensity}
      onRestoreDefaults={preferences.restoreDefaults}
      emptyLabel="This finding has no directly linked evidence rows at the current scope."
      onRowActivate={row => activateEvidence(row, onOpenCall, onOpenThread)}
      activateOnClick
      viewportHeight={Math.min(480, Math.max(180, rows.length * 46 + 50))}
    />
  );
}

function activateEvidence(
  row: InvestigationEvidenceRow,
  onOpenCall: (recordId: string) => void,
  onOpenThread: (thread: string) => void,
) {
  if (row.recordId) onOpenCall(row.recordId);
  else if (row.thread !== 'Aggregate') onOpenThread(row.thread);
}
