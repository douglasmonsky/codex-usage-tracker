import type {
  AgenticInvestigationPayload,
  InvestigationEvidenceRow as ApiEvidenceRow,
  InvestigationFindingPayload,
} from '../../api/investigations';
import {
  diagnosticSnapshotDefinitions,
  type DiagnosticSnapshotMap,
} from '../../api/diagnostics';
import type { CallRow, DashboardModel, Finding } from '../../api/types';
import {
  visualizationSpecSchema,
  type HeatmapVisualizationSpecV1,
} from '../../visualization';
import { snapshotCard } from '../diagnostics/diagnosticSnapshotCards';

type InvestigationConfidence = 'high' | 'medium' | 'low';
export type InvestigationTone = 'risk' | 'caution' | 'positive' | 'neutral' | 'context';

export type InvestigationEvidenceRow = {
  id: string;
  findingId: string;
  recordId: string;
  thread: string;
  pattern: string;
  events: number;
  tokens: number;
  value: string;
  confidence: InvestigationConfidence;
  action: string;
  detail: string;
  source: string;
};

export type InvestigationFinding = {
  id: string;
  title: string;
  category: string;
  confidence: InvestigationConfidence;
  tone: InvestigationTone;
  summary: string;
  action: string;
  verification: string[];
  missingAccess: string;
  privacyNote: string;
  evidence: InvestigationEvidenceRow[];
  evidenceCount: number;
  impactScore: number;
  source: string;
};

export type InvestigationWorkspaceModel = {
  findings: InvestigationFinding[];
  evidence: InvestigationEvidenceRow[];
  caveats: string[];
  sourceReports: string[];
  live: boolean;
};

const supplementalSnapshotKeys = new Set([
  'toolOutput',
  'fileReads',
  'fileModifications',
  'readProductivity',
  'concentration',
  'guidedSummary',
]);

export function buildInvestigationWorkspace(
  model: DashboardModel,
  agentic: AgenticInvestigationPayload | undefined,
  snapshots: DiagnosticSnapshotMap,
): InvestigationWorkspaceModel {
  const primary = agentic?.findings.length
    ? agentic.findings.map((finding, index) => findingFromAgentic(finding, index))
    : fallbackFindings(model);
  const supplemental = snapshotFindings(snapshots);
  const findings = dedupeFindings([...primary, ...supplemental, cacheContextFinding(model.calls)])
    .filter((finding): finding is InvestigationFinding => Boolean(finding))
    .sort((left, right) => right.impactScore - left.impactScore || right.evidenceCount - left.evidenceCount);
  return {
    findings,
    evidence: findings.flatMap(finding => finding.evidence),
    caveats: agentic?.caveats ?? [
      'Local Codex logs only; this is not an official OpenAI usage ledger.',
      'Static fallback findings use loaded aggregate rows and cannot identify shell or file rediscovery directly.',
    ],
    sourceReports: agentic?.summary.source_reports ?? [],
    live: Boolean(agentic),
  };
}

export function buildWasteFingerprintSpec(
  findings: InvestigationFinding[],
  historyScope: 'active' | 'all',
  sourceRevision: string,
): HeatmapVisualizationSpecV1 {
  const rows = findings.flatMap(finding => {
    const grouped = new Map<string, InvestigationEvidenceRow[]>();
    for (const row of finding.evidence) {
      const thread = row.thread || 'Aggregate';
      grouped.set(thread, [...(grouped.get(thread) ?? []), row]);
    }
    if (!grouped.size) grouped.set('Aggregate', []);
    return [...grouped.entries()].map(([thread, evidence]) => ({
      id: `${finding.id}:${thread}`,
      thread,
      pattern: finding.category,
      score: Math.max(1, evidence.reduce((sum, row) => sum + Math.max(row.events, 1), 0)),
      tokens: evidence.reduce((sum, row) => sum + row.tokens, 0),
      finding: finding.title,
    }));
  });
  return {
    schema: visualizationSpecSchema,
    id: 'waste-fingerprint-matrix',
    title: 'Waste fingerprint matrix',
    description: 'Recurring diagnostic patterns by thread or aggregate scope; darker cells carry more supporting events.',
    state: rows.length
      ? { kind: 'ready' }
      : { kind: 'empty', message: 'No diagnostic fingerprints are available for the current scope.' },
    scope: { label: `${findings.length} ranked findings`, rowCount: rows.length, historyScope },
    freshness: {
      generatedAt: sourceRevision || 'loaded-aggregate-snapshot',
      sourceRevision,
    },
    caveats: ['Event counts rank evidence volume, not guaranteed token savings.'],
    accessibility: {
      summary: fingerprintSummary(findings),
      keyboardInstructions: 'Use arrow keys to move between cells; use the synchronized table for exact values.',
    },
    table: {
      caption: 'Waste fingerprints by thread and diagnostic family',
      columns: [
        { field: 'thread', label: 'Thread', type: 'text' },
        { field: 'pattern', label: 'Pattern', type: 'category' },
        { field: 'score', label: 'Events', type: 'number', unit: 'count', align: 'right' },
        { field: 'tokens', label: 'Tokens', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'finding', label: 'Finding', type: 'text' },
      ],
      defaultSort: { field: 'score', direction: 'desc' },
    },
    interactions: { selection: { keyField: 'id', labelField: 'finding' } },
    kind: 'heatmap',
    data: { rows },
    encoding: {
      x: { field: 'pattern', label: 'Diagnostic family', type: 'category' },
      y: { field: 'thread', label: 'Thread', type: 'category' },
      value: { field: 'score', label: 'Supporting events', type: 'number', unit: 'count' },
      min: 0,
    },
  };
}

