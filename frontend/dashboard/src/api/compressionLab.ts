import type { ContextRuntime } from './types';

const compressionApiSchema = 'codex-usage-tracker-compression-api-v1';
const activeStatuses = new Set(['pending', 'running']);
const successfulStatuses = new Set(['completed', 'completed_with_warnings']);

export type CompressionScopeRequest = {
  includeArchived: boolean;
  since?: string | null;
  until?: string | null;
  thread?: string | null;
  model?: string | null;
  effort?: string | null;
  detectorFamilies?: string[];
};

export type CompressionProgress = {
  percent: number;
  stage: string;
  current_detector: string | null;
  completed_detectors: number;
  total_detectors: number;
  records_examined: number;
  candidate_count: number;
};

export type CompressionApiPayload = {
  schema: 'codex-usage-tracker-compression-api-v1';
  kind: string;
  run_id: string | null;
  status: string;
  source_revision?: string;
  scope?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
  cache?: { reused?: boolean; mode?: string | null; request_reused?: string };
  timing?: Record<string, unknown>;
  progress?: CompressionProgress;
  profile?: CompressionProfile;
  warnings?: Array<Record<string, unknown>>;
  caveats?: string[];
  error?: { code?: string; message?: string } | null;
  next?: {
    tool?: string;
    arguments?: Record<string, unknown>;
    poll_after_ms?: number;
  };
};

export type CompressionProfile = {
  schema?: string;
  run_id?: string;
  status?: string;
  candidate_count?: number;
  observed_exposure?: Record<string, number>;
  portfolio_estimate?: { low?: number; likely?: number; high?: number };
  families?: Array<{
    family?: string;
    candidate_count?: number;
    adjusted_estimate?: { low?: number; likely?: number; high?: number };
  }>;
  coverage?: Record<string, unknown>;
  cache?: { mode?: string; reused?: boolean };
  duration_ms?: number;
  content_mode?: string;
  includes_indexed_content?: boolean;
  includes_raw_fragments?: boolean;
  warnings?: Array<Record<string, unknown>>;
  caveats?: string[];
};

export type CompressionRunOptions = {
  refresh?: boolean;
  signal?: AbortSignal;
  onProgress?: (payload: CompressionApiPayload) => void;
  pollIntervalMs?: number;
};

export async function loadCompressionProfile(
  runtime: ContextRuntime,
  scope: CompressionScopeRequest,
  options: { runId?: string; signal?: AbortSignal } = {},
): Promise<CompressionApiPayload> {
  ensureCompressionRuntime(runtime);
  const params = compressionScopeParams(scope);
  if (options.runId) params.set('run_id', options.runId);
  return fetchCompressionPayload(`/api/compression/profile?${params.toString()}`, runtime, {
    signal: options.signal,
  });
}

export async function runCompressionAnalysis(
  runtime: ContextRuntime,
  scope: CompressionScopeRequest,
  options: CompressionRunOptions = {},
): Promise<CompressionApiPayload> {
  ensureCompressionRuntime(runtime);
  const params = compressionScopeParams(scope);
  if (options.refresh) params.set('refresh', '1');
  let status = await fetchCompressionPayload(`/api/compression/start?${params.toString()}`, runtime, {
    method: 'POST',
    signal: options.signal,
  });
  options.onProgress?.(status);
  while (activeStatuses.has(status.status)) {
    const delay = options.pollIntervalMs ?? status.next?.poll_after_ms ?? 250;
    await waitForPoll(delay, options.signal);
    if (!status.run_id) throw new Error('Compression Lab status did not include a run ID.');
    const statusParams = new URLSearchParams({ run_id: status.run_id, _: String(Date.now()) });
    status = await fetchCompressionPayload(
      `/api/compression/status?${statusParams.toString()}`,
      runtime,
      { signal: options.signal },
    );
    options.onProgress?.(status);
  }
  if (!successfulStatuses.has(status.status) || !status.run_id) {
    throw new Error(status.error?.message ?? `Compression Lab run ended with ${status.status}.`);
  }
  return loadCompressionProfile(runtime, scope, {
    runId: status.run_id,
    signal: options.signal,
  });
}

function compressionScopeParams(scope: CompressionScopeRequest): URLSearchParams {
  const params = new URLSearchParams({
    include_archived: scope.includeArchived ? '1' : '0',
  });
  appendValue(params, 'since', scope.since);
  appendValue(params, 'until', scope.until);
  appendValue(params, 'thread', scope.thread);
  appendValue(params, 'model', scope.model);
  appendValue(params, 'effort', scope.effort);
  for (const family of scope.detectorFamilies ?? []) {
    if (family) params.append('detector_family', family);
  }
  params.set('_', String(Date.now()));
  return params;
}

function appendValue(params: URLSearchParams, key: string, value?: string | null): void {
  if (value) params.set(key, value);
}

async function fetchCompressionPayload(
  url: string,
  runtime: ContextRuntime,
  options: { method?: 'POST'; signal?: AbortSignal },
): Promise<CompressionApiPayload> {
  const response = await fetch(url, {
    method: options.method,
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
    signal: options.signal,
  });
  const payload = await response.json().catch(() => ({}));
  if (isCompressionPayload(payload)) return payload;
  if (!response.ok) {
    const message = payload && typeof payload === 'object' && typeof payload.error === 'string'
      ? payload.error
      : `Compression Lab request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  throw new Error('Compression Lab returned an unsupported schema.');
}

function isCompressionPayload(payload: unknown): payload is CompressionApiPayload {
  if (!payload || typeof payload !== 'object') return false;
  const candidate = payload as Partial<CompressionApiPayload>;
  return candidate.schema === compressionApiSchema
    && typeof candidate.kind === 'string'
    && typeof candidate.status === 'string';
}

function waitForPoll(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortReason(signal));
  if (milliseconds <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      globalThis.clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(signal ? abortReason(signal) : new DOMException('Aborted', 'AbortError'));
    };
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException('Aborted', 'AbortError');
}

function ensureCompressionRuntime(runtime: ContextRuntime): void {
  if (window.location.protocol === 'file:' || runtime.fileMode) {
    throw new Error('Compression Lab requires the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Compression Lab requires the localhost dashboard API token.');
  }
}
