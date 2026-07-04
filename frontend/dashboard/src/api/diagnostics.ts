import { usageRowToCall } from './client';
import type { CallRow, ContextRuntime, UsageRow } from './types';

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

export const diagnosticFactSourceDefinitions = [
  { key: 'facts', label: 'Top Facts', title: 'Top Diagnostic Facts', path: '/api/diagnostics/facts', limit: 50 },
  { key: 'tools', label: 'Tools', title: 'Tool and Function Activity', path: '/api/diagnostics/tools', limit: 25 },
  {
    key: 'compactions',
    label: 'Compactions',
    title: 'Compaction Activity',
    path: '/api/diagnostics/compactions',
    limit: 25,
  },
] as const;

export type DiagnosticFactSourceDefinition = (typeof diagnosticFactSourceDefinitions)[number];
export type DiagnosticFactSourceKey = DiagnosticFactSourceDefinition['key'];

export type DiagnosticFactRow = {
  fact_type?: string | null;
  fact_name?: string | null;
  fact_category?: string | null;
  occurrences?: number | null;
  associated_calls?: number | null;
  associated_input_tokens?: number | null;
  associated_cached_input_tokens?: number | null;
  associated_uncached_input_tokens?: number | null;
  associated_output_tokens?: number | null;
  associated_reasoning_output_tokens?: number | null;
  associated_total_tokens?: number | null;
  avg_cache_ratio?: number | null;
  largest_call_tokens?: number | null;
  largest_record_id?: string | null;
  latest_event_timestamp?: string | null;
  action_hint?: string | null;
};

export type DiagnosticFactsPayload = {
  schema?: string;
  view?: string;
  row_count?: number;
  total_matched_rows?: number;
  truncated?: boolean;
  raw_context_included?: boolean;
  rows?: DiagnosticFactRow[];
  notes?: string[];
};

export type DiagnosticFactCallsPayload = {
  schema?: string;
  view?: string;
  row_count?: number;
  total_matched_rows?: number;
  truncated?: boolean;
  raw_context_included?: boolean;
  rows?: UsageRow[];
  notes?: string[];
};

export type DiagnosticFactCallsResult = {
  calls: CallRow[];
  rawPayload: DiagnosticFactCallsPayload;
};

export type DiagnosticFactSortKey =
  | 'uncached'
  | 'total'
  | 'tokens'
  | 'calls'
  | 'cache'
  | 'latest'
  | 'time'
  | 'occurrences'
  | 'fact'
  | 'cached'
  | 'output'
  | 'largest';
export type DiagnosticFactCallSortKey =
  | 'tokens'
  | 'input'
  | 'cached'
  | 'uncached'
  | 'output'
  | 'reasoning'
  | 'cache'
  | 'time'
  | 'thread'
  | 'model'
  | 'effort';
export type DiagnosticSortDirection = 'asc' | 'desc';

export type DiagnosticFactsOptions = {
  sort?: DiagnosticFactSortKey;
  direction?: DiagnosticSortDirection;
};

export type DiagnosticFactCallsOptions = {
  limit?: number;
  offset?: number;
  sort?: DiagnosticFactCallSortKey;
  direction?: DiagnosticSortDirection;
};

const diagnosticSnapshotCache = new Map<string, Promise<DiagnosticSnapshotMap> | DiagnosticSnapshotMap>();
const diagnosticFactsCache = new Map<string, Promise<DiagnosticFactsPayload> | DiagnosticFactsPayload>();
const diagnosticFactCallsCache = new Map<string, Promise<DiagnosticFactCallsResult> | DiagnosticFactCallsResult>();
const diagnosticMergedFactCallsCache = new Map<string, DiagnosticFactCallsResult>();

export function clearDiagnosticApiCache(): void {
  diagnosticSnapshotCache.clear();
  diagnosticFactsCache.clear();
  diagnosticFactCallsCache.clear();
  diagnosticMergedFactCallsCache.clear();
}

export function cachedDiagnosticSnapshots(runtime: ContextRuntime): DiagnosticSnapshotMap | null {
  return resolvedCachedValue(diagnosticSnapshotCache, runtimeCacheKey(runtime));
}

