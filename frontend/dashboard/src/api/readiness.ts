import type { ContextRuntime, HomeStatusPayload } from './types';

export async function loadHomeStatus(
  runtime: ContextRuntime,
  signal?: AbortSignal,
): Promise<HomeStatusPayload> {
  if (runtime.fileMode || !runtime.apiToken) {
    throw new Error('Home status requires the localhost dashboard server.');
  }
  const response = await fetch('/api/status?include_archived=false', {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    signal,
  });
  const payload = await response.json() as HomeStatusPayload & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error || `Home status request failed (${response.status})`);
  }
  if (
    payload.schema !== 'codex-usage-tracker-status-v1'
    || payload.home_summary?.schema !== 'codex-usage-tracker-home-summary-v1'
  ) {
    throw new Error('Home status returned an unsupported schema.');
  }
  return payload;
}
