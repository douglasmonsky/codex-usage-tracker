import { fixtureModel } from '../test-fixtures/dashboardFixture';
import {
  abortableDelay,
  assertLiveUsagePayloadAvailable,
  isAbortError,
  liveUsageHeaders,
} from '../data/httpTransportSupport';
import { buildFindings, buildModelCosts, buildReports } from './modelInsights';
import { buildOverviewSeriesFromDailyValues } from './overviewSeries';
import { scopeSummaryFromBootPayload, summaryNumber } from './dashboardScopeSummary';
import { usageBillingFields, usageServiceTierFields } from './rowAnnotations';
import type { CallRow, ContextRuntime, DashboardBootPayload, DashboardModel, MetricCard, Series, ThreadRow, UsageRow, WeeklyWindow } from './types';
import {
  loadAllUsagePayloadPaged,
  requestScopedWindowPayload,
  type RefreshProgressPayload,
  type UsagePayloadRequest,
} from './usagePayloadWindow';

export type { RefreshProgressPayload, UsagePayloadRequest } from './usagePayloadWindow';

declare global {
  interface Window {
    __CODEX_USAGE_BOOT__?: DashboardBootPayload;
  }
}

export function readBootPayload(): DashboardBootPayload | null {
  if (window.__CODEX_USAGE_BOOT__) {
    return window.__CODEX_USAGE_BOOT__;
  }

  const embedded = document.getElementById('usage-data');
  if (!embedded?.textContent) {
    return null;
  }

  try {
    return JSON.parse(embedded.textContent) as DashboardBootPayload;
  } catch {
    return null;
  }
}

export async function loadUsagePayload(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest = {},
): Promise<DashboardBootPayload> {
  if (options.refresh && currentPayload?.refresh_jobs_available) {
    const refreshed = await tryRefreshUsageIndex(currentPayload, options);
    const nextOptions = { ...options, refresh: !refreshed };
    if (nextOptions.loadWindow && nextOptions.loadWindow !== 'rows') {
      return requestScopedWindowPayload(currentPayload, nextOptions, requestUsagePayload);
    }
    return nextOptions.limit === 0
      ? loadAllUsagePayloadPaged(currentPayload, nextOptions, requestUsagePayload)
      : requestUsagePayload(currentPayload, nextOptions);
  }
  if (options.loadWindow && options.loadWindow !== 'rows') {
    return requestScopedWindowPayload(currentPayload, options, requestUsagePayload);
  }
  return options.limit === 0
    ? loadAllUsagePayloadPaged(currentPayload, options, requestUsagePayload)
    : requestUsagePayload(currentPayload, options);
}

async function tryRefreshUsageIndex(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest,
): Promise<boolean> {
  try {
    await refreshUsageIndex(currentPayload, options);
    return true;
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (error instanceof UsageRefreshJobFailedError) {
      throw error;
    }
    return false;
  }
}

async function requestUsagePayload(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest = {},
): Promise<DashboardBootPayload> {
  assertLiveUsagePayloadAvailable(currentPayload);

  const params = new URLSearchParams({
    refresh: options.refresh ? '1' : '0',
    limit: String(options.limit ?? currentPayload?.limit ?? currentPayload?.loaded_row_count ?? 500),
    _: String(Date.now()),
  });
  if (options.loadWindow) params.set('load_window', options.loadWindow);
  if (options.since) params.set('since', options.since);
  if (options.offset && options.offset > 0) {
    params.set('offset', String(options.offset));
  }
  const includeArchived = options.includeArchived ?? payloadIncludesArchived(currentPayload);
  if (includeArchived) {
    params.set('include_archived', '1');
  }

  const response = await fetch(`/api/usage?${params.toString()}`, {
    headers: liveUsageHeaders(currentPayload),
    cache: 'no-store',
    signal: options.signal,
  });
  const payload = await readJsonResponse(response, 'Usage refresh');
  return payload as DashboardBootPayload;
}