export function callsForFinding(finding: Finding, calls: CallRow[]): CallRow[] {
  const title = finding.title.toLowerCase();
  if (title.includes('cache')) {
    return topCalls(calls.filter(call => call.signal === 'cache-risk' || call.cachedPct < 35), 8);
  }
  if (title.includes('effort') || title.includes('reasoning')) {
    return topCalls(calls.filter(call => call.effort.toLowerCase() === 'high' || call.reasoningOutput > 0), 8);
  }
  if (title.includes('tool') || title.includes('output')) {
    return topCalls(calls.filter(call => call.output > 1_000 || call.tags.length > 0), 8);
  }
  return topCalls(calls, 8);
}

function findingFromAgentic(payload: InvestigationFindingPayload, index: number): InvestigationFinding {
  const id = uniqueId(payload.finding, index);
  const confidence = normalizeConfidence(payload.confidence);
  const evidence = payload.evidence.map((row, rowIndex) => evidenceFromAgentic(id, payload, row, rowIndex));
  const impactScore = impactFromSummary(payload.evidence_summary, evidence, payload.evidence_count);
  return {
    id,
    title: payload.finding,
    category: categoryForTitle(payload.finding),
    confidence,
    tone: toneForFinding(payload.finding, confidence),
    summary: payload.why_it_matters || 'The local report found a repeatable aggregate signal worth reviewing.',
    action: payload.recommended_action || 'Inspect the strongest supporting evidence before changing the workflow.',
    verification: payload.verify_with ?? [],
    missingAccess: payload.missing_access || 'No additional access is required for the aggregate evidence.',
    privacyNote: payload.privacy_notes || 'No raw fragments are included.',
    evidence,
    evidenceCount: Math.max(payload.evidence_count, evidence.length),
    impactScore,
    source: 'Agentic investigation',
  };
}

function evidenceFromAgentic(
  findingId: string,
  finding: InvestigationFindingPayload,
  row: ApiEvidenceRow,
  index: number,
): InvestigationEvidenceRow {
  const primaryRecommendation = objectValue(row.primary_recommendation);
  return {
    id: `${findingId}:evidence:${index}`,
    findingId,
    recordId: textValue(row.record_id),
    thread: textValue(row.thread_name) || textValue(row.thread_key) || textValue(row.thread) || 'Aggregate',
    pattern: textValue(row.candidate_kind) || textValue(row.command_family) || categoryForTitle(finding.finding),
    events: numericValue(row.occurrences ?? row.call_count ?? row.read_events ?? 1),
    tokens: numericValue(row.total_tokens ?? row.max_total_tokens ?? row.allocated_output_token_sum),
    value: textValue(row.candidate_explanation) || textValue(row.recommendation) || 'Supporting activity',
    confidence: normalizeConfidence(finding.confidence),
    action: textValue(row.recommended_action) || textValue(primaryRecommendation.action) || finding.recommended_action,
    detail: textValue(row.event_timestamp) || textValue(row.basename) || textValue(row.extension),
    source: 'Agentic investigation',
  };
}

