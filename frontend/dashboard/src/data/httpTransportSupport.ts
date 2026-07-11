import type { DashboardBootPayload } from '../api/types';

export function assertLiveUsagePayloadAvailable(
  currentPayload: DashboardBootPayload | null,
): asserts currentPayload is DashboardBootPayload {
  if (window.location.protocol === 'file:') {
    throw new Error('Live refresh requires the localhost dashboard server.');
  }
  if (!currentPayload?.api_token) {
    throw new Error('Live refresh requires localhost dashboard API token.');
  }
}

export function liveUsageHeaders(currentPayload: DashboardBootPayload): HeadersInit {
  return {
    Accept: 'application/json',
    'X-Codex-Usage-Token': currentPayload.api_token || '',
  };
}

export function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortReason(signal));
      return;
    }
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      window.clearTimeout(timeout);
      reject(abortReason(signal));
    }
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError';
}

function abortReason(signal?: AbortSignal): Error {
  return signal?.reason instanceof Error
    ? signal.reason
    : new DOMException('The request was cancelled.', 'AbortError');
}
