import type { DiagnosticFactRow, DiagnosticFactsPayload, DiagnosticSnapshotPayload } from '../../api/diagnostics';

export type ToolEvidenceRow = {
  id: string;
  factType: string;
  name: string;
  category: string;
  occurrences: number;
  associatedCalls: number;
  cachedInputTokens: number;
  uncachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
  totalTokens: number;
  cachePct: number;
  largestCallTokens: number;
  latestEventTimestamp: string;
  representativeRecordId: string;
  actionHint: string;
  source: DiagnosticFactRow;
};

export type FileEvidenceRow = {
  id: string;
  pathHash: string;
  pathLabel: string;
  readEvents: number;
  allocatedOutputTokens: number;
  modificationEvents: number;
  readRecordId: string;
  modificationRecordId: string;
  representativeRecordId: string;
};

export function toolEvidenceRows(payload?: DiagnosticFactsPayload | null): ToolEvidenceRow[] {
  return (payload?.rows ?? []).map((row, index) => {
    const factType = text(row.fact_type) || 'tool';
    const name = text(row.fact_name) || `Tool ${index + 1}`;
    return {
      id: `${factType}:${name}`,
      factType,
      name,
      category: text(row.fact_category) || 'tool activity',
      occurrences: number(row.occurrences),
      associatedCalls: number(row.associated_calls),
      cachedInputTokens: number(row.associated_cached_input_tokens),
      uncachedInputTokens: number(row.associated_uncached_input_tokens),
      outputTokens: number(row.associated_output_tokens),
      reasoningOutputTokens: number(row.associated_reasoning_output_tokens),
      totalTokens: number(row.associated_total_tokens),
      cachePct: percent(row.avg_cache_ratio),
      largestCallTokens: number(row.largest_call_tokens),
      latestEventTimestamp: text(row.latest_event_timestamp),
      representativeRecordId: text(row.largest_record_id),
      actionHint: text(row.action_hint),
      source: row,
    };
  });
}

export function fileEvidenceRows(
  reads?: DiagnosticSnapshotPayload | null,
  modifications?: DiagnosticSnapshotPayload | null,
): FileEvidenceRow[] {
  const merged = new Map<string, FileEvidenceRow>();
  for (const row of records(reads?.top_paths)) {
    const pathHash = text(row.path_hash);
    const pathLabel = text(row.path_label) || 'Unknown path';
    const id = pathHash || `label:${pathLabel}`;
    merged.set(id, {
      id,
      pathHash,
      pathLabel,
      readEvents: number(row.read_events),
      allocatedOutputTokens: number(row.allocated_output_token_sum),
      modificationEvents: 0,
      readRecordId: text(row.representative_record_id),
      modificationRecordId: '',
      representativeRecordId: text(row.representative_record_id),
    });
  }
  for (const row of records(modifications?.top_paths)) {
    const pathHash = text(row.path_hash);
    const pathLabel = text(row.path_label) || 'Unknown path';
    const id = pathHash || `label:${pathLabel}`;
    const existing = merged.get(id);
    const modificationRecordId = text(row.representative_record_id);
    merged.set(id, {
      id,
      pathHash,
      pathLabel,
      readEvents: existing?.readEvents ?? 0,
      allocatedOutputTokens: existing?.allocatedOutputTokens ?? 0,
      modificationEvents: number(row.modification_events),
      readRecordId: existing?.readRecordId ?? '',
      modificationRecordId,
      representativeRecordId: existing?.representativeRecordId || modificationRecordId,
    });
  }
  return [...merged.values()].sort((left, right) =>
    right.allocatedOutputTokens - left.allocatedOutputTokens
      || right.readEvents - left.readEvents
      || right.modificationEvents - left.modificationEvents
      || left.pathLabel.localeCompare(right.pathLabel),
  );
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
    : [];
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function number(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function percent(value: unknown): number {
  const parsed = number(value);
  return parsed <= 1 ? parsed * 100 : parsed;
}
