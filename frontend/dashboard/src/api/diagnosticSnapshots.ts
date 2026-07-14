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

export async function refreshDiagnosticSnapshots(runtime: ContextRuntime): Promise<DiagnosticSnapshotMap> {
  ensureDiagnosticsRuntime(runtime);
  const response = await fetch(`/api/diagnostics/refresh?_=${Date.now()}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await readJsonResponse(response, 'Diagnostic snapshot refresh')) as {
    sections?: DiagnosticSnapshotMap;
  };
  const sections = payload.sections ?? {};
  snapshotCache.set(runtimeCacheKey(runtime), sections);
  for (const [key, section] of Object.entries(sections) as Array<[DiagnosticSnapshotKey, DiagnosticSnapshotPayload]>) {
    sectionCache.set(sectionCacheKey(key, runtime), section);
  }
  return sections;
}

export async function refreshDiagnosticSnapshot(
  definition: DiagnosticSnapshotDefinition,
  runtime: ContextRuntime,
): Promise<DiagnosticSnapshotPayload> {
  ensureDiagnosticsRuntime(runtime);
  const response = await fetch(`${definition.refreshPath}?_=${Date.now()}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await readJsonResponse(response, definition.title)) as DiagnosticSnapshotPayload;
  const cacheKey = runtimeCacheKey(runtime);
  const cached = snapshotCache.get(cacheKey);
  const current = cached ? await Promise.resolve(cached) : {};
  snapshotCache.set(cacheKey, { ...current, [definition.key]: payload });
  sectionCache.set(sectionCacheKey(definition.key, runtime), payload);
  return payload;
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
  const payload = (await response.json()) as { error?: string };
  if (payload.error) throw new Error(payload.error);
  return payload;
}
