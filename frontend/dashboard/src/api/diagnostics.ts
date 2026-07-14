import { usageRowToCall } from './client';
import { clearDiagnosticSnapshotCache } from './diagnosticSnapshots';
import type { CallRow, ContextRuntime, UsageRow } from './types';

export * from './diagnosticSnapshots';

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

type DiagnosticFactSourceDefinition = (typeof diagnosticFactSourceDefinitions)[number];
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

type DiagnosticFactCallsPayload = {
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
  cacheKey?: string;
  includeArchived?: boolean;
  signal?: AbortSignal;
  limit?: number;
  offset?: number;
  sort?: DiagnosticFactSortKey;
  direction?: DiagnosticSortDirection;
};

export type DiagnosticFactCallsOptions = {
  cacheKey?: string;
  includeArchived?: boolean;
  signal?: AbortSignal;
  limit?: number;
  offset?: number;
  sort?: DiagnosticFactCallSortKey;
  direction?: DiagnosticSortDirection;
};

const diagnosticFactsCache = new Map<string, Promise<DiagnosticFactsPayload> | DiagnosticFactsPayload>();
const diagnosticFactCallsCache = new Map<string, Promise<DiagnosticFactCallsResult> | DiagnosticFactCallsResult>();

export function clearDiagnosticApiCache(): void {
  clearDiagnosticSnapshotCache();
  diagnosticFactsCache.clear();
  diagnosticFactCallsCache.clear();
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
  const limit = Math.max(1, Math.round(options.limit ?? definition.limit));
  const offset = Math.max(0, Math.round(options.offset ?? 0));
  const load = async () => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      sort,
      direction,
    });
    appendBooleanParam(params, 'include_archived', options.includeArchived);
    const response = await fetch(`${definition.path}?${params.toString()}`, {
      headers: {
        Accept: 'application/json',
        'X-Codex-Usage-Token': runtime.apiToken,
      },
      cache: 'no-store',
      signal: options.signal,
    });
    return (await readJsonResponse(response, definition.title)) as DiagnosticFactsPayload;
  };
  if (options.signal) return load();
  return cachedRequest(
    diagnosticFactsCache,
    factSourceCacheKey(
      definition.key,
      runtime,
      limit,
      offset,
      sort,
      direction,
      options.cacheKey,
      options.includeArchived,
    ),
    load,
  );
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
  const load = async () => {
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
    });
    appendBooleanParam(params, 'include_archived', options.includeArchived);
    const response = await fetch(`/api/diagnostics/fact-calls?${params.toString()}`, {
      headers: {
        Accept: 'application/json',
        'X-Codex-Usage-Token': runtime.apiToken,
      },
      cache: 'no-store',
      signal: options.signal,
    });
    const payload = (await readJsonResponse(response, 'Diagnostic fact calls')) as DiagnosticFactCallsPayload;
    return {
      calls: (payload.rows ?? []).map((row, index) => usageRowToCall(row, index)),
      rawPayload: payload,
    };
  };
  if (options.signal) return load();
  return cachedRequest(
    diagnosticFactCallsCache,
    factCallsCacheKey(
      fact,
      runtime,
      limit,
      offset,
      sort,
      direction,
      options.cacheKey,
      options.includeArchived,
    ),
    load,
  );
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
  limit: number,
  offset: number,
  sort: DiagnosticFactSortKey,
  direction: DiagnosticSortDirection,
  sourceRevision = '',
  includeArchived?: boolean,
): string {
  return [
    'facts',
    sourceKey,
    runtimeCacheKey(runtime),
    sourceRevision,
    includeArchived ?? 'default',
    limit,
    offset,
    sort,
    direction,
  ].join(':');
}

export function normalizeDiagnosticFactSortKey(sort: DiagnosticFactSortKey): DiagnosticFactSortKey {
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
  sourceRevision = '',
  includeArchived?: boolean,
): string {
  return [
    'fact-calls',
    runtimeCacheKey(runtime),
    sourceRevision,
    includeArchived ?? 'default',
    String(fact.fact_type ?? ''),
    String(fact.fact_name ?? ''),
    limit,
    offset,
    sort,
    direction,
  ].join(':');
}

function appendBooleanParam(params: URLSearchParams, key: string, value: boolean | undefined): void {
  if (value !== undefined) params.set(key, String(value));
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