async function refreshUsageIndex(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest,
): Promise<RefreshProgressPayload> {
  assertLiveUsagePayloadAvailable(currentPayload);
  const params = new URLSearchParams({ _: String(Date.now()) });
  const includeArchived = options.includeArchived ?? payloadIncludesArchived(currentPayload);
  if (includeArchived) {
    params.set('include_archived', '1');
  }
  const startResponse = await fetch(`/api/refresh/start?${params.toString()}`, {
    headers: liveUsageHeaders(currentPayload),
    cache: 'no-store',
    signal: options.signal,
  });
  const started = (await readJsonResponse(startResponse, 'Usage refresh start')) as RefreshProgressPayload;
  options.onProgress?.(started);
  const jobId = typeof started.job_id === 'string' ? started.job_id : '';
  if (!jobId) {
    throw new Error('Usage refresh start did not return a job id.');
  }
  return pollUsageRefreshJob(currentPayload, jobId, options.onProgress, options.signal);
}

async function pollUsageRefreshJob(
  currentPayload: DashboardBootPayload,
  jobId: string,
  onProgress?: (progress: RefreshProgressPayload) => void,
  signal?: AbortSignal,
): Promise<RefreshProgressPayload> {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    signal?.throwIfAborted();
    const params = new URLSearchParams({ job_id: jobId, _: String(Date.now()) });
    const response = await fetch(`/api/refresh/status?${params.toString()}`, {
      headers: liveUsageHeaders(currentPayload),
      cache: 'no-store',
      signal,
    });
    const progress = (await readJsonResponse(response, 'Usage refresh status')) as RefreshProgressPayload;
    onProgress?.(progress);
    if (progress.status === 'completed') {
      return progress;
    }
    if (progress.status === 'failed') {
      throw new UsageRefreshJobFailedError(progress.error || progress.message || 'Usage refresh failed.');
    }
    await abortableDelay(Math.min(1000, 150 + attempt * 50), signal);
  }
  throw new Error('Usage refresh did not complete before the polling timeout.');
}

class UsageRefreshJobFailedError extends Error {}


export function modelFromBootPayload(payload: DashboardBootPayload | null): DashboardModel {
 if (!payload) {
 return {
 ...fixtureModel,
 contextRuntime: contextRuntimeFromBootPayload(payload),
 };
 }

 const rows = payload.rows ?? [];
 const calls = rows.map(usageRowToCall);
  const totalTokens = rows.length ? sumRows(rows, row => Number(row.total_tokens ?? 0)) : summaryNumber(payload, 'total_tokens');
  const estimatedCost = rows.length ? sumRows(rows, row => Number(row.estimated_cost_usd ?? 0)) : summaryNumber(payload, 'estimated_cost_usd');
  const cachedTokens = rows.length ? sumRows(rows, row => Number(row.cached_input_tokens ?? 0)) : summaryNumber(payload, 'cached_input_tokens');
  const inputTokens = rows.length ? sumRows(rows, row => Number(row.input_tokens ?? 0)) : summaryNumber(payload, 'input_tokens');
  const uncachedTokens = rows.length
    ? sumRows(rows, row => {
        const input = Number(row.input_tokens ?? 0);
        const cached = Number(row.cached_input_tokens ?? 0);
        return Number(row.uncached_input_tokens ?? Math.max(input - cached, 0));
      })
    : Math.max(inputTokens - cachedTokens, 0);
  const outputTokens = rows.length ? sumRows(rows, row => Number(row.output_tokens ?? 0)) : summaryNumber(payload, 'output_tokens');
  const reasoningOutputTokens = rows.length
    ? sumRows(rows, row => Number(row.reasoning_output_tokens ?? 0))
    : summaryNumber(payload, 'reasoning_output_tokens');
  const cachePct = inputTokens > 0 ? (cachedTokens / inputTokens) * 100 : 0;
  const totalCalls = calls.length || Math.max(0, Number(payload.loaded_row_count ?? 0));
const overviewSeries = buildOverviewSeries(rows);
const usageDrainSeries = buildUsageDrainSeries(rows);
const cards = buildCards({
    cachePct,
    cachedTokens,
    estimatedCost,
    historyScope: payload.history_scope ?? 'active',
    totalCalls,
    totalTokens,
    tokenBreakdown: {
      cachedInput: cachedTokens,
      uncachedInput: uncachedTokens,
      output: outputTokens,
      reasoningOutput: reasoningOutputTokens,
    },
    usageRemainingCard: buildUsageRemainingCard(payload),
  });

 return {
 ...emptyDashboardModel(payload),
contextRuntime: contextRuntimeFromBootPayload(payload),
scopeSummary: scopeSummaryFromBootPayload(payload),
cards,
...overviewSeries,
...usageDrainSeries,
calls,
threads: buildThreads(calls),
findings: buildFindings(calls),
modelCosts: buildModelCosts(calls),
reports: buildReports(calls),
cacheSegments: [
      { label: 'Cache read', value: cachePct, color: '#2563eb' },
      { label: 'Uncached input', value: Math.max(100 - cachePct, 0), color: '#7c3aed' },
    ],
  };
}

