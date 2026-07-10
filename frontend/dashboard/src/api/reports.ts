import { usageRowToCall } from './client';
import type { CallRow, ContextRuntime, ReportSummary, UsageRow } from './types';

type ReportPackReport = ReportSummary & { key: string };

type ReportsPackPayload = {
  schema?: string;
  reports?: ReportPackReport[];
  evidence?: Record<string, { rows?: UsageRow[]; row_count?: number; limit?: number }>;
  row_count?: number;
  total_matched_rows?: number;
  raw_context_included?: boolean;
};

export type ReportsPackModel = {
  reports: ReportPackReport[];
  evidence: Record<string, CallRow[]>;
  rowCount: number;
  totalMatchedRows: number;
  rawPayload: ReportsPackPayload;
};

export type ReportsPackRequest = {
  limit?: number;
  evidenceLimit?: number;
  includeArchived?: boolean;
};

export async function loadReportsPack(
  runtime: ContextRuntime,
  options: ReportsPackRequest = {},
): Promise<ReportsPackModel> {
  if (window.location.protocol === 'file:') {
    throw new Error('Live report pack requires the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Live report pack requires localhost dashboard API token.');
  }

  const params = new URLSearchParams({
    limit: String(options.limit ?? 500),
    evidence_limit: String(options.evidenceLimit ?? 8),
    _: String(Date.now()),
  });
  if (options.includeArchived) {
    params.set('include_archived', '1');
  }

  const response = await fetch(`/api/reports/pack?${params.toString()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await readJsonResponse(response, 'Reports pack')) as ReportsPackPayload;
  return {
    reports: payload.reports ?? [],
    evidence: evidenceRowsToCalls(payload.evidence ?? {}),
    rowCount: Number(payload.row_count ?? 0),
    totalMatchedRows: Number(payload.total_matched_rows ?? payload.row_count ?? 0),
    rawPayload: payload,
  };
}

function evidenceRowsToCalls(evidence: NonNullable<ReportsPackPayload['evidence']>): Record<string, CallRow[]> {
  return Object.fromEntries(
    Object.entries(evidence).map(([key, value]) => [
      key,
      (value.rows ?? []).map((row, index) => usageRowToCall(row, index)),
    ]),
  );
}

async function readJsonResponse(response: Response, label: string): Promise<Record<string, unknown>> {
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(typeof payload.error === 'string' ? payload.error : `${label} failed with HTTP ${response.status}`);
  }
  return payload;
}
