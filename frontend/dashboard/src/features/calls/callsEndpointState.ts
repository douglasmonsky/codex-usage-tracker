import type { ContextRuntime } from '../../api/types';
import type { CallsApiSort, CallsQueryFilters } from '../../data/exploreQueries';
import { callsDateRange } from './callsFilterSort';
import type {
  CallsSortKey,
  ConfidenceFilter,
  SourceFilter,
  TimeFilter,
} from './callFilterSummary';

const apiSortByCallsSort: Partial<Record<CallsSortKey, CallsApiSort>> = {
  time: 'time',
  duration: 'duration',
  gap: 'gap',
  thread: 'thread',
  initiator: 'initiator',
  model: 'model',
  effort: 'effort',
  total: 'tokens',
  cached: 'cached',
  uncached: 'uncached',
  output: 'output',
  reasoning: 'reasoning',
  cache: 'cache',
};

export type CallsEndpointStateInput = {
  runtime: ContextRuntime;
  enabled: boolean;
  activePreset: string;
  sourceFilter: SourceFilter;
  sortKey: CallsSortKey;
  timeFilter: TimeFilter;
  dateStart: string;
  dateEnd: string;
  confidenceFilter: ConfidenceFilter;
  globalQuery: string;
  localQuery: string;
  modelFilter: string;
  effortFilter: string;
};

export type CallsEndpointState = {
  enabled: boolean;
  reason: string;
  sort: CallsApiSort;
  filters: CallsQueryFilters;
};

export function callsEndpointState(input: CallsEndpointStateInput): CallsEndpointState {
  const sort = apiSortByCallsSort[input.sortKey];
  const dateRange = callsDateRange(input.timeFilter, input.dateStart, input.dateEnd, new Date());
  const reason = endpointFallbackReason(input, sort, dateRange.invalid);
  return {
    enabled: !reason,
    reason,
    sort: sort ?? 'time',
    filters: {
      query: [input.globalQuery.trim(), input.localQuery.trim()].filter(Boolean).join(' '),
      model: input.modelFilter === 'all' ? undefined : input.modelFilter,
      effort: input.effortFilter === 'all' ? undefined : input.effortFilter,
      ...confidenceApiFilters(input.confidenceFilter),
      ...dateApiFilters(dateRange.start, dateRange.endExclusive),
    },
  };
}

function endpointFallbackReason(
  input: CallsEndpointStateInput,
  sort: CallsApiSort | undefined,
  invalidDateRange: boolean,
): string {
  if (!input.enabled || input.runtime.fileMode || !input.runtime.apiToken) return 'Stored snapshot';
  if (input.globalQuery.trim() && input.localQuery.trim()) return 'Multiple searches use loaded snapshot';
  if (input.activePreset) return 'Preset uses loaded snapshot';
  if (input.sourceFilter !== 'all') return 'Source filter uses loaded snapshot';
  if (!sort) return 'This sort uses loaded snapshot';
  if (invalidDateRange) return 'Invalid date range';
  return '';
}

function confidenceApiFilters(filter: ConfidenceFilter): Pick<CallsQueryFilters, 'pricingStatus' | 'creditConfidence'> {
  if (filter === 'cost-exact') return { pricingStatus: 'priced' };
  if (filter === 'cost-estimated') return { pricingStatus: 'estimated' };
  if (filter === 'cost-unpriced') return { pricingStatus: 'unpriced' };
  if (filter === 'credit-exact') return { creditConfidence: 'exact' };
  if (filter === 'credit-estimated') return { creditConfidence: 'estimated' };
  if (filter === 'credit-override') return { creditConfidence: 'user_override' };
  if (filter === 'credit-missing') return { creditConfidence: 'unpriced' };
  return {};
}

function dateApiFilters(start: Date | null, endExclusive: Date | null): Pick<CallsQueryFilters, 'since' | 'until'> {
  return {
    since: start?.toISOString(),
    until: endExclusive ? new Date(endExclusive.getTime() - 1).toISOString() : undefined,
  };
}
