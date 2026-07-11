import type { LoadWindow } from '../data/dataScope';
import type { DashboardBootPayload, UsageRow } from './types';

export type RefreshProgressPayload = {
  schema?: string;
  job_id?: string;
  status?: string;
  phase?: string;
  message?: string;
  completed?: number;
  total?: number;
  percent?: number;
  error?: string;
  result?: Record<string, unknown>;
};

export type UsagePayloadRequest = {
  refresh?: boolean;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
  loadWindow?: LoadWindow;
  since?: string | null;
  onProgress?: (progress: RefreshProgressPayload) => void;
  signal?: AbortSignal;
};

type UsagePageRequester = (
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest,
) => Promise<DashboardBootPayload>;

const uncappedUsagePageSize = 10_000;
const scopedWindowEvidenceLimit = 500;

export async function requestScopedWindowPayload(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest,
  requestPage: UsagePageRequester,
): Promise<DashboardBootPayload> {
  const requestedEvidenceLimit = options.limit && options.limit > 0
    ? options.limit
    : scopedWindowEvidenceLimit;
  const payload = await requestPage(currentPayload, { ...options, limit: requestedEvidenceLimit });
  options.onProgress?.({
    status: 'completed',
    phase: 'loading_rows',
    message: `Loaded ${options.loadWindow === 'all' ? 'all-history' : options.loadWindow} evidence window`,
    completed: Number(payload.loaded_row_count ?? payload.rows?.length ?? 0),
    total: Number(payload.total_available_rows ?? payload.loaded_row_count ?? 0),
    percent: 100,
  });
  return payload;
}

export async function loadAllUsagePayloadPaged(
  currentPayload: DashboardBootPayload | null,
  options: UsagePayloadRequest,
  requestPage: UsagePageRequester,
): Promise<DashboardBootPayload> {
  const rows: UsageRow[] = [];
  let offset = 0;
  let latestPayload: DashboardBootPayload | null = null;
  let totalRows = Number(currentPayload?.total_available_rows ?? 0);
  for (let pageIndex = 0; pageIndex < 1000; pageIndex += 1) {
    options.signal?.throwIfAborted();
    const payload = await requestPage(currentPayload, {
      ...options,
      refresh: pageIndex === 0 ? options.refresh : false,
      limit: uncappedUsagePageSize,
      offset,
    });
    const pageRows = payload.rows ?? [];
    latestPayload = payload;
    rows.push(...pageRows);
    totalRows = Number(payload.total_available_rows ?? totalRows ?? rows.length);
    const pageComplete = rows.length >= totalRows || !payload.has_more;
    options.onProgress?.({
      status: pageComplete ? 'completed' : 'running',
      phase: 'loading_rows',
      message: 'Loading all rows',
      completed: rows.length,
      total: totalRows,
      percent: pageComplete ? 100 : totalRows > 0 ? Math.min(99, Math.floor((rows.length / totalRows) * 100)) : 0,
    });
    offset += pageRows.length;
    if (!payload.has_more || pageRows.length === 0 || rows.length >= totalRows) break;
  }
  return {
    ...(latestPayload ?? currentPayload ?? {}),
    rows,
    loaded_row_count: rows.length,
    limit: null,
    limit_label: 'All',
    has_more: false,
    total_available_rows: totalRows || rows.length,
  } as DashboardBootPayload;
}
