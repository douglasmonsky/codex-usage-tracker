import type { CallRow } from '../../api/types';
import { rowMatchesQuery } from '../shared/filtering';

export function overviewCallsForQuery(calls: CallRow[], globalQuery = ''): CallRow[] {
  return calls.filter(call =>
    rowMatchesQuery([call.thread, call.model, call.effort, call.signal, call.recommendation], globalQuery),
  );
}