function emptyDashboardModel(payload: DashboardBootPayload): DashboardModel {
return {
 ...fixtureModel,
 contextRuntime: contextRuntimeFromBootPayload(payload),
 tokenSeries: [],
 costSeries: [],
 cacheSeries: [],
 weeklyCreditSeries: [],
 usageRemainingSeries: [],
 actualVsPredictedSeries: [],
 calls: [],
 threads: [],
 findings: [],
 weeklyWindows: [],
 modelCosts: [],
 commandActions: [],
 cacheSegments: [],
 cacheHeatmap: [],
 diagnostics: [],
 reports: [],
};
}

function buildOverviewSeries(rows: UsageRow[]): Pick<DashboardModel, 'tokenSeries' | 'costSeries' | 'cacheSeries'> {
  return buildOverviewSeriesFromDailyValues(
    rows.map(row => ({
      timestamp: rowTimestamp(row),
      cached: Number(row.cached_input_tokens ?? 0),
cost: Number(row.estimated_cost_usd ?? 0),
input: Number(row.input_tokens ?? 0),
output: Number(row.output_tokens ?? 0),
})),
  );
}

function buildUsageDrainSeries(
  rows: UsageRow[],
): Pick<DashboardModel, 'weeklyCreditSeries' | 'usageRemainingSeries' | 'actualVsPredictedSeries' | 'weeklyWindows'> {
  const dailyRows = [...rows]
    .map(row => ({ row, timestamp: rowTimestamp(row) }))
    .filter(entry => Number.isFinite(entry.timestamp))
    .sort((left, right) => left.timestamp - right.timestamp);
  const daily = new Map<string, { timestamp: number; credits: number; weeklyUsedPercent: number | null }>();
  for (const { row, timestamp } of dailyRows) {
    const label = formatChartDate(timestamp);
    const current = daily.get(label) ?? { timestamp, credits: 0, weeklyUsedPercent: null };
    current.credits += Math.max(0, Number(row.usage_credits ?? 0));
    const usedPercent = percentNumber(row.rate_limit_secondary_used_percent);
    if (usedPercent !== null) current.weeklyUsedPercent = usedPercent;
    daily.set(label, current);
  }
  const dailyPoints = [...daily.entries()].map(([label, value]) => ({ label, ...value }));
  let cumulativeCredits = 0;
  const observedPoints = dailyPoints.map(point => {
    cumulativeCredits += point.credits;
    return { label: point.label, value: cumulativeCredits };
  });
  const predictedPoints = observedPoints.map((point, index) => ({
    label: point.label,
    value: observedPoints.length > 1 ? (observedPoints.at(-1)?.value ?? 0) * ((index + 1) / observedPoints.length) : point.value,
  }));
  const remainingPoints = dailyPoints
    .filter(point => point.weeklyUsedPercent !== null)
    .map(point => ({ label: point.label, value: clampPercent(100 - (point.weeklyUsedPercent ?? 0)) }));
  const weeklyWindows = buildWeeklyWindows(rows);
  return {
    weeklyCreditSeries: buildWeeklyCreditSeries(weeklyWindows),
    usageRemainingSeries: remainingPoints.length
      ? [{ id: 'weekly-remaining', label: 'Weekly remaining', color: '#059669', points: remainingPoints }]
      : [],
    actualVsPredictedSeries: observedPoints.length
      ? [
          { id: 'observed-drain', label: 'Observed drain', color: '#2563eb', points: observedPoints },
          { id: 'loaded-baseline', label: 'Loaded-row baseline', color: '#1d4ed8', dashed: true, points: predictedPoints },
        ]
      : [],
    weeklyWindows,
  };
}

