import type { ShellI18n } from '../../app/i18n';
import type { CallContextPayload, CallRow } from '../../api/types';
import type { ContextLoadState } from '../shared/contextEvidenceState';
import { formatNumber, pct } from '../shared/format';

export function exactReadoutBody(call: CallRow, shellI18n: ShellI18n): string {
  return formatI18nTemplate(
    shellI18n.t(
      'call.readout.exact_body',
      '{input} input tokens = {cached} cached + {uncached} uncached; {output} output tokens; {cache} cache reuse.',
    ),
    {
      input: formatNumber(call.input),
      cached: formatNumber(call.cachedInput),
      uncached: formatNumber(call.uncachedInput),
      output: formatNumber(call.output),
      cache: pct(call.cachedPct),
    },
  );
}

export function previousUnavailableReadout(shellI18n: ShellI18n): string {
  return shellI18n.t(
    'call.readout.previous_unavailable',
    'No previous call is loaded in resolved thread, call-to-call deltas unavailable.',
  );
}

export function previousCallReadout(call: CallRow, previous: CallRow): string {
  const uncached = call.uncachedInput - previous.uncachedInput;
  const cached = call.cachedInput - previous.cachedInput;
  if (uncached > 0 && cached < 0) {
    return `Fresh input rose by ${formatNumber(uncached)} while cached input fell by ${formatNumber(Math.abs(cached))}; classic cache-drop profile.`;
  }
  if (uncached > 0) {
    return `Fresh input increased by ${formatNumber(uncached)} from previous call; inspect evidence new files, tool results, or rewritten context.`;
  }
  if (uncached < 0 && cached >= 0) {
    return `Fresh input fell by ${formatNumber(Math.abs(uncached))} while cached input increased, so this call reused context more efficiently previous one.`;
  }
  return 'Token accounting broadly stable compared previous call in resolved thread.';
}

export function evidenceStateReadout(state: ContextLoadState, shellI18n: ShellI18n): string {
  if (state.status === 'loaded') {
    const entries = state.payload.entries?.length ?? 0;
    const visibleChars = Number(state.payload.visible_char_count ?? 0);
    const visibleTokens = Number(state.payload.visible_token_estimate ?? 0);
    const serializedDetail = serializedEvidenceReadoutDetail(state.payload, shellI18n);
    return formatI18nTemplate(
      shellI18n.t(
        'call.readout.evidence_analyzed',
        'Evidence analyzed: {totalEntries} selected-turn entries, {visibleChars} visible redacted chars, {visibleTokens} visible tokens.{serializedDetail}',
      ),
      {
        totalEntries: formatNumber(entries),
        visibleChars: formatNumber(visibleChars),
        visibleTokens: formatNumber(visibleTokens),
        estimator: state.payload.visible_token_estimator ?? 'visible-token estimate',
        serializedDetail,
        renderedEntries: formatNumber(entries),
      },
    );
  }
  if (state.status === 'loading') {
    return shellI18n.t('call.readout.evidence_loading', state.message);
  }
  if (state.status === 'error') {
    return `Evidence request failed: ${state.message}`;
  }
  return 'Evidence is not loaded yet. Aggregate token counts are exact, but visible-context attribution needs runtime evidence.';
}

export function serializedEvidenceReadoutDetail(payload: CallContextPayload, shellI18n: ShellI18n): string {
  const serialized = payload.serialized_evidence ?? {};
  if (serialized.deferred || serialized.deferred_buckets) {
    return shellI18n.t(
      'call.readout.evidence_serialized_deferred',
      'Fast serialized estimate only; full serialized grouping deferred.',
    );
  }
  const serializedTokens = serializedTokenEstimate(payload);
  if (serializedTokens <= 0) return '';
  return formatI18nTemplate(
    shellI18n.t('call.readout.evidence_serialized_bound', ' Serialized local upper bound: {tokens} tokens.'),
    {
      tokens: formatNumber(serializedTokens),
      chars: formatNumber(Number(serialized.raw_json_char_count ?? serialized.total_chars ?? 0)),
    },
  );
}

export function nextDiagnosticMove(call: CallRow, previous: CallRow | null): string {
  const cache = call.input > 0 ? call.cachedInput / call.input : call.cachedPct / 100;
  const previousCache = previous && previous.input > 0 ? previous.cachedInput / previous.input : previous ? previous.cachedPct / 100 : null;
  const previousUncached = previous?.uncachedInput ?? 0;
  if (previous && previousCache !== null && previousCache >= 0.8 && cache <= 0.05 && call.input >= 1_000) {
    return 'Compare previous call, then inspect loaded evidence see fresh context was sent after cache miss.';
  }
  if (previous && call.uncachedInput > Math.max(previousUncached * 2, 1_000)) {
    return 'Inspect most recent evidence entries first; spike is in fresh uncached input, not cached history.';
  }
  if (cache >= 0.85) {
    return `Cache reuse is healthy; focus on ${formatNumber(call.uncachedInput)} uncached tokens were still billed as fresh input.`;
  }
  if (previous) {
    return 'Use delta cards to locate whether change came from cached input, uncached input, or output/reasoning.';
  }
  return 'Use loaded evidence if aggregate totals are not enough understand this isolated call.';
}

export function readoutPositionDetail(positionLabel: string): string {
  return positionLabel === 'Hydrated from /api/call'
    ? 'Position: hydrated live record outside loaded snapshot'
    : `Position: ${positionLabel}`;
}

export function formatI18nTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key) => values[key] ?? match);
}

function serializedTokenEstimate(payload: CallContextPayload): number {
  const serialized = payload.serialized_evidence ?? {};
  return Number(serialized.raw_json_token_estimate ?? serialized.token_estimate ?? 0);
}