export async function loadDiagnosticSnapshots(runtime: ContextRuntime): Promise<DiagnosticSnapshotMap> {
  ensureDiagnosticsRuntime(runtime);
  return cachedRequest(
    diagnosticSnapshotCache,
    runtimeCacheKey(runtime),
    async () => {
      const entries = await Promise.all(
        diagnosticSnapshotDefinitions.map(async definition => [
          definition.key,
          await readDiagnosticSnapshot(definition, runtime),
        ] as const),
      );
      return Object.fromEntries(entries) as DiagnosticSnapshotMap;
    },
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
  diagnosticSnapshotCache.set(runtimeCacheKey(runtime), sections);
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
  const cached = diagnosticSnapshotCache.get(cacheKey);
  const current = cached ? await Promise.resolve(cached) : {};
  diagnosticSnapshotCache.set(cacheKey, { ...current, [definition.key]: payload });
  return payload;
}

export function cachedDiagnosticFactSource(
  sourceKey: DiagnosticFactSourceKey,
  runtime: ContextRuntime,
  options: DiagnosticFactsOptions = {},
): DiagnosticFactsPayload | null {
  const definition = diagnosticFactSourceDefinitions.find(candidate => candidate.key === sourceKey) ?? diagnosticFactSourceDefinitions[0];
  const sort = normalizeDiagnosticFactSortKey(options.sort ?? 'uncached');
  const direction = options.direction ?? 'desc';
  return resolvedCachedValue(diagnosticFactsCache, factSourceCacheKey(definition.key, runtime, sort, direction));
}

export async function loadDiagnosticFactSource(
  sourceKey: DiagnosticFactSourceKey,
  runtime: ContextRuntime,
  options: DiagnosticFactsOptions = {},
): Promise<DiagnosticFactsPayload> {
  ensureDiagnosticsRuntime(runtime);
  const definition =
    diagnosticFactSourceDefinitions.find(candidate => candidate.key === sourceKey) ?? diagnosticFactSourceDefinitions[0];
  const sort = normalizeDiagnosticFactSortKey(options.sort ?? 'uncached');
  const direction = options.direction ?? 'desc';
  return cachedRequest(diagnosticFactsCache, factSourceCacheKey(definition.key, runtime, sort, direction), async () => {
    const params = new URLSearchParams({
      limit: String(definition.limit),
      sort,
      direction,
      _: String(Date.now()),
    });
    const response = await fetch(`${definition.path}?${params.toString()}`, {
      headers: {
        Accept: 'application/json',
        'X-Codex-Usage-Token': runtime.apiToken,
      },
      cache: 'no-store',
    });
    return (await readJsonResponse(response, definition.title)) as DiagnosticFactsPayload;
  });
}

export async function loadDiagnosticFacts(runtime: ContextRuntime): Promise<DiagnosticFactsPayload> {
  return loadDiagnosticFactSource('facts', runtime);
}

export function cachedDiagnosticFactCalls(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  options: DiagnosticFactCallsOptions = {},
): DiagnosticFactCallsResult | null {
  const factType = String(fact.fact_type ?? '');
  const factName = String(fact.fact_name ?? '');
  if (!factType || !factName) return null;
  const limit = Math.max(1, Math.round(options.limit ?? 8));
  const offset = Math.max(0, Math.round(options.offset ?? 0));
  const sort = options.sort ?? 'tokens';
  const direction = options.direction ?? 'desc';
  return resolvedCachedValue(diagnosticFactCallsCache, factCallsCacheKey(fact, runtime, limit, offset, sort, direction));
}

export function cachedMergedDiagnosticFactCalls(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  options: DiagnosticFactCallsOptions = {},
): DiagnosticFactCallsResult | null {
  const factType = String(fact.fact_type ?? '');
  const factName = String(fact.fact_name ?? '');
  if (!factType || !factName) return null;
  const limit = Math.max(1, Math.round(options.limit ?? 8));
  const sort = options.sort ?? 'tokens';
  const direction = options.direction ?? 'desc';
  return diagnosticMergedFactCallsCache.get(mergedFactCallsCacheKey(fact, runtime, limit, sort, direction)) ?? null;
}

export function rememberMergedDiagnosticFactCalls(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  result: DiagnosticFactCallsResult,
  options: DiagnosticFactCallsOptions = {},
): void {
  const factType = String(fact.fact_type ?? '');
  const factName = String(fact.fact_name ?? '');
  if (!factType || !factName) return;
  const limit = Math.max(1, Math.round(options.limit ?? 8));
  const sort = options.sort ?? 'tokens';
  const direction = options.direction ?? 'desc';
  diagnosticMergedFactCallsCache.set(mergedFactCallsCacheKey(fact, runtime, limit, sort, direction), result);
}

export async function loadDiagnosticFactCalls(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  options: DiagnosticFactCallsOptions = {},
): Promise<DiagnosticFactCallsResult> {
  ensureDiagnosticsRuntime(runtime);
  const limit = Math.max(1, Math.round(options.limit ?? 8));
  const offset = Math.max(0, Math.round(options.offset ?? 0));
  const sort = options.sort ?? 'tokens';
  const direction = options.direction ?? 'desc';
  return cachedRequest(diagnosticFactCallsCache, factCallsCacheKey(fact, runtime, limit, offset, sort, direction), async () => {
    const factType = String(fact.fact_type ?? '');
    const factName = String(fact.fact_name ?? '');
    if (!factType || !factName) {
      throw new Error('Diagnostic fact type and name are required.');
    }
    const params = new URLSearchParams({
      fact_type: factType,
      fact_name: factName,
      limit: String(limit),
      offset: String(offset),
      sort,
      direction,
      _: String(Date.now()),
    });
    const response = await fetch(`/api/diagnostics/fact-calls?${params.toString()}`, {
      headers: {
        Accept: 'application/json',
        'X-Codex-Usage-Token': runtime.apiToken,
      },
      cache: 'no-store',
    });
    const payload = (await readJsonResponse(response, 'Diagnostic fact calls')) as DiagnosticFactCallsPayload;
    return {
      calls: (payload.rows ?? []).map((row, index) => usageRowToCall(row, index)),
      rawPayload: payload,
    };
  });
}

function resolvedCachedValue<T>(cache: Map<string, Promise<T> | T>, key: string): T | null {
  const cached = cache.get(key);
  if (cached === undefined || isPromise(cached)) return null;
  return cached;
}

function isPromise<T>(value: Promise<T> | T): value is Promise<T> {
  return typeof (value as Promise<T>).then === 'function';
}

function cachedRequest<T>(cache: Map<string, Promise<T> | T>, key: string, load: () => Promise<T>): Promise<T> {
  const cached = cache.get(key);
  if (cached !== undefined) {
    return Promise.resolve(cached);
  }

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

function factSourceCacheKey(
  sourceKey: DiagnosticFactSourceKey,
  runtime: ContextRuntime,
  sort: DiagnosticFactSortKey,
  direction: DiagnosticSortDirection,
): string {
  return ['facts', sourceKey, runtimeCacheKey(runtime), sort, direction].join(':');
}

function normalizeDiagnosticFactSortKey(sort: DiagnosticFactSortKey): DiagnosticFactSortKey {
  if (sort === 'total') return 'tokens';
  if (sort === 'latest') return 'time';
  return sort;
}

function factCallsCacheKey(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  limit: number,
  offset: number,
  sort: DiagnosticFactCallSortKey,
  direction: DiagnosticSortDirection,
): string {
  return [
    'fact-calls',
    runtimeCacheKey(runtime),
    String(fact.fact_type ?? ''),
    String(fact.fact_name ?? ''),
    limit,
    offset,
    sort,
    direction,
  ].join(':');
}

function mergedFactCallsCacheKey(
  fact: DiagnosticFactRow,
  runtime: ContextRuntime,
  limit: number,
  sort: DiagnosticFactCallSortKey,
  direction: DiagnosticSortDirection,
): string {
  return [
    'fact-calls-merged',
    runtimeCacheKey(runtime),
    String(fact.fact_type ?? ''),
    String(fact.fact_name ?? ''),
    limit,
    sort,
    direction,
  ].join(':');
}

async function readDiagnosticSnapshot(
  definition: DiagnosticSnapshotDefinition,
  runtime: ContextRuntime,
): Promise<DiagnosticSnapshotPayload> {
  const response = await fetch(`${definition.path}?_=${Date.now()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  return (await readJsonResponse(response, definition.title)) as DiagnosticSnapshotPayload;
}

function ensureDiagnosticsRuntime(runtime: ContextRuntime): void {
  if (runtime.fileMode) {
    throw new Error('Diagnostic facts require localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Diagnostic facts require localhost dashboard API token.');
  }
}

async function readJsonResponse(response: Response, label: string): Promise<unknown> {
  if (!response.ok) {
    throw new Error(`${label} request failed with HTTP ${response.status}`);
  }
  const payload = (await response.json()) as { error?: string };
  if (payload.error) {
    throw new Error(payload.error);
  }
  return payload;
}