function snapshotFindings(snapshots: DiagnosticSnapshotMap): InvestigationFinding[] {
  return diagnosticSnapshotDefinitions.flatMap((definition, index) => {
    if (!supplementalSnapshotKeys.has(definition.key) || !snapshots[definition.key]) return [];
    const card = snapshotCard(definition, snapshots[definition.key]);
    const id = uniqueId(definition.key, index + 100);
    const evidence = card.rows.slice(0, 8).map((row, rowIndex): InvestigationEvidenceRow => ({
      id: `${id}:evidence:${rowIndex}`,
      findingId: id,
      recordId: row.recordId ?? '',
      thread: row.label || 'Aggregate',
      pattern: definition.title,
      events: 1,
      tokens: 0,
      value: row.value,
      confidence: card.status === 'ready' ? 'medium' : 'low',
      action: actionForCategory(definition.key),
      detail: row.detail,
      source: card.status === 'ready' ? 'Stored diagnostic snapshot' : 'Loaded aggregate fallback',
    }));
    return [{
      id,
      title: titleForSnapshot(definition.key),
      category: categoryForSnapshot(definition.key),
      confidence: card.status === 'ready' ? 'medium' as const : 'low' as const,
      tone: toneForSnapshot(definition.key),
      summary: `${card.subtitle}. ${card.metrics.map(metric => `${metric.label}: ${metric.value}`).join('; ')}.`,
      action: actionForCategory(definition.key),
      verification: ['usage_report_pack'],
      missingAccess: card.status === 'ready' ? 'Outcome quality remains outside aggregate telemetry.' : 'Live diagnostics are unavailable in static mode.',
      privacyNote: 'This module uses aggregate or stored diagnostic fields and omits raw fragments.',
      evidence,
      evidenceCount: evidence.length,
      impactScore: evidence.length * 8 + (card.status === 'ready' ? 10 : 0),
      source: evidence[0]?.source ?? 'Diagnostic snapshot',
    }];
  });
}

function fallbackFindings(model: DashboardModel): InvestigationFinding[] {
  return model.findings.map((finding, index) => {
    const id = uniqueId(finding.title, index);
    const calls = callsForFinding(finding, model.calls);
    const confidence: InvestigationConfidence = finding.severity === 'High' ? 'medium' : 'low';
    return {
      id,
      title: finding.title,
      category: categoryForTitle(finding.title),
      confidence,
      tone: finding.severity === 'High' ? 'risk' : 'caution',
      summary: finding.summary,
      action: actionForCategory(categoryForTitle(finding.title)),
      verification: ['usage_calls', 'usage_report_pack'],
      missingAccess: 'Static mode cannot inspect indexed commands or repeated safe file identities.',
      privacyNote: 'Only loaded aggregate call fields are used.',
      evidence: calls.map((call, rowIndex) => evidenceFromCall(id, call, rowIndex, confidence)),
      evidenceCount: calls.length,
      impactScore: finding.credits + finding.share,
      source: 'Loaded aggregate fallback',
    };
  });
}

function cacheContextFinding(calls: CallRow[]): InvestigationFinding | null {
  const evidenceCalls = topCalls(calls.filter(call => call.cachedPct < 35 || (call.contextWindowPct ?? 0) >= 75), 8);
  if (!evidenceCalls.length) return null;
  const id = 'cache-context-pressure';
  return {
    id,
    title: 'Cache and context pressure',
    category: 'Cache/context',
    confidence: 'medium',
    tone: 'context',
    summary: `${evidenceCalls.length} loaded calls combine weak cache reuse or elevated context pressure.`,
    action: 'Inspect a high-token evidence call, preserve a concise handoff, and start fresh before cold context is resent.',
    verification: ['usage_large_low_output_calls', 'usage_thread_trace'],
    missingAccess: 'Aggregate evidence cannot determine whether the large context was necessary for output quality.',
    privacyNote: 'No prompt or raw tool output is included.',
    evidence: evidenceCalls.map((call, index) => evidenceFromCall(id, call, index, 'medium')),
    evidenceCount: evidenceCalls.length,
    impactScore: evidenceCalls.reduce((sum, call) => sum + call.totalTokens, 0) / 1_000,
    source: 'Loaded call aggregates',
  };
}

function evidenceFromCall(
  findingId: string,
  call: CallRow,
  index: number,
  confidence: InvestigationConfidence,
): InvestigationEvidenceRow {
  return {
    id: `${findingId}:call:${index}`,
    findingId,
    recordId: call.id,
    thread: call.thread,
    pattern: call.signal || call.tags[0] || 'aggregate call',
    events: 1,
    tokens: call.totalTokens,
    value: `${call.cachedPct.toFixed(1)}% cache · ${call.output.toLocaleString()} output`,
    confidence,
    action: call.recommendation || 'Open the call and verify whether the context and effort matched the task.',
    detail: `${call.model} · ${call.effort} · ${call.time}`,
    source: 'Loaded call aggregates',
  };
}