function buildWeeklyWindows(rows: UsageRow[]): WeeklyWindow[] {
  const weeklyBuckets = new Map<string, { rows: UsageRow[]; latestTimestamp: number; latestUsedPercent: number | null }>();
  for (const row of rows) {
    const timestamp = rowTimestamp(row);
    if (!Number.isFinite(timestamp)) continue;
    const key = weeklyWindowKey(row, timestamp);
    const bucket = weeklyBuckets.get(key) ?? { rows: [], latestTimestamp: 0, latestUsedPercent: null };
    bucket.rows.push(row);
    if (timestamp >= bucket.latestTimestamp) {
      bucket.latestTimestamp = timestamp;
      bucket.latestUsedPercent = percentNumber(row.rate_limit_secondary_used_percent);
    }
    weeklyBuckets.set(key, bucket);
  }
  return [...weeklyBuckets.entries()]
    .map(([week, bucket]) => {
      const credits = bucket.rows.reduce((sum, row) => sum + Math.max(0, Number(row.usage_credits ?? 0)), 0);
      const observedPct = bucket.latestUsedPercent ?? 0;
      return {
        week,
        plan: String(bucket.rows[0]?.rate_limit_plan_type ?? 'unknown'),
        observedPct,
        credits,
        projected: observedPct > 0 ? credits / (observedPct / 100) : credits,
        ciLow: observedPct > 0 ? credits / (observedPct / 100) * 0.85 : credits,
        ciHigh: observedPct > 0 ? credits / (observedPct / 100) * 1.15 : credits,
        confidence: bucket.rows.length >= 20 ? 'Medium' : 'Low',
        note: `Loaded ${formatNumber(bucket.rows.length)} rows`,
      } satisfies WeeklyWindow;
    })
    .sort((left, right) => left.week.localeCompare(right.week));
}

function buildWeeklyCreditSeries(weeklyWindows: WeeklyWindow[]): Series[] {
  if (!weeklyWindows.length) return [];
  return [
    {
      id: 'weekly-projected',
      label: 'Projected weekly credits',
      color: '#2563eb',
      points: weeklyWindows.map(window => ({
        label: window.week,
        value: window.projected,
        low: window.ciLow,
        high: window.ciHigh,
      })),
    },
    {
      id: 'loaded-credits',
      label: 'Loaded-row credits',
      color: '#0f766e',
      dashed: true,
      points: weeklyWindows.map(window => ({ label: window.week, value: window.credits })),
    },
  ];
}

function weeklyWindowKey(row: UsageRow, timestamp: number): string {
  const resetSeconds = numericValue(row.rate_limit_secondary_resets_at);
  if (resetSeconds !== null && resetSeconds > 0) {
    return formatChartDate(resetSeconds * 1000);
  }
  return formatChartDate(timestamp);
}

function formatChartDate(timestamp: number): string {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(timestamp));
}

function contextRuntimeFromBootPayload(payload: DashboardBootPayload | null): ContextRuntime {
  return {
    apiToken: String(payload?.api_token ?? ''),
    contextApiEnabled: Boolean(payload?.context_api_enabled),
    fileMode: window.location.protocol === 'file:',
  };
}

function buildCards(input: {
  cachePct: number;
  cachedTokens: number;
  estimatedCost: number;
  historyScope: string;
  totalCalls: number;
  totalTokens: number;
  tokenBreakdown: {
    cachedInput: number;
    uncachedInput: number;
    output: number;
    reasoningOutput: number;
  };
  usageRemainingCard: MetricCard;
}): MetricCard[] {
  return [
    {
      label: 'Total Tokens',
      value: formatCompact(input.totalTokens),
      detail: `${input.historyScope} history scope`,
      trend: 'loaded aggregate rows',
      tone: 'blue',
      breakdown: [
        { label: 'Cached', value: formatCompact(input.tokenBreakdown.cachedInput) },
        { label: 'Uncached', value: formatCompact(input.tokenBreakdown.uncachedInput) },
        { label: 'Output', value: formatCompact(input.tokenBreakdown.output) },
        { label: 'Reasoning', value: formatCompact(input.tokenBreakdown.reasoningOutput) },
      ],
    },
    {
      label: 'Estimated Cost',
      value: money(input.estimatedCost),
      detail: 'local pricing config',
      trend: 'privacy-safe estimate',
      tone: 'green',
    },
    {
      label: 'Cache Hit Rate',
      value: `${input.cachePct.toFixed(1)}%`,
      detail: `${formatCompact(input.cachedTokens)} cached input`,
      trend: input.cachePct >= 40 ? 'healthy cache reuse' : 'cache risk',
      tone: input.cachePct >= 40 ? 'purple' : 'orange',
    },
    {
      label: 'Total Calls',
      value: formatNumber(input.totalCalls),
      detail: 'loaded calls in this dashboard',
      trend: 'privacy-safe',
      tone: 'blue',
    },
    input.usageRemainingCard,
  ];
}

