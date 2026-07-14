import type { ContextRuntime } from './types';

export const diagnosticSnapshotDefinitions = [
  { key: 'overview', title: 'Overview', path: '/api/diagnostics/overview', refreshPath: '/api/diagnostics/overview/refresh' },
  { key: 'toolOutput', title: 'Tool Output', path: '/api/diagnostics/tool-output', refreshPath: '/api/diagnostics/tool-output/refresh' },
  { key: 'commands', title: 'Commands', path: '/api/diagnostics/commands', refreshPath: '/api/diagnostics/commands/refresh' },
  {
    key: 'gitInteractions',
    title: 'Git Interactions',
    path: '/api/diagnostics/git-interactions',
    refreshPath: '/api/diagnostics/git-interactions/refresh',
  },
  { key: 'fileReads', title: 'File Reads', path: '/api/diagnostics/file-reads', refreshPath: '/api/diagnostics/file-reads/refresh' },
  {
    key: 'fileModifications',
    title: 'File Modifications',
    path: '/api/diagnostics/file-modifications',
    refreshPath: '/api/diagnostics/file-modifications/refresh',
  },
  {
    key: 'readProductivity',
    title: 'Read Productivity',
    path: '/api/diagnostics/read-productivity',
    refreshPath: '/api/diagnostics/read-productivity/refresh',
  },
  { key: 'concentration', title: 'Concentration', path: '/api/diagnostics/concentration', refreshPath: '/api/diagnostics/concentration/refresh' },
  {
    key: 'guidedSummary',
    title: 'What Is Driving Usage?',
    path: '/api/diagnostics/guided-summary',
    refreshPath: '/api/diagnostics/guided-summary/refresh',
  },
  { key: 'usageDrain', title: 'Usage Drain', path: '/api/diagnostics/usage-drain', refreshPath: '/api/diagnostics/usage-drain/refresh' },
] as const;

export type DiagnosticSnapshotDefinition = (typeof diagnosticSnapshotDefinitions)[number];
export type DiagnosticSnapshotKey = DiagnosticSnapshotDefinition['key'];
export type DiagnosticSnapshotPayload = Record<string, unknown> & {
  schema?: string;
  section?: string;
  status?: string;
  refreshed?: boolean;
  raw_context_included?: boolean;
  snapshot?: {
    computed_at?: string;
    history_scope?: string;
    source_logs_scanned?: number;
    usage_rows_scanned?: number;
  } | null;
  notes?: string[];
};
export type DiagnosticSnapshotMap = Partial<Record<DiagnosticSnapshotKey, DiagnosticSnapshotPayload>>;

export type DiagnosticRefreshJob = {
  schema: 'codex-usage-tracker-analysis-job-v1';
  job_id: string;
  job_kind: 'diagnostic-refresh';
  status: 'pending' | 'running' | 'completed' | 'failed' | 'missing';
  stage: string;
  source_revision?: string;
  updated_at?: string;
  progress: {
    completed_units: number;
    total_units: number | null;
    percent: number | null;
    current_unit: string | null;
  };
  error?: { code?: string; type?: string } | null;
  next?: { action?: string; job_id?: string; poll_after_ms?: number };
};

export type DiagnosticRefreshOptions = {
  signal?: AbortSignal;
  onProgress?: (job: DiagnosticRefreshJob) => void;
  pollIntervalMs?: number;
};

export type DiagnosticSnapshotRequest = {
  cacheKey?: string;
  signal?: AbortSignal;
};

const snapshotCache = new Map<string, Promise<DiagnosticSnapshotMap> | DiagnosticSnapshotMap>();
const sectionCache = new Map<string, Promise<DiagnosticSnapshotPayload> | DiagnosticSnapshotPayload>();

export function clearDiagnosticSnapshotCache(): void {
  snapshotCache.clear();
  sectionCache.clear();
}

export async function loadDiagnosticSnapshot(
  key: DiagnosticSnapshotKey,
  runtime: ContextRuntime,
  options: DiagnosticSnapshotRequest = {},
): Promise<DiagnosticSnapshotPayload> {
  ensureDiagnosticsRuntime(runtime);
  const definition = snapshotDefinition(key);
  if (options.signal) {
    return readDiagnosticSnapshot(definition, runtime, options.signal);
  }
  return cachedRequest(
    sectionCache,
    sectionCacheKey(key, runtime, options.cacheKey),
    () => readDiagnosticSnapshot(definition, runtime),
  );
}

export async function refreshDiagnosticSnapshots(
  runtime: ContextRuntime,
  options: DiagnosticRefreshOptions = {},
): Promise<DiagnosticSnapshotMap> {
  ensureDiagnosticsRuntime(runtime);
  const response = await fetch(`/api/diagnostics/refresh?_=${Date.now()}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
    signal: options.signal,
  });
  const payload = (await readJsonResponse(response, 'Diagnostic snapshot refresh')) as {
    sections?: DiagnosticSnapshotMap;
  };
  const sections = payload.sections ?? (isDiagnosticRefreshJob(payload)
    ? await completedSnapshotMap(runtime, await pollDiagnosticRefresh(payload, runtime, options), options.signal)
    : {});
  snapshotCache.set(runtimeCacheKey(runtime), sections);
  for (const [key, section] of Object.entries(sections) as Array<[DiagnosticSnapshotKey, DiagnosticSnapshotPayload]>) {
    sectionCache.set(sectionCacheKey(key, runtime), section);
  }
  return sections;
}

export async function refreshDiagnosticSnapshot(
  definition: DiagnosticSnapshotDefinition,
  runtime: ContextRuntime,
  options: DiagnosticRefreshOptions = {},
): Promise<DiagnosticSnapshotPayload> {
  ensureDiagnosticsRuntime(runtime);
  const response = await fetch(`${definition.refreshPath}?_=${Date.now()}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
    signal: options.signal,
  });
  const started = await readJsonResponse(response, definition.title);
  const payload = isDiagnosticRefreshJob(started)
    ? await completedSnapshot(runtime, definition, await pollDiagnosticRefresh(started, runtime, options), options.signal)
    : started as DiagnosticSnapshotPayload;
  const cacheKey = runtimeCacheKey(runtime);
  const cached = snapshotCache.get(cacheKey);
  const current = cached ? await Promise.resolve(cached) : {};
  snapshotCache.set(cacheKey, { ...current, [definition.key]: payload });
  sectionCache.set(sectionCacheKey(definition.key, runtime), payload);
  return payload;
}

