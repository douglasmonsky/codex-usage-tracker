import type { ColumnDef } from '@tanstack/react-table';

import type { CallRow, ThreadRow, WeeklyWindow } from '../../api/types';
import { formatCompact, formatNumber, money, pct } from './format';

export const callColumns: Array<ColumnDef<CallRow>> = [
  { accessorKey: 'time', header: 'Time' },
  { accessorKey: 'thread', header: 'Thread' },
  { accessorKey: 'model', header: 'Model' },
  {
    accessorKey: 'effort',
    header: 'Effort',
    cell: info => <span className={`pill effort-${String(info.getValue())}`}>{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'input',
    header: 'Input Tokens',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'output',
    header: 'Output Tokens',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachedPct',
    header: 'Cached %',
    cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cost',
    header: 'Est. Cost',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  { accessorKey: 'duration', header: 'Duration' },
  {
    accessorKey: 'fast',
    header: 'Fast',
    cell: info => <span className={info.getValue() ? 'status-badge green' : 'muted'}>{info.getValue() ? 'Yes' : '-'}</span>,
  },
];

export const threadColumns: Array<ColumnDef<ThreadRow>> = [
  { accessorKey: 'name', header: 'Thread' },
  {
    accessorKey: 'turns',
    header: 'Turns',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'totalTokens',
    header: 'Total Tokens',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cost',
    header: 'Est. Cost',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachePct',
    header: 'Cache %',
    cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'costPerCall',
    header: 'Cost / Call',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'coldResumeRisk',
    header: 'Cold Resume Risk',
    cell: info => <span className={`status-badge ${riskTone(String(info.getValue()))}`}>{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'productivity',
    header: 'Productivity',
    cell: info => <span className="score">{formatNumber(Number(info.getValue()))}</span>,
  },
];

export const weeklyColumns: Array<ColumnDef<WeeklyWindow>> = [
  { accessorKey: 'week', header: 'Week' },
  { accessorKey: 'plan', header: 'Plan' },
  {
    accessorKey: 'observedPct',
    header: 'Observed %',
    cell: info => <span className="num">{pct(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'credits',
    header: 'Credits',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'projected',
    header: 'Projected / Week',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    id: 'ci',
    header: '95% CI',
    cell: info => {
      const row = info.row.original;
      return (
        <span className="num">
          {formatNumber(row.ciLow)} - {formatNumber(row.ciHigh)}
        </span>
      );
    },
  },
  {
    accessorKey: 'confidence',
    header: 'Confidence',
    cell: info => <span className={`status-badge ${riskTone(String(info.getValue()))}`}>{String(info.getValue())}</span>,
  },
  { accessorKey: 'note', header: 'Notes' },
];

function riskTone(value: string): 'green' | 'orange' | 'red' | 'neutral' {
  if (value === 'High') {
    return 'red';
  }
  if (value === 'Medium') {
    return 'orange';
  }
  if (value === 'Low') {
    return 'green';
  }
  return 'neutral';
}
