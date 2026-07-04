import type { ThreadRow } from '../../api/types';
import { rowMatchesQuery } from '../shared/filtering';

export type ThreadRiskFilter = 'all' | 'High' | 'Medium' | 'Low';

const threadRiskFilterValues = new Set<string>(['all', 'High', 'Medium', 'Low']);

export type ThreadsFilterSummaryInput = {
  shownCount: number;
  totalCount: number;
  localQuery: string;
  globalQuery: string;
  riskFilter: ThreadRiskFilter;
  selectedThreadName: string | null;
};

export function buildThreadsFilterSummary(input: ThreadsFilterSummaryInput): string {
  const parts: string[] = [];
  const searchTerms = [input.localQuery.trim(), input.globalQuery.trim()].filter(Boolean);

  if (searchTerms.length) {
    parts.push(`Search ${searchTerms.map(term => `"${term}"`).join(' + ')}`);
  }
  if (input.riskFilter !== 'all') {
    parts.push(`Cold risk ${input.riskFilter}`);
  }
  if (input.selectedThreadName) {
    parts.push(`Selected ${input.selectedThreadName}`);
  }

  const base = `Showing ${input.shownCount.toLocaleString()} of ${input.totalCount.toLocaleString()} grouped threads`;
  return parts.length ? `${base} - Filters: ${parts.join('; ')}` : base;
}

export function threadMatchesFilters(
  thread: ThreadRow,
  {
    localQuery,
    globalQuery,
    riskFilter,
  }: Pick<ThreadsFilterSummaryInput, 'localQuery' | 'globalQuery' | 'riskFilter'>,
): boolean {
  if (riskFilter !== 'all' && thread.coldResumeRisk !== riskFilter) {
    return false;
  }
  const searchableValues = [thread.name, thread.coldResumeRisk, thread.totalTokens, thread.cost, thread.cachePct];
  return [globalQuery, localQuery].every(query => rowMatchesQuery(searchableValues, query));
}

export function normalizeThreadRiskFilter(value: string): ThreadRiskFilter {
  return threadRiskFilterValues.has(value) ? (value as ThreadRiskFilter) : 'all';
}