function buildUsageRemainingCard(payload: DashboardBootPayload): MetricCard {
  const observedCard = observedUsageRemainingCard(payload.observed_usage);
  if (observedCard) return observedCard;
  const configuredCard = configuredUsageRemainingCard(payload.allowance_windows);
  if (configuredCard) return configuredCard;
  return {
    label: 'Usage Remaining',
    value: 'Unknown',
    detail: payload.allowance_configured ? 'allowance configured; no current window' : 'no observed usage or allowance window',
    trend: payload.allowance_error ? `config issue: ${payload.allowance_error}` : 'not available in payload',
    tone: payload.allowance_error ? 'red' : 'orange',
  };
}

function observedUsageRemainingCard(observedUsage: DashboardBootPayload['observed_usage']): MetricCard | null {
  const windows = Array.isArray(observedUsage?.windows) ? observedUsage.windows : [];
  if (!observedUsage?.available || !windows.length) return null;
 const window = preferredUsageWindow(windows, entry => percentNumber(entry.used_percent) !== null);
  if (!window) return null;
  const usedPercent = percentNumber(window.used_percent) ?? 0;
  const remainingPercent = clampPercent(100 - usedPercent);
  return {
    label: 'Usage Remaining',
    value: formatPercent(remainingPercent),
    detail: `${shortLabel(window.label || window.key, 'Observed usage')} observed usage`,
    trend: resetLabel(window.resets_at) || observedUsage.source || 'observed locally',
    tone: usageRemainingTone(remainingPercent),
  };
}

function configuredUsageRemainingCard(windows: DashboardBootPayload['allowance_windows']): MetricCard | null {
  if (!Array.isArray(windows) || !windows.length) return null;
 const window = preferredUsageWindow(windows, entry => {
    const remainingPercent = percentNumber(entry.remaining_percent);
    const remainingCredits = numericValue(entry.remaining_credits);
    const totalCredits = numericValue(entry.total_credits);
    return remainingPercent !== null || remainingCredits !== null || (totalCredits !== null && totalCredits > 0);
  });
  if (!window) return null;
  const remainingCredits = numericValue(window.remaining_credits);
  const totalCredits = numericValue(window.total_credits);
  const computedPercent = remainingCredits !== null && totalCredits !== null && totalCredits > 0
    ? remainingCredits / totalCredits * 100
    : null;
  const remainingPercent = percentNumber(window.remaining_percent) ?? computedPercent;
  const value = remainingPercent !== null ? formatPercent(clampPercent(remainingPercent)) : `${formatCredits(remainingCredits ?? 0)} left`;
  return {
    label: 'Usage Remaining',
    value,
    detail: `${shortLabel(window.label || window.key, 'Allowance')} allowance window`,
    trend: [remainingCredits === null ? '' : `${formatCredits(remainingCredits)} left`, resetLabel(window.reset_at)]
      .filter(Boolean)
      .join(' · ') || 'configured allowance',
 tone: remainingPercent === null ? 'green' : usageRemainingTone(clampPercent(remainingPercent)),
 };
}

type UsageWindowCandidate = {
 key?: string;
 label?: string;
 window_minutes?: number | null;
};

function preferredUsageWindow<T extends UsageWindowCandidate>(
 windows: T[],
 isUsable: (window: T) => boolean,
): T | null {
 const usableWindows = windows.filter(isUsable);
 return usableWindows.find(isWeeklyUsageWindow) ?? usableWindows[0] ?? null;
}

function isWeeklyUsageWindow(window: UsageWindowCandidate): boolean {
 const windowMinutes = numericValue(window.window_minutes);
 const label = `${window.key ?? ''} ${window.label ?? ''}`.toLowerCase();
 return windowMinutes === 10_080 || /\b(weekly|week|7d|7-day|7 day)\b/.test(label);
}

