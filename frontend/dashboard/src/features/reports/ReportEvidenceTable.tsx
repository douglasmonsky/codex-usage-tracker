import type { ColumnDef } from '@tanstack/react-table';
import { useMemo } from 'react';

import type { CallRow } from '../../api/types';
import { DataTable } from '../../components/DataTable';
import { formatCompact, money, pct } from '../shared/format';
import { callActionColumn, callInvestigatorRowLabel } from '../shared/tables';
import { callCredits } from './reportModel';

type ReportEvidenceTableProps = {
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function ReportEvidenceTable({ calls, onOpenInvestigator, onCopyCallLink }: ReportEvidenceTableProps) {
  const columns = useMemo<Array<ColumnDef<CallRow>>>(() => [
    { accessorKey: 'time', header: 'Time' },
    { accessorKey: 'thread', header: 'Thread' },
    { accessorKey: 'model', header: 'Model' },
    {
      accessorKey: 'effort',
      header: 'Effort',
      cell: info => <span className={`pill effort-${String(info.getValue())}`}>{String(info.getValue())}</span>,
    },
    {
      id: 'credits',
      header: 'Credits',
      cell: info => <span className="num">{formatCompact(callCredits(info.row.original))}</span>,
      sortingFn: (left, right) => callCredits(left.original) - callCredits(right.original),
    },
    {
      accessorKey: 'cost',
      header: 'Est. Cost',
      cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
    },
    {
      accessorKey: 'cachedPct',
      header: 'Cached %',
      cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
    },
    callActionColumn({ onOpenInvestigator, onCopyCallLink, labelPrefix: 'report side evidence call' }),
  ], [onCopyCallLink, onOpenInvestigator]);

  return (
    <DataTable
      columns={columns}
      data={calls}
      compact
      emptyLabel="No loaded aggregate calls match this selected report."
      getRowId={call => call.id}
      getRowActionLabel={call => callInvestigatorRowLabel(call, 'report side evidence call')}
      onRowActivate={call => onOpenInvestigator(call.id)}
      ariaLabel="Selected report evidence calls"
    />
  );
}
