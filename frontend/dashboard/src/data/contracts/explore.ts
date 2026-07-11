import { usageRowToCall } from '../../api/client';
import type { CallRow, UsageRow } from '../../api/types';

type ExplorePage<T> = {
  rows: T[];
  rowCount: number;
  totalMatchedRows: number;
  limit: number | null;
  offset: number;
  hasMore: boolean;
  nextOffset: number | null;
  rawContextIncluded: false;
};

export type ExploreCallsPage = ExplorePage<CallRow> & {
  schema: 'codex-usage-tracker-calls-v1' | 'codex-usage-tracker-thread-calls-v1';
  threadKey: string;
};

export type ThreadSummaryRecord = {
  threadKey: string;
  threadLabel: string;
  firstEventTimestamp: string;
  latestEventTimestamp: string;
  latestRecordId: string;
  callCount: number;
  sessionCount: number;
  inputTokens: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  totalTokens: number;
  estimatedCostUsd: number | null;
  usageCredits: number | null;
  averageCacheRatio: number;
  maxContextWindowPercent: number | null;
  maxRecommendationScore: number | null;
  primaryRecommendation: string;
  initiatorSummary: string;
  archivedCallCount: number;
  updatedAt: string;
};

export type ExploreThreadsPage = ExplorePage<ThreadSummaryRecord> & {
  schema: 'codex-usage-tracker-threads-v1';
  includeArchived: boolean;
};

export class ExploreContractError extends Error {}

export function decodeExploreCalls(value: unknown): ExploreCallsPage {
  const payload = record(value, 'calls response');
  const schema = payload.schema;
  if (schema !== 'codex-usage-tracker-calls-v1' && schema !== 'codex-usage-tracker-thread-calls-v1') {
    throw new ExploreContractError('Unsupported calls response schema.');
  }
  const page = pageMetadata(payload);
  return {
    schema,
    ...page,
    rows: records(payload.rows, 'call rows').map((row, index) =>
      usageRowToCall(row as UsageRow, page.offset + index),
    ),
    threadKey: text(payload.thread_key),
  };
}

export function decodeExploreThreads(value: unknown): ExploreThreadsPage {
  const payload = record(value, 'threads response');
  if (payload.schema !== 'codex-usage-tracker-threads-v1') {
    throw new ExploreContractError('Unsupported threads response schema.');
  }
  return {
    schema: payload.schema,
    ...pageMetadata(payload),
    rows: records(payload.rows, 'thread rows').map(decodeThreadSummary),
    includeArchived: boolean(payload.include_archived),
  };
}

function pageMetadata(payload: Record<string, unknown>): Omit<ExplorePage<never>, 'rows'> {
  const rowCount = number(payload.row_count);
  const totalMatchedRows = optionalNumber(payload.total_matched_rows) ?? rowCount;
  const limit = nullableLimit(payload.limit);
  const offset = number(payload.offset);
  const computedHasMore = limit !== null && offset + rowCount < totalMatchedRows;
  const hasMore = typeof payload.has_more === 'boolean' ? payload.has_more : computedHasMore;
  const computedNextOffset = hasMore ? offset + rowCount : null;
  return {
    rowCount,
    totalMatchedRows,
    limit,
    offset,
    hasMore,
    nextOffset: optionalNumber(payload.next_offset) ?? computedNextOffset,
    rawContextIncluded: false,
  };
}

function decodeThreadSummary(value: Record<string, unknown>): ThreadSummaryRecord {
  return {
    threadKey: text(value.thread_key),
    threadLabel: text(value.thread_label || value.thread_key),
    firstEventTimestamp: text(value.first_event_timestamp),
    latestEventTimestamp: text(value.latest_event_timestamp),
    latestRecordId: text(value.latest_record_id),
    callCount: number(value.call_count),
    sessionCount: number(value.session_count),
    inputTokens: number(value.input_tokens),
    cachedInputTokens: number(value.cached_input_tokens),
    uncachedInputTokens: number(value.uncached_input_tokens),
    outputTokens: number(value.output_tokens),
    reasoningOutputTokens: number(value.reasoning_output_tokens),
    totalTokens: number(value.total_tokens),
    estimatedCostUsd: optionalNumber(value.estimated_cost_usd),
    usageCredits: optionalNumber(value.usage_credits),
    averageCacheRatio: number(value.avg_cache_ratio),
    maxContextWindowPercent: optionalNumber(value.max_context_window_percent),
    maxRecommendationScore: optionalNumber(value.max_recommendation_score),
    primaryRecommendation: text(value.primary_recommendation),
    initiatorSummary: text(value.call_initiator_summary),
    archivedCallCount: number(value.archived_call_count),
    updatedAt: text(value.updated_at),
  };
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ExploreContractError(`Expected ${label} to be an object.`);
  }
  return value as Record<string, unknown>;
}

function records(value: unknown, label: string): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) throw new ExploreContractError(`Expected ${label} to be an array.`);
  return value.map((item, index) => record(item, `${label}[${index}]`));
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function number(value: unknown): number {
  return optionalNumber(value) ?? 0;
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nullableLimit(value: unknown): number | null {
  if (value === null || value === undefined || value === '' || value === 0 || value === '0') return null;
  return optionalNumber(value);
}

function boolean(value: unknown): boolean {
  return value === true;
}
