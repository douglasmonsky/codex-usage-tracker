import type { DiagnosticFactRow } from '../../api/diagnostics';
import type { CallRow } from '../../api/types';

export function factFromCalls(factType: string, factName: string, calls: CallRow[]): DiagnosticFactRow {
  const largest = [...calls].sort((left, right) => right.totalTokens - left.totalTokens)[0];
  const associatedInput = calls.reduce((sum, call) => sum + call.input, 0);
  const associatedCached = calls.reduce((sum, call) => sum + Math.round(call.input * (call.cachedPct / 100)), 0);
  return {
    fact_type: factType,
    fact_name: factName,
    fact_category: 'react-fallback',
    occurrences: calls.length,
    associated_calls: calls.length,
    associated_input_tokens: associatedInput,
    associated_cached_input_tokens: associatedCached,
    associated_uncached_input_tokens: calls.reduce((sum, call) => sum + call.uncachedInput, 0),
    associated_output_tokens: calls.reduce((sum, call) => sum + call.output, 0),
    associated_reasoning_output_tokens: calls.reduce((sum, call) => sum + call.reasoningOutput, 0),
    associated_total_tokens: calls.reduce((sum, call) => sum + call.totalTokens, 0),
    avg_cache_ratio: associatedInput ? associatedCached / associatedInput : 0,
    largest_call_tokens: largest?.totalTokens ?? 0,
    largest_record_id: largest?.id ?? null,
    latest_event_timestamp: largest?.rawTime || largest?.time || null,
    action_hint: 'Open associated aggregate calls in the full Call Investigator.',
  };
}

export function numericFactField(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}
