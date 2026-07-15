import type {
  ContextRuntime,
} from './types';
import type {
  AllowanceAnalysisJobPayload,
  AllowanceAnalysisPayload,
  AllowanceEvidencePayload,
  AllowanceSeriesPayload,
  AllowanceStatusPayload,
  AllowanceWindowKindV2,
} from './allowanceIntelligenceTypes';

export type AllowanceSeriesRequest = {
  rangePreset?: '24h' | '7d' | '8w' | '6m' | 'all' | 'custom';
  startAt?: string;
  endAt?: string;
  granularity?: 'auto' | 'raw' | 'hour' | 'day' | 'week' | 'month' | 'cycle';
  windowKind?: AllowanceWindowKindV2;
  cohortId?: string;
  includeArchived?: boolean;
};

export type AllowanceEvidenceRequest = {
  limit?: number;
  before?: string;
  order?: 'asc' | 'desc';
  windowKind?: AllowanceWindowKindV2;
  cohortId?: string;
  startAt?: string;
  endAt?: string;
  includeArchived?: boolean;
  privacyMode?: 'strict' | 'normal' | 'local';
};

export type AllowanceAnalysisRequest = {
  windowKind?: 'weekly';
  cohortId?: string;
  forecastHorizon?: number;
  includeArchived?: boolean;
  minCyclesPerSide?: number;
  permutationCount?: number;
};

export async function loadAllowanceStatus(
  runtime: ContextRuntime,
  options: { includeArchived?: boolean; sinceRevision?: string } = {},
  signal?: AbortSignal,
): Promise<AllowanceStatusPayload> {
  const params = new URLSearchParams();
  appendBoolean(params, 'include_archived', options.includeArchived);
  appendValue(params, 'since_revision', options.sinceRevision);
  return fetchAllowance(runtime, '/api/allowance/status', params, 'GET',
    'codex-usage-tracker-allowance-status-v2', 'Allowance status', signal);
}

export async function loadAllowanceSeries(
  runtime: ContextRuntime,
  options: AllowanceSeriesRequest = {},
  signal?: AbortSignal,
): Promise<AllowanceSeriesPayload> {
  const rangePreset = options.rangePreset ?? '7d';
  if (rangePreset === 'custom' && (!options.startAt || !options.endAt)) {
    throw new Error('Custom allowance ranges require startAt and endAt');
  }
  const params = new URLSearchParams({
    range_preset: rangePreset,
    granularity: options.granularity ?? 'auto',
    window_kind: options.windowKind ?? 'weekly',
  });
  appendValue(params, 'start_at', options.startAt);
  appendValue(params, 'end_at', options.endAt);
  appendValue(params, 'cohort_id', options.cohortId);
  appendBoolean(params, 'include_archived', options.includeArchived);
  return fetchAllowance(runtime, '/api/allowance/series', params, 'GET',
    'codex-usage-tracker-allowance-series-v2', 'Allowance series', signal);
}

export async function loadAllowanceEvidence(
  runtime: ContextRuntime,
  options: AllowanceEvidenceRequest = {},
  signal?: AbortSignal,
): Promise<AllowanceEvidencePayload> {
  const limit = options.limit ?? 50;
  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
    throw new Error('Allowance evidence limit must be between 1 and 500');
  }
  const params = new URLSearchParams({
    limit: String(limit),
    order: options.order ?? 'desc',
    privacy_mode: options.privacyMode ?? 'normal',
  });
  appendValue(params, 'before', options.before);
  appendValue(params, 'window_kind', options.windowKind);
  appendValue(params, 'cohort_id', options.cohortId);
  appendValue(params, 'start_at', options.startAt);
  appendValue(params, 'end_at', options.endAt);
  appendBoolean(params, 'include_archived', options.includeArchived);
  return fetchAllowance(runtime, '/api/allowance/evidence', params, 'GET',
    'codex-usage-tracker-allowance-evidence-v2', 'Allowance evidence', signal);
}

export async function loadAllowanceAnalysis(
  runtime: ContextRuntime,
  options: AllowanceAnalysisRequest = {},
  signal?: AbortSignal,
): Promise<AllowanceAnalysisPayload> {
  return fetchAllowance(runtime, '/api/allowance/analysis', analysisParams(options), 'GET',
    'codex-usage-tracker-allowance-analysis-v2', 'Allowance analysis', signal);
}

export async function startAllowanceAnalysis(
  runtime: ContextRuntime,
  options: AllowanceAnalysisRequest = {},
  signal?: AbortSignal,
): Promise<AllowanceAnalysisJobPayload> {
  return fetchAllowance(runtime, '/api/allowance/analysis/jobs', analysisParams(options), 'POST',
    'codex-usage-tracker-analysis-job-v1', 'Allowance analysis job', signal);
}

export async function loadAllowanceAnalysisJob(
  runtime: ContextRuntime,
  jobId: string,
  signal?: AbortSignal,
): Promise<AllowanceAnalysisJobPayload> {
  if (!jobId) throw new Error('Allowance analysis job id is required');
  return fetchAllowance(
    runtime,
    '/api/allowance/analysis/jobs',
    new URLSearchParams({ job_id: jobId }),
    'GET',
    'codex-usage-tracker-analysis-job-v1',
    'Allowance analysis job status',
    signal,
  );
}

function analysisParams(options: AllowanceAnalysisRequest): URLSearchParams {
  const horizon = options.forecastHorizon ?? 1;
  if (!Number.isInteger(horizon) || horizon < 1 || horizon > 12) {
    throw new Error('Allowance forecast horizon must be between 1 and 12');
  }
  const params = new URLSearchParams({
    window_kind: options.windowKind ?? 'weekly',
    cohort_id: options.cohortId ?? 'codex',
    forecast_horizon: String(horizon),
  });
  appendBoolean(params, 'include_archived', options.includeArchived);
  appendNumber(params, 'min_cycles_per_side', options.minCyclesPerSide);
  appendNumber(params, 'permutation_count', options.permutationCount);
  return params;
}

async function fetchAllowance<T extends { schema: string }>(
  runtime: ContextRuntime,
  path: string,
  params: URLSearchParams,
  method: 'GET' | 'POST',
  expectedSchema: T['schema'],
  label: string,
  signal?: AbortSignal,
): Promise<T> {
  ensureAllowanceRuntime(runtime);
  const query = params.toString();
  const response = await fetch(query ? `${path}?${query}` : path, {
    method,
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
    signal,
  });
  const payload = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(payload.error || `${label} request failed (${response.status})`);
  if (payload.schema !== expectedSchema) throw new Error(`${label} returned an unsupported schema`);
  return payload;
}

function appendValue(params: URLSearchParams, key: string, value: string | undefined) {
  if (value) params.set(key, value);
}

function appendBoolean(params: URLSearchParams, key: string, value: boolean | undefined) {
  if (value) params.set(key, '1');
}

function appendNumber(params: URLSearchParams, key: string, value: number | undefined) {
  if (value !== undefined) params.set(key, String(value));
}

function ensureAllowanceRuntime(runtime: ContextRuntime) {
  if (runtime.fileMode || !runtime.apiToken) {
    throw new Error('Allowance intelligence requires the localhost dashboard server');
  }
}
