import type { AllowanceDataState, AllowanceAnalysisJobPayload } from '../../api/types';

const FRESH_POLL_MS = 30_000;
const DEGRADED_POLL_MS = 60_000;
const MAX_BACKOFF_MS = 5 * 60_000;

export function allowanceStatusPollInterval(
  dataState: AllowanceDataState | undefined,
  failureCount: number,
  visible: boolean,
): number | false {
  if (!visible) return false;
  const base = dataState === 'fresh' || dataState === 'aging' ? FRESH_POLL_MS : DEGRADED_POLL_MS;
  return Math.min(base * 2 ** Math.max(0, failureCount), MAX_BACKOFF_MS);
}

export function allowanceAnalysisPollInterval(
  status: AllowanceAnalysisJobPayload['status'] | undefined,
  visible: boolean,
): 500 | false {
  if (!visible) return false;
  return status === 'pending' || status === 'queued' || status === 'running' ? 500 : false;
}

export function isPageVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}
