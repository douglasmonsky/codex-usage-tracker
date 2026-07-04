import type { DiagnosticFactCallsResult } from '../../api/diagnostics';

export const FACT_CALL_PAGE_SIZE = 8;

export function diagnosticFactKey(fact: { fact_type?: string | null; fact_name?: string | null }): string {
  return `${fact.fact_type ?? ''}\u0000${fact.fact_name ?? ''}`;
}

export function factCallsTotal(result: DiagnosticFactCallsResult): number {
  return Math.max(result.calls.length, Number(result.rawPayload.total_matched_rows ?? result.calls.length));
}

export function factCallsHasMore(result: DiagnosticFactCallsResult): boolean {
  return Boolean(result.rawPayload.truncated) && result.calls.length < factCallsTotal(result);
}

export function mergeFactCallResults(current: DiagnosticFactCallsResult, next: DiagnosticFactCallsResult): DiagnosticFactCallsResult {
  const calls = [...current.calls];
  const seen = new Set(calls.map(call => call.id).filter(Boolean));
  next.calls.forEach(call => {
    if (seen.has(call.id)) return;
    seen.add(call.id);
    calls.push(call);
  });

  const rows = [...(current.rawPayload.rows ?? [])];
  const seenRows = new Set(rows.map(row => row.record_id).filter(Boolean));
  (next.rawPayload.rows ?? []).forEach(row => {
    const recordId = row.record_id;
    if (recordId && seenRows.has(recordId)) return;
    if (recordId) seenRows.add(recordId);
    rows.push(row);
  });

  const total = Math.max(calls.length, Number(next.rawPayload.total_matched_rows ?? current.rawPayload.total_matched_rows ?? calls.length));
  return {
    calls,
    rawPayload: {
      ...next.rawPayload,
      rows,
      row_count: calls.length,
      total_matched_rows: total,
      truncated: calls.length < total,
    },
  };
}