function dedupeFindings(findings: Array<InvestigationFinding | null>): InvestigationFinding[] {
  const seen = new Set<string>();
  return findings.filter(finding => {
    if (!finding) return false;
    const key = finding.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }) as InvestigationFinding[];
}

function impactFromSummary(summary: Record<string, unknown>, evidence: InvestigationEvidenceRow[], fallback: number): number {
  const tokens = numericValue(summary.total_tokens ?? summary.max_total_tokens);
  const events = numericValue(summary.total_occurrences ?? summary.total_call_count ?? fallback);
  return tokens / 1_000 + events * 10 + evidence.length;
}

function topCalls(calls: CallRow[], limit: number): CallRow[] {
  return [...calls].sort((left, right) => right.totalTokens - left.totalTokens || right.cost - left.cost).slice(0, limit);
}

function normalizeConfidence(value: string): InvestigationConfidence {
  const normalized = value.toLowerCase();
  if (normalized.includes('high') || normalized.includes('strong')) return 'high';
  if (normalized.includes('medium') || normalized.includes('possible')) return 'medium';
  return 'low';
}

function categoryForTitle(title: string): string {
  const normalized = title.toLowerCase();
  if (normalized.includes('shell') || normalized.includes('command')) return 'Shell churn';
  if (
    normalized.includes('file')
    || normalized.includes('rediscovery')
    || normalized.includes('read pattern')
    || normalized.includes('read-to-')
  ) return 'File rediscovery';
  if (normalized.includes('cache') || normalized.includes('context')) return 'Cache/context';
  if (normalized.includes('tool') || normalized.includes('output')) return 'Low output';
  if (normalized.includes('concentr')) return 'Concentration';
  return 'Usage driver';
}

function categoryForSnapshot(key: string): string {
  if (key === 'toolOutput') return 'Tool output';
  if (key === 'concentration') return 'Concentration';
  if (key === 'guidedSummary') return 'Guided summary';
  if (key === 'fileModifications') return 'File modifications';
  if (key === 'readProductivity') return 'Read productivity';
  return 'File rediscovery';
}

function titleForSnapshot(key: string): string {
  const titles: Record<string, string> = {
    toolOutput: 'Tool output pressure',
    fileReads: 'File read patterns',
    fileModifications: 'File modification concentration',
    readProductivity: 'Read-to-change productivity',
    concentration: 'Usage concentration',
    guidedSummary: 'Guided usage summary',
  };
  return titles[key] ?? 'Diagnostic evidence';
}

function actionForCategory(category: string): string {
  const normalized = category.toLowerCase();
  if (normalized.includes('shell') || normalized === 'commands') return 'Replace repeated inspection sequences with one scoped script or reusable task.';
  if (normalized.includes('file') || normalized.includes('read')) return 'Keep a short repository orientation note and reuse prior findings before reopening the same files.';
  if (normalized.includes('tool') || normalized.includes('output')) return 'Bound command output and summarize noisy tool results before the next model turn.';
  if (normalized.includes('cache') || normalized.includes('context')) return 'Use a concise handoff and start a fresh thread before a cold resume resends large context.';
  if (normalized.includes('concentr')) return 'Inspect the dominant thread before applying a broad workflow change.';
  return 'Open the strongest evidence row and verify the suspected waste before changing the workflow.';
}

function toneForFinding(title: string, confidence: InvestigationConfidence): InvestigationTone {
  if (title.toLowerCase().includes('no strong')) return 'neutral';
  if (title.toLowerCase().includes('cache') || title.toLowerCase().includes('context')) return 'context';
  return confidence === 'high' ? 'risk' : confidence === 'medium' ? 'caution' : 'neutral';
}

function toneForSnapshot(key: string): InvestigationTone {
  return key === 'concentration' ? 'caution' : key === 'guidedSummary' ? 'positive' : key === 'toolOutput' ? 'risk' : 'context';
}

function fingerprintSummary(findings: InvestigationFinding[]): string {
  if (!findings.length) return 'No diagnostic fingerprints are available.';
  const top = findings[0];
  return `${top.title} is the highest-ranked of ${findings.length} findings with ${top.evidenceCount} supporting rows.`;
}

function uniqueId(value: string, index: number): string {
  const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 56);
  return `${slug || 'finding'}-${index + 1}`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function numericValue(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}