export function usageRowToCall(row: UsageRow, index = 0): CallRow {
  const eventTimestamp = String(row.event_timestamp ?? row.time ?? row.turn_timestamp ?? row.started_at ?? row.call_started_at ?? '');
  const rawTime = eventTimestamp;
  const callStartedAt = String(row.call_started_at ?? row.started_at ?? eventTimestamp);
  const input = Number(row.input_tokens ?? 0);
  const output = Number(row.output_tokens ?? 0);
  const reasoningOutput = Number(row.reasoning_output_tokens ?? 0);
  const cached = Number(row.cached_input_tokens ?? 0);
  const cacheRatio = Number(row.cache_hit_ratio ?? row.cache_ratio ?? 0);
  const cachedPct = input > 0 ? (cached / input) * 100 : cacheRatio * 100;
  const totalTokens = Number(row.total_tokens ?? input + output);
  const durationSeconds = Number(row.duration_seconds ?? row.call_duration_seconds ?? 0);
  const previousCallEventTimestamp = String(row.previous_call_event_timestamp ?? '');
  const previousCallGapSeconds = Number(row.previous_call_delta_seconds ?? 0);
  const uncachedInput = Number(row.uncached_input_tokens ?? Math.max(input - cached, 0));
  const id = String(row.record_id ?? row.id ?? `${rawTime || 'row'}-${index}`);
  const signal = String(row.primary_signal ?? '').trim();
  const lineNumber = Number(row.line_number);
  const contextWindowPct = percentNumber(row.context_window_percent);
  const modelContextWindow = Number(row.model_context_window);
  const cumulativeTotalTokens = Number(row.cumulative_total_tokens);
  return {
    id,
    threadKey: String(row.thread_key ?? ''),
    rawTime,
    eventTimestamp,
    callStartedAt,
    time: formatShortDate(rawTime),
    thread: getThreadLabel(row),
    model: String(row.model ?? 'unknown'),
    effort: String(row.effort ?? 'blank'),
    input,
    output,
    reasoningOutput,
    totalTokens,
    cachedInput: cached,
    uncachedInput,
    cachedPct,
    ...usageBillingFields(row),
    duration: formatDuration(durationSeconds),
    durationSeconds,
    previousCallGap: formatDuration(previousCallGapSeconds),
    previousCallEventTimestamp,
    previousCallGapSeconds: Number.isFinite(previousCallGapSeconds) ? previousCallGapSeconds : 0,
    initiator: String(row.call_initiator ?? 'unknown'),
    initiatorReason: String(row.call_initiator_reason ?? ''),
    initiatorConfidence: String(row.call_initiator_confidence ?? ''),
    ...usageServiceTierFields(row, durationSeconds, totalTokens),
    usageCreditConfidence: String(row.usage_credit_confidence ?? 'unknown'),
    usageCreditModel: String(row.usage_credit_model ?? ''),
    usageCreditSource: String(row.usage_credit_source ?? ''),
    usageCreditFetchedAt: String(row.usage_credit_fetched_at ?? ''),
    usageCreditTier: String(row.usage_credit_tier ?? ''),
    usageCreditNote: String(row.usage_credit_note ?? ''),
    pricingModel: String(row.pricing_model ?? ''),
    pricingEstimated: Boolean(row.pricing_estimated),
    signal: signal || (cachedPct < 25 ? 'cache-risk' : 'aggregate'),
    recommendation: String(row.recommended_action ?? ''),
    tags: cachedPct < 25 ? ['uncached'] : cachedPct > 60 ? ['healthy-cache'] : [],
    sessionId: String(row.session_id ?? ''),
    turnId: String(row.turn_id ?? ''),
    parentSessionId: String(row.parent_session_id ?? ''),
    parentSessionUpdatedAt: String(row.resolved_parent_session_updated_at ?? row.parent_session_updated_at ?? ''),
    parentThread: String(row.resolved_parent_thread_name ?? row.parent_thread_name ?? ''),
    threadAttachmentLabel: String(row.thread_attachment_label ?? ''),
    threadSource: String(row.thread_source ?? ''),
    subagentType: String(row.subagent_type ?? ''),
    agentRole: String(row.agent_role ?? ''),
    agentNickname: String(row.agent_nickname ?? ''),
    project: String(row.project_name ?? ''),
    projectRelativeCwd: String(row.project_relative_cwd ?? ''),
    projectTags: Array.isArray(row.project_tags) ? row.project_tags.map(tag => String(tag)) : [],
    cwd: String(row.cwd ?? ''),
    sourceFile: String(row.source_file ?? ''),
    lineNumber: Number.isFinite(lineNumber) && lineNumber > 0 ? lineNumber : null,
    gitBranch: String(row.git_branch ?? ''),
    gitRemoteLabel: String(row.git_remote_label ?? ''),
    gitRemoteHash: String(row.git_remote_hash ?? ''),
    contextWindowPct,
    modelContextWindow: Number.isFinite(modelContextWindow) && modelContextWindow > 0 ? modelContextWindow : null,
    cumulativeTotalTokens: Number.isFinite(cumulativeTotalTokens) && cumulativeTotalTokens > 0 ? cumulativeTotalTokens : null,
    estimatedCacheSavings: Number(row.estimated_cache_savings_usd ?? 0),
    efficiencyFlags: Array.isArray(row.efficiency_flags) ? row.efficiency_flags.map(flag => String(flag)) : [],
  };
}

