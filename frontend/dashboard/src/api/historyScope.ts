import type { DashboardBootPayload } from './types';

export type PayloadHistoryScope = 'active' | 'all';

export function historyScopeFromPayload(
  payload: DashboardBootPayload | null,
  fallback: PayloadHistoryScope = 'active',
): PayloadHistoryScope {
  if (!payload) return fallback;
  if (typeof payload.include_archived === 'boolean') {
    return payload.include_archived ? 'all' : 'active';
  }
  if (payload.history_scope === 'all-history' || payload.history_scope === 'all') {
    return 'all';
  }
  if (payload.history_scope === 'active') return 'active';
  return fallback;
}
