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

type EvidenceResult = {
  schema: 'codex-usage-tracker.evidence-result.v1';
  selector: { kind: string; id: string; section: string; analysis_id?: string };
  records: EvidenceRecord[];
  next_cursor: string | null;
  dashboard_target: Record<string, unknown>;
  subject: Record<string, unknown> | null;
};

export type EvidenceEnvelope = {
  schema: 'codex-usage-tracker.mcp-envelope.v1';
  tool: 'usage_evidence';
  request_id: string;
  generated_at: string;
  source_revision: string | null;
  data_class: 'aggregate';
  scope: { history: string; privacy_mode: string; filters: Record<string, unknown> };
  result_schema: 'codex-usage-tracker.evidence-result.v1';
  result: EvidenceResult;
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
): Promise<EvidenceEnvelope> {
  if (runtime.fileMode) {
    throw new EvidenceApiError('Evidence hydration requires the localhost dashboard server.', 0, 'file_mode');
  }
  if (!runtime.apiToken) {
    throw new EvidenceApiError('Evidence hydration requires a localhost dashboard API token.', 0, 'missing_token');
  }
  const params = new URLSearchParams({
    selector_kind: request.kind,
    selector_id: request.selectorId,
    section: request.section ?? 'summary',
    limit: String(request.limit ?? 20),
    history: request.history ?? 'active',
  });
  if (request.cursor) params.set('cursor', request.cursor);
  if (request.kind === 'finding' && request.analysisId) {
    params.set('analysis_id', request.analysisId);
  }
  const response = await fetch(`/api/v2/evidence?${params.toString()}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = await readPayload(response);
  if (!response.ok) {
    const message = typeof payload.error === 'string'
      ? payload.error
      : `Evidence request failed (${response.status})`;
    throw new EvidenceApiError(
      message,
      response.status,
      typeof payload.code === 'string' ? payload.code : null,
    );
  }
  if (
    payload.schema !== 'codex-usage-tracker.mcp-envelope.v1'
    || payload.result_schema !== 'codex-usage-tracker.evidence-result.v1'
    || !isEvidenceResult(payload.result)
  ) {
    throw new EvidenceApiError('Evidence response did not match the shared evidence contract.', 502, 'invalid_contract');
  }
  return payload as EvidenceEnvelope;
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