function percentNumber(value: unknown): number | null {
const numeric = Number(value);
if (!Number.isFinite(numeric)) return null;
return numeric <= 1 ? numeric * 100 : numeric;
}

function numericValue(value: unknown): number | null {
const numeric = Number(value);
return Number.isFinite(numeric) ? numeric : null;
}

function clampPercent(value: number): number {
return Math.max(0, Math.min(100, value));
}

function formatPercent(value: number): string {
const digits = Math.abs(value) >= 10 ? 0 : 1;
return `${value.toFixed(digits)}%`;
}

function formatCredits(value: number): string {
return `${formatCompact(value)} cr`;
}

function resetLabel(value: number | string | null | undefined): string {
if (value === null || value === undefined || value === '') return '';
const timestamp = typeof value === 'number' ? value * 1000 : Date.parse(value);
if (!Number.isFinite(timestamp)) return '';
return `resets ${formatStableTimestamp(timestamp)}`;
}

function formatStableTimestamp(value: string | number): string {
const date = new Date(value);
if (Number.isNaN(date.getTime())) return String(value);
return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

function shortLabel(value: string | undefined, fallback: string): string {
const label = value?.trim();
return label || fallback;
}

function usageRemainingTone(remainingPercent: number): MetricCard['tone'] {
if (remainingPercent < 20) return 'red';
if (remainingPercent < 40) return 'orange';
return 'green';
}

function payloadIncludesArchived(payload: DashboardBootPayload): boolean {
if (typeof payload.include_archived === 'boolean') return payload.include_archived;
return payload.history_scope === 'all-history' || payload.history_scope === 'all';
}

function getThreadLabel(row: UsageRow): string {
  const direct = row.thread_name ?? row.thread ?? row.resolved_parent_thread_name ?? row.parent_thread_name;
  if (direct && String(direct).trim()) {
    return String(direct);
  }

  const project = row.project_name ?? row.project_relative_cwd;
  const sessionSuffix = row.session_id ? row.session_id.slice(-6) : '';
  if (project && sessionSuffix) {
    return `${project} ${sessionSuffix}`;
  }

  return row.thread_attachment_label ? String(row.thread_attachment_label) : 'Untitled thread';
}

export function buildThreads(calls: CallRow[]): ThreadRow[] {
  const grouped = new Map<string, CallRow[]>();
  for (const call of calls) {
    const identity = call.threadKey ? `key:${call.threadKey}` : `name:${call.thread}`;
    grouped.set(identity, [...(grouped.get(identity) ?? []), call]);
  }

  return [...grouped.entries()]
    .map(([, rows]) => {
      const turns = rows.length;
      const sortedRows = [...rows].sort((left, right) => callTimestamp(right) - callTimestamp(left));
      const latestCall = sortedRows[0] ?? null;
      const threadKey = sortedRows.find(row => row.threadKey)?.threadKey;
      const name = latestCall?.thread ?? rows[0]?.thread ?? 'Untitled thread';
      const latestActivityRaw = latestCall?.rawTime || latestCall?.time || '';
      const totalTokens = rows.reduce((sum, row) => sum + row.totalTokens, 0);
      const cachedInput = rows.reduce((sum, row) => sum + row.cachedInput, 0);
      const uncachedInput = rows.reduce((sum, row) => sum + row.uncachedInput, 0);
      const outputTokens = rows.reduce((sum, row) => sum + row.output, 0);
      const reasoningOutput = rows.reduce((sum, row) => sum + row.reasoningOutput, 0);
      const cost = rows.reduce((sum, row) => sum + row.cost, 0);
      const credits = rows.reduce((sum, row) => sum + row.credits, 0);
      const totalDurationSeconds = rows.reduce((sum, row) => sum + row.durationSeconds, 0);
      const gapRows = rows.filter(row => row.previousCallGapSeconds > 0);
      const averageGapSeconds =
        gapRows.reduce((sum, row) => sum + row.previousCallGapSeconds, 0) / Math.max(gapRows.length, 1);
      const totalInput = cachedInput + uncachedInput;
      const cachePct =
        totalInput > 0 ? cachedInput / totalInput * 100 : rows.reduce((sum, row) => sum + row.cachedPct, 0) / Math.max(turns, 1);
      const contextValues = rows
        .map(row => row.contextWindowPct)
        .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
      const coldResumeRisk = cachePct < 25 ? 'High' : cachePct < 45 ? 'Medium' : 'Low';
      return {
        name,
        ...(threadKey ? { threadKey } : {}),
        latestCallId: latestCall?.id ?? '',
        latestActivity: formatShortDate(latestActivityRaw),
        latestActivityRaw,
        turns,
        totalDurationSeconds,
        totalDuration: formatDuration(totalDurationSeconds),
        averageGapSeconds,
        averageGap: formatDuration(averageGapSeconds),
        initiatorSummary: summarizeThreadValues(rows.map(row => row.initiator)),
        modelSummary: summarizeThreadValues(rows.map(row => row.model)),
        effortSummary: summarizeThreadValues(rows.map(row => row.effort)),
        totalTokens,
        cachedInput,
        uncachedInput,
        outputTokens,
        reasoningOutput,
        cost,
        credits,
        cachePct,
        contextPct: contextValues.length ? Math.max(...contextValues) : null,
        costPerCall: cost / Math.max(turns, 1),
        coldResumeRisk,
        productivity: Math.max(20, Math.round(cachePct - cost / Math.max(turns, 1) * 4)),
      } satisfies ThreadRow;
    })
    .sort((left, right) => right.cost - left.cost)
    .slice(0, 20);
}

function callTimestamp(row: CallRow): number {
  const parsed = Date.parse(row.rawTime || row.time);
  return Number.isFinite(parsed) ? parsed : 0;
}

function summarizeThreadValues(values: string[], limit = 3): string {
  const counts = new Map<string, number>();
  for (const value of values) {
    const label = value.trim() || 'unknown';
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([label, count]) => `${label} x${formatNumber(count)}`)
    .join(', ') || 'unknown';
}

function sumRows(rows: UsageRow[], selector: (row: UsageRow) => number): number {
  return rows.reduce((total, row) => total + selector(row), 0);
}

async function readJsonResponse(response: Response, label: string): Promise<Record<string, unknown>> {
  let payload: Record<string, unknown>;
  try {
    payload = await response.json() as Record<string, unknown>;
  } catch (error) {
    if (response.ok) {
      throw new Error(`${label} response could not be read as JSON: ${errorMessage(error)}`);
    }
    payload = {};
  }
  if (!response.ok) {
    const message = typeof payload.error === 'string' ? payload.error : `${label} request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds.toFixed(0)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function formatShortDate(raw: string): string {
const date = new Date(raw);
if (Number.isNaN(date.getTime())) {
return raw || '-';
}
return new Intl.DateTimeFormat('en-US', {
month: 'short',
day: 'numeric',
hour: 'numeric',
minute: '2-digit',
}).format(date);
}

function rowTimestamp(row: UsageRow): number {
return Date.parse(String(row.started_at ?? row.call_started_at ?? row.time ?? row.event_timestamp ?? row.turn_timestamp ?? ''));
}
