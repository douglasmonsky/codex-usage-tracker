import type { ContextRuntime } from './types';

export type InvestigationEvidenceRow = Record<string, unknown> & {
  record_id?: string;
  thread_name?: string;
  thread_key?: string;
  total_tokens?: number;
  output_tokens?: number;
  occurrences?: number;
  call_count?: number;
};

export type InvestigationFindingPayload = {
  finding: string;
  evidence_count: number;
  evidence_summary: Record<string, unknown>;
  evidence: InvestigationEvidenceRow[];
  confidence: string;
  why_it_matters: string;
  recommended_action: string;
  verify_with: string[];
  missing_access: string;
  privacy_notes: string;
};

export type AgenticInvestigationPayload = {
  schema: 'codex-usage-tracker-agentic-investigation-v1';
  content_mode: string;
  includes_indexed_content: boolean;
  includes_raw_fragments: boolean;
  privacy_mode: string;
  goal: string;
  filters: Record<string, unknown>;
  summary: {
    finding_count: number;
    top_finding: string | null;
    confidence: string;
    source_reports: string[];
  };
  findings: InvestigationFindingPayload[];
  recommended_next_tools: Array<Record<string, unknown>>;
  caveats: string[];
};

export type InvestigationWalkBranch = Record<string, unknown> & {
  scan_type?: string;
  hypothesis?: string;
  status?: string;
  score?: number;
  evidence?: Array<Record<string, unknown>>;
};

export type InvestigationWalkPayload = {
  schema: 'codex-usage-tracker-investigation-walk-v1';
  content_mode: string;
  includes_indexed_content: boolean;
  includes_raw_fragments: boolean;
  privacy_mode: string;
  question: string;
  filters: Record<string, unknown>;
  summary: {
    branch_count: number;
    supported_branch_count: number;
    top_hypothesis: string | null;
    confidence: string;
  };
  branches: InvestigationWalkBranch[];
  recommended_next_tools: Array<Record<string, unknown>>;
};

type InvestigationRequest = {
  evidenceLimit?: number;
  includeArchived?: boolean;
};

export async function loadAgenticInvestigation(
  runtime: ContextRuntime,
  options: InvestigationRequest & { goal?: string } = {},
): Promise<AgenticInvestigationPayload> {
  const params = investigationParams(options);
  params.set('goal', options.goal ?? 'token_waste');
  params.set('detail_mode', 'compact');
  return loadInvestigationPayload(runtime, '/api/investigations/agentic', params, 'Investigation');
}

export async function loadInvestigationWalk(
  runtime: ContextRuntime,
  question: string,
  options: InvestigationRequest & { minOccurrences?: number } = {},
): Promise<InvestigationWalkPayload> {
  const params = investigationParams(options);
  params.set('question', question.trim() || 'Where is avoidable token waste concentrated?');
  params.set('min_occurrences', String(Math.max(1, options.minOccurrences ?? 2)));
  return loadInvestigationPayload(runtime, '/api/investigations/walk', params, 'Local investigation trace');
}

function investigationParams(options: InvestigationRequest): URLSearchParams {
  const params = new URLSearchParams({
    evidence_limit: String(Math.max(1, options.evidenceLimit ?? 8)),
    _: String(Date.now()),
  });
  if (options.includeArchived) params.set('include_archived', '1');
  return params;
}

async function loadInvestigationPayload<T>(
  runtime: ContextRuntime,
  path: string,
  params: URLSearchParams,
  label: string,
): Promise<T> {
  ensureInvestigationRuntime(runtime);
  const response = await fetch(`${path}?${params.toString()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(typeof payload.error === 'string' ? payload.error : `${label} failed with HTTP ${response.status}`);
  }
  return payload as T;
}

function ensureInvestigationRuntime(runtime: ContextRuntime): void {
  if (runtime.fileMode || window.location.protocol === 'file:') {
    throw new Error('Live investigations require the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Live investigations require the localhost dashboard API token.');
  }
}
