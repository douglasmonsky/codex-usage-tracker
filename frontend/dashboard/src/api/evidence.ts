import type { ContextRuntime } from './types';

type EvidenceKind = 'call' | 'thread' | 'finding' | 'allowance';
export type EvidenceMetricValue = string | number | boolean | null;

export type EvidenceRecord = {
  schema: 'codex-usage-tracker.evidence.v1';
  evidence_id: string;
  kind: string;
  label: string;
  selectors: Record<string, string>;
  metrics: Record<string, EvidenceMetricValue>;
  source_schema: string;
  dashboard_target: Record<string, unknown> | null;
};

export type EvidenceResult = {
  schema: 'codex-usage-tracker.evidence-result.v1';
  selector: { kind: string; id: string; section: string; analysis_id?: string };
  records: EvidenceRecord[];
  next_cursor: string | null;
  dashboard_target: Record<string, unknown>;
  subject: Record<string, unknown> | null;
};

export type EvidenceApiRequest = {
  kind: EvidenceKind;
  selectorId: string;
  section?: 'summary' | 'calls';
  limit?: number;
  cursor?: string;
  history?: 'active' | 'all';
  analysisId?: string | null;
};

export class EvidenceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
    this.name = 'EvidenceApiError';
  }
}

export async function loadEvidence(
  request: EvidenceApiRequest,
  runtime: ContextRuntime,
): Promise<EvidenceResult> {
  if (runtime.fileMode) {
    throw new EvidenceApiError('Evidence hydration requires the localhost dashboard server.', 0, 'file_mode');
  }
  const payload = {
    selector_kind: request.kind,
    selector_id: request.selectorId,
    section: request.section ?? 'summary',
    limit: request.limit ?? 20,
    history: request.history ?? 'active',
    ...(request.cursor ? { cursor: request.cursor } : {}),
    ...(request.kind === 'finding' && request.analysisId
      ? { analysis_id: request.analysisId }
      : {}),
  };
  const response = await fetch('/api/v2/evidence', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(runtime.apiToken ? { 'X-Codex-Usage-Token': runtime.apiToken } : {}),
    },
    body: JSON.stringify(payload),
    cache: 'no-store',
  });
  const responsePayload = await readPayload(response);
  if (!response.ok) {
    const error = readError(responsePayload);
    const message = error?.message ?? `Evidence request failed (${response.status})`;
    throw new EvidenceApiError(
      message,
      response.status,
      error?.code ?? null,
    );
  }
  if (!isEvidenceResult(responsePayload)) {
    throw new EvidenceApiError('Evidence response did not match the shared evidence contract.', 502, 'invalid_contract');
  }
  return responsePayload;
}

function readError(payload: Record<string, unknown>): { code: string; message: string } | null {
  if (!payload.error || typeof payload.error !== 'object') return null;
  const error = payload.error as Record<string, unknown>;
  return typeof error.code === 'string' && typeof error.message === 'string'
    ? { code: error.code, message: error.message }
    : null;
}

async function readPayload(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload = await response.json();
    return payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function isEvidenceResult(value: unknown): value is EvidenceResult {
  if (!value || typeof value !== 'object') return false;
  const result = value as Partial<EvidenceResult>;
  return result.schema === 'codex-usage-tracker.evidence-result.v1'
    && Boolean(result.selector)
    && Array.isArray(result.records)
    && (result.next_cursor === null || typeof result.next_cursor === 'string');
}
