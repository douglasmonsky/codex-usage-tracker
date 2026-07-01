import type { ColumnDef } from '@tanstack/react-table';
import type { CallRow, ThreadRow, WeeklyWindow } from '../../api/types';
import type { CsvColumn } from './exportCsv';
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
    accessorKey: 'signal',
    header: 'Signal',
    cell: info => <span className="status-badge blue">{String(info.getValue())}</span>,
  },
];

export const callCsvColumns: Array<CsvColumn<CallRow>> = [
  { header: 'Time', value: row => row.rawTime || row.time },
  { header: 'Thread', value: row => row.thread },
  { header: 'Model', value: row => row.model },
  { header: 'Effort', value: row => row.effort },
  { header: 'Input Tokens', value: row => row.input },
  { header: 'Output Tokens', value: row => row.output },
  { header: 'Reasoning Output Tokens', value: row => row.reasoningOutput },
  { header: 'Uncached Input Tokens', value: row => row.uncachedInput },
  { header: 'Cached Percent', value: row => row.cachedPct.toFixed(2) },
  { header: 'Estimated Cost USD', value: row => row.cost.toFixed(6) },
  { header: 'Usage Credits', value: row => row.credits.toFixed(6) },
  { header: 'Duration Seconds', value: row => row.durationSeconds },
  { header: 'Signal', value: row => row.signal },
  { header: 'Recommendation', value: row => row.recommendation },
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
    cell: info => <span className="score">{Number(info.getValue())}</span>,
  },
];

export const threadCsvColumns: Array<CsvColumn<ThreadRow>> = [
  { header: 'Thread', value: row => row.name },
  { header: 'Turns', value: row => row.turns },
  { header: 'Total Tokens', value: row => row.totalTokens },
  { header: 'Estimated Cost USD', value: row => row.cost.toFixed(6) },
  { header: 'Cache Percent', value: row => row.cachePct.toFixed(2) },
  { header: 'Cost Per Call USD', value: row => row.costPerCall.toFixed(6) },
  { header: 'Cold Resume Risk', value: row => row.coldResumeRisk },
  { header: 'Productivity', value: row => row.productivity },
];

export const weeklyWindowColumns: Array<ColumnDef<WeeklyWindow>> = [
  { accessorKey: 'week', header: 'Week' },
  { accessorKey: 'plan', header: 'Plan' },
  {
    accessorKey: 'credits',
    header: 'Credits',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'projected',
    header: 'Projected',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'confidence',
    header: 'Confidence',
    cell: info => <span className={`status-badge ${riskTone(String(info.getValue()))}`}>{String(info.getValue())}</span>,
  },
  { accessorKey: 'note', header: 'Note' },
];

export const weeklyColumns = weeklyWindowColumns;

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
