import type { CallRow } from '../../api/types';
import type { ExploreCallsPage } from '../../data/contracts/explore';

export type ProgressiveThreadCallState = {
  expanded: boolean;
  enabled: boolean;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFetchNextPageError: boolean;
};

export function dedupeThreadCallPages(pages: ExploreCallsPage[], fallback: CallRow[]): CallRow[] {
  const source = pages.length ? pages.flatMap(page => page.rows) : fallback;
  const seen = new Set<string>();
  return source.filter(row => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}

export function shouldFetchNextThreadCallPage(state: ProgressiveThreadCallState): boolean {
  return state.expanded
    && state.enabled
    && state.hasNextPage
    && !state.isFetchingNextPage
    && !state.isFetchNextPageError;
}