async function pollDiagnosticRefresh(
  started: DiagnosticRefreshJob,
  runtime: ContextRuntime,
  options: DiagnosticRefreshOptions,
): Promise<DiagnosticRefreshJob> {
  let job = started;
  options.onProgress?.(job);
  while (job.status === 'pending' || job.status === 'running') {
    const delayMs = options.pollIntervalMs ?? job.next?.poll_after_ms ?? 250;
    await waitForPoll(delayMs, options.signal);
    const params = new URLSearchParams({ job_id: job.job_id, _: String(Date.now()) });
    const response = await fetch(`/api/diagnostics/refresh/status?${params.toString()}`, {
      headers: {
        Accept: 'application/json',
        'X-Codex-Usage-Token': runtime.apiToken,
      },
      cache: 'no-store',
      signal: options.signal,
    });
    job = await readJsonResponse(response, 'Diagnostic refresh status') as DiagnosticRefreshJob;
    options.onProgress?.(job);
  }
  if (job.status !== 'completed') {
    throw new Error(`Diagnostic refresh failed: ${job.error?.code ?? job.status}`);
  }
  return job;
}

async function completedSnapshotMap(
  runtime: ContextRuntime,
  _job: DiagnosticRefreshJob,
  signal?: AbortSignal,
): Promise<DiagnosticSnapshotMap> {
  const rows = await Promise.all(diagnosticSnapshotDefinitions.map(async definition => [
    definition.key,
    await readDiagnosticSnapshot(definition, runtime, signal),
  ] as const));
  return Object.fromEntries(rows) as DiagnosticSnapshotMap;
}

async function completedSnapshot(
  runtime: ContextRuntime,
  definition: DiagnosticSnapshotDefinition,
  _job: DiagnosticRefreshJob,
  signal?: AbortSignal,
): Promise<DiagnosticSnapshotPayload> {
  return readDiagnosticSnapshot(definition, runtime, signal);
}

function isDiagnosticRefreshJob(payload: unknown): payload is DiagnosticRefreshJob {
  if (!payload || typeof payload !== 'object') return false;
  const candidate = payload as Partial<DiagnosticRefreshJob>;
  return candidate.schema === 'codex-usage-tracker-analysis-job-v1'
    && candidate.job_kind === 'diagnostic-refresh'
    && typeof candidate.job_id === 'string';
}

function waitForPoll(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
  if (milliseconds <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'));
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function cachedRequest<T>(cache: Map<string, Promise<T> | T>, key: string, load: () => Promise<T>): Promise<T> {
  const cached = cache.get(key);
  if (cached !== undefined) return Promise.resolve(cached);
  const promise = load()
    .then(value => {
      cache.set(key, value);
      return value;
    })
    .catch(error => {
      cache.delete(key);
      throw error;
    });
  cache.set(key, promise);
  return promise;
}

function runtimeCacheKey(runtime: ContextRuntime): string {
  return `${runtime.fileMode ? 'file' : 'live'}:${runtime.apiToken}`;
}

function sectionCacheKey(
  key: DiagnosticSnapshotKey,
  runtime: ContextRuntime,
  sourceRevision = '',
): string {
  return `snapshot:${runtimeCacheKey(runtime)}:${sourceRevision}:${key}`;
}

function snapshotDefinition(key: DiagnosticSnapshotKey): DiagnosticSnapshotDefinition {
  const definition = diagnosticSnapshotDefinitions.find(candidate => candidate.key === key);
  if (!definition) throw new Error(`Unknown diagnostic snapshot: ${key}`);
  return definition;
}

async function readDiagnosticSnapshot(
  definition: DiagnosticSnapshotDefinition,
  runtime: ContextRuntime,
  signal?: AbortSignal,
): Promise<DiagnosticSnapshotPayload> {
  const response = await fetch(`${definition.path}?_=${Date.now()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
    signal,
  });
  return (await readJsonResponse(response, definition.title)) as DiagnosticSnapshotPayload;
}

function ensureDiagnosticsRuntime(runtime: ContextRuntime): void {
  if (runtime.fileMode) throw new Error('Diagnostic facts require localhost dashboard server.');
  if (!runtime.apiToken) throw new Error('Diagnostic facts require localhost dashboard API token.');
}

async function readJsonResponse(response: Response, label: string): Promise<unknown> {
  if (!response.ok) throw new Error(`${label} request failed with HTTP ${response.status}`);
  const payload = (await response.json()) as { error?: unknown };
  if (typeof payload.error === 'string' && payload.error) throw new Error(payload.error);
  return payload;
}
