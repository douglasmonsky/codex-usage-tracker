import type { RefreshProgressPayload } from '../api/client';
import type { LoadWindow } from '../data/dataScope';
import type { HistoryScope } from './shellUrl';

export type RefreshOptions = {
  loadLimit?: number;
  loadWindow?: LoadWindow;
  historyScope?: HistoryScope;
  refresh?: boolean;
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function refreshProgressLabel(progress: RefreshProgressPayload, historyScope: HistoryScope): string {
  const scope = historyScope === 'all' ? 'all history' : 'active history';
  const message = progress.message || 'Refreshing usage index';
  const percent = typeof progress.percent === 'number' ? ` ${Math.round(progress.percent)}%` : '';
  return `${message}${percent} (${scope})`;
}
