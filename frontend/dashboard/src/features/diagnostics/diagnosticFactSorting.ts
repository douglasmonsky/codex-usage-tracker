import type { DiagnosticFactRow } from '../../api/diagnostics';
import type { CallRow } from '../../api/types';

export type FactSortKey =
  | 'uncached'
  | 'total'
  | 'calls'
  | 'cache'
  | 'latest'
  | 'occurrences'
  | 'fact'
  | 'cached'
  | 'output'
  | 'largest';

export type FactCallSortKey =
  | 'tokens'
  | 'input'
  | 'cached'
  | 'uncached'
  | 'output'
  | 'reasoning'
  | 'cache'
  | 'time'
  | 'thread'
  | 'model'
  | 'effort';

export type SortDirection = 'asc' | 'desc';
export type FactSortState = { key: FactSortKey; direction: SortDirection };
export type FactCallSortState = { key: FactCallSortKey; direction: SortDirection };

export const factSortOptions: Array<{ key: FactSortKey; label: string }> = [
  { key: 'uncached', label: 'Uncached input' },
  { key: 'total', label: 'Total tokens' },
  { key: 'cached', label: 'Cached input' },
  { key: 'output', label: 'Output tokens' },
  { key: 'largest', label: 'Largest call' },
  { key: 'calls', label: 'Associated calls' },
  { key: 'cache', label: 'Cache %' },
  { key: 'latest', label: 'Latest time' },
  { key: 'occurrences', label: 'Occurrences' },
  { key: 'fact', label: 'Fact name' },
];

export const factCallSortOptions: Array<{ key: FactCallSortKey; label: string }> = [
  { key: 'tokens', label: 'Total tokens' },
  { key: 'input', label: 'Input tokens' },
  { key: 'cached', label: 'Cached input' },
  { key: 'uncached', label: 'Uncached input' },
  { key: 'output', label: 'Output tokens' },
  { key: 'reasoning', label: 'Reasoning tokens' },
  { key: 'cache', label: 'Cache %' },
  { key: 'time', label: 'Time' },
  { key: 'thread', label: 'Thread' },
  { key: 'model', label: 'Model' },
  { key: 'effort', label: 'Effort' },
];

export function numberField(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

export function defaultFactSortDirection(sortKey: FactSortKey): SortDirection {
  return sortKey === 'fact' ? 'asc' : 'desc';
}

export function defaultFactCallSortDirection(sortKey: FactCallSortKey): SortDirection {
  return sortKey === 'effort' || sortKey === 'model' || sortKey === 'thread' ? 'asc' : 'desc';
}

export function diagnosticFactCallSortDescription(sort: FactCallSortState): string {
  const label = factCallSortOptions.find(option => option.key === sort.key)?.label ?? 'Total tokens';
  return `sorted by ${label.toLowerCase()} ${sort.direction === 'desc' ? 'descending' : 'ascending'}`;
}

export function diagnosticFactSortDescription(sort: FactSortState): string {
  const label = factSortOptions.find(option => option.key === sort.key)?.label ?? 'Uncached input';
  return `sorted by ${label.toLowerCase()} ${sort.direction === 'desc' ? 'descending' : 'ascending'}`;
}

export function sortDiagnosticFacts(
  facts: DiagnosticFactRow[],
  sortKey: FactSortKey,
  direction: SortDirection,
): DiagnosticFactRow[] {
  const multiplier = direction === 'asc' ? 1 : -1;
  return [...facts].sort((left, right) => {
    const order = compareFactValue(left, right, sortKey) * multiplier;
    return order || compareFactValue(left, right, 'uncached') * -1 || compareFactValue(left, right, 'fact');
  });
}

function compareFactValue(left: DiagnosticFactRow, right: DiagnosticFactRow, sortKey: FactSortKey): number {
  if (sortKey === 'fact') {
    return `${left.fact_type ?? ''}/${left.fact_name ?? ''}`.localeCompare(`${right.fact_type ?? ''}/${right.fact_name ?? ''}`);
  }
  return factMetric(left, sortKey) - factMetric(right, sortKey);
}

function factMetric(fact: DiagnosticFactRow, sortKey: FactSortKey): number {
  if (sortKey === 'calls') return numberField(fact.associated_calls);
  if (sortKey === 'cached') return numberField(fact.associated_cached_input_tokens);
  if (sortKey === 'cache') return cachePctFromFact(fact);
  if (sortKey === 'largest') return numberField(fact.largest_call_tokens);
  if (sortKey === 'latest') return Date.parse(fact.latest_event_timestamp ?? '') || 0;
  if (sortKey === 'occurrences') return numberField(fact.occurrences);
  if (sortKey === 'output') return numberField(fact.associated_output_tokens);
  if (sortKey === 'total') return numberField(fact.associated_total_tokens);
  return numberField(fact.associated_uncached_input_tokens);
}

export function sortDiagnosticFactCalls(calls: CallRow[], sortKey: FactCallSortKey, direction: SortDirection): CallRow[] {
  const multiplier = direction === 'asc' ? 1 : -1;
  return [...calls].sort((left, right) => {
    const order = compareCallValue(left, right, sortKey) * multiplier;
    return order || compareCallValue(left, right, 'tokens') * -1 || left.id.localeCompare(right.id);
  });
}

function compareCallValue(left: CallRow, right: CallRow, sortKey: FactCallSortKey): number {
  if (sortKey === 'thread' || sortKey === 'model' || sortKey === 'effort') {
    return String(left[sortKey]).localeCompare(String(right[sortKey]));
  }
  return callMetric(left, sortKey) - callMetric(right, sortKey);
}

function callMetric(call: CallRow, sortKey: FactCallSortKey): number {
  if (sortKey === 'cache') return call.cachedPct;
  if (sortKey === 'cached') return call.cachedInput;
  if (sortKey === 'input') return call.input;
  if (sortKey === 'output') return call.output;
  if (sortKey === 'reasoning') return call.reasoningOutput;
  if (sortKey === 'time') return Date.parse(call.rawTime) || 0;
  if (sortKey === 'uncached') return call.uncachedInput;
  return call.totalTokens;
}

export function cachePctFromFact(fact: DiagnosticFactRow): number {
  const ratio = numberField(fact.avg_cache_ratio);
  return ratio <= 1 ? ratio * 100 : ratio;
}
