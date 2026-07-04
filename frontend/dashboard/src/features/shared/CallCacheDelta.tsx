import type { CallRow } from '../../api/types';
import { formatNumber, pct } from './format';

export function CallCacheDelta({ call, calls }: { call: CallRow; calls: CallRow[] }) {
  const chronologicalCalls = [...calls, call]
    .filter((row, index, rows) => rows.findIndex(candidate => candidate.id === row.id) === index)
    .sort(compareCallTimeAscending);
  const selectedIndex = chronologicalCalls.findIndex(row => row.id === call.id);
  const previous = selectedIndex > 0 ? chronologicalCalls[selectedIndex - 1] : null;
  const delta = previous ? callAccountingDelta(call, previous) : null;
  const diagnostic = cacheDiagnostic(call, previous);

  return (
    <div className="call-cache-delta-card composition-card">
      <div className="composition-head">
        <strong>Cache Accounting Delta</strong>
        <span>{previous ? `Call ${selectedIndex + 1} of ${chronologicalCalls.length}` : 'No previous call'}</span>
      </div>
      <CacheVerdict
        call={call}
        delta={delta}
        diagnostic={diagnostic}
        previous={previous}
        selectedIndex={selectedIndex}
        totalCalls={chronologicalCalls.length}
      />
      {previous && delta ? (
        <>
          <p className="diagnostic-interpretation">{deltaInterpretation(delta)}</p>
          <div className="cache-delta-grid">
            <DeltaMetric
              label="Last call input"
              value={signedNumber(delta.input)}
              detail={`${formatNumber(previous.input)} -> ${formatNumber(call.input)}`}
            />
            <DeltaMetric
              label="Cached input"
              value={signedNumber(delta.cached)}
              detail={`${formatNumber(previous.cachedInput)} -> ${formatNumber(call.cachedInput)}`}
            />
            <DeltaMetric
              label="Uncached input"
              value={signedNumber(delta.uncached)}
              detail={`${formatNumber(previous.uncachedInput)} -> ${formatNumber(call.uncachedInput)}`}
            />
            <DeltaMetric
              label="Output"
              value={signedNumber(delta.output)}
              detail={`${formatNumber(previous.output)} -> ${formatNumber(call.output)}`}
            />
            <DeltaMetric
              label="Reasoning output"
              value={signedNumber(delta.reasoning)}
              detail={`${formatNumber(previous.reasoningOutput)} -> ${formatNumber(call.reasoningOutput)}`}
            />
            <DeltaMetric
              label="Cache ratio"
              value={signedPctPoints(delta.cacheRatio)}
              detail={`${pct(previous.cachedPct)} -> ${pct(call.cachedPct)}`}
            />
          </div>
        </>
      ) : (
        <p className="empty-state">No previous aggregate call available for cache delta accounting.</p>
      )}
    </div>
  );
}

type AccountingDelta = {
  input: number;
  cached: number;
  uncached: number;
  output: number;
  reasoning: number;
  cacheRatio: number;
};

type CacheDiagnosticKey = 'cold' | 'partial' | 'spike' | 'warm';

type CacheDiagnostic = {
  key: CacheDiagnosticKey;
  label: string;
  body: string;
};

function CacheVerdict({
  call,
  delta,
  diagnostic,
  previous,
  selectedIndex,
  totalCalls,
}: {
  call: CallRow;
  delta: AccountingDelta | null;
  diagnostic: CacheDiagnostic;
  previous: CallRow | null;
  selectedIndex: number;
  totalCalls: number;
}) {
  return (
    <div className={`cache-verdict-card cache-verdict-${diagnostic.key}`}>
      <div className="cache-verdict-main">
        <span className="cache-diagnostic-pill">{diagnostic.label}</span>
        <p>{diagnostic.body}</p>
      </div>
      <div className="cache-verdict-meta">
        <span>Cache ratio: {pct(call.cachedPct)}</span>
        <span>{delta ? cacheDeltaLine(delta) : 'No previous call loaded for delta comparison.'}</span>
        <span>Position: {selectedIndex + 1} of {totalCalls}</span>
        <span>Next: {diagnosticNextStep(call, diagnostic, previous)}</span>
      </div>
    </div>
  );
}

function cacheDiagnostic(call: CallRow, previous: CallRow | null): CacheDiagnostic {
  const diagnostic = classifyCacheDiagnostic(call, previous);
  if (diagnostic === 'spike') {
    return {
      key: 'spike',
      label: 'Uncached spike',
      body: 'Fresh input rose sharply compared with the previous call in this resolved thread.',
    };
  }
  if (diagnostic === 'warm') {
    return {
      key: 'warm',
      label: 'Warm cache reuse',
      body: 'Most input tokens reused prompt cache. The uncached portion is the most likely investigation target.',
    };
  }
  if (diagnostic === 'partial') {
    return {
      key: 'partial',
      label: 'Partial cache miss',
      body: 'Some prefix reused cache, but a meaningful share of input was fresh or reserialized.',
    };
  }
  return {
    key: 'cold',
    label: 'Cold resume / stale cache',
    body: 'Conversation-specific cache likely expired or missed; remaining cache is probably stable Codex scaffolding or tool schema prefix.',
  };
}

function classifyCacheDiagnostic(call: CallRow, previous: CallRow | null): CacheDiagnosticKey {
  const cache = cacheRatio(call);
  const previousCache = previous ? cacheRatio(previous) : null;
  const previousUncached = previous?.uncachedInput ?? 0;
  const coldRatio = 0.05;
  const warmRatio = 0.85;
  const previousWarmRatio = 0.8;
  const significantTokens = 1_000;

  if (previous && previousCache !== null && previousCache >= previousWarmRatio && cache <= coldRatio && call.input >= significantTokens) {
    return 'cold';
  }
  if (previous && call.uncachedInput > Math.max(previousUncached * 2, significantTokens)) {
    return 'spike';
  }
  if (cache >= warmRatio) return 'warm';
  if (cache > coldRatio) return 'partial';
  return 'cold';
}

function cacheRatio(call: CallRow): number {
  return Number.isFinite(call.cachedPct) ? call.cachedPct / 100 : 0;
}

function cacheDeltaLine(delta: AccountingDelta): string {
  return `Uncached input: ${signedNumber(delta.uncached)}. Cached input: ${signedNumber(delta.cached)}. Cache ratio: ${signedPctPoints(delta.cacheRatio)}.`;
}

function diagnosticNextStep(call: CallRow, diagnostic: CacheDiagnostic, previous: CallRow | null): string {
  if (diagnostic.key === 'cold') {
    return 'Compare the previous call, then inspect loaded evidence to see what fresh context was sent after the cache miss.';
  }
  if (diagnostic.key === 'spike') {
    return 'Inspect the most recent evidence entries first; the spike is in fresh uncached input, not cached history.';
  }
  if (diagnostic.key === 'warm') {
    return `Cache reuse is healthy; focus on ${formatNumber(call.uncachedInput)} uncached tokens that were still billed as fresh input.`;
  }
  if (previous) {
    return 'Use delta cards to locate whether the change came from cached input, uncached input, or output/reasoning.';
  }
  return 'Use loaded evidence if aggregate totals are not enough to understand this isolated call.';
}

function callAccountingDelta(call: CallRow, previous: CallRow): AccountingDelta {
  return {
    input: call.input - previous.input,
    cached: call.cachedInput - previous.cachedInput,
    uncached: call.uncachedInput - previous.uncachedInput,
    output: call.output - previous.output,
    reasoning: call.reasoningOutput - previous.reasoningOutput,
    cacheRatio: call.cachedPct - previous.cachedPct,
  };
}

function deltaInterpretation(delta: AccountingDelta): string {
  if (delta.uncached > 0 && delta.cached < 0) {
    return `Uncached input rose by ${formatNumber(delta.uncached)} while cached input fell by ${formatNumber(Math.abs(delta.cached))}.`;
  }
  if (delta.uncached > 0) {
    return `Uncached input increased by ${formatNumber(delta.uncached)} versus the previous aggregate call.`;
  }
  if (delta.uncached < 0 && delta.cached >= 0) {
    return `Uncached input decreased by ${formatNumber(Math.abs(delta.uncached))} while cached input increased.`;
  }
  return 'Cache accounting is stable versus the previous aggregate call.';
}

function DeltaMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <span className="cache-delta-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
    </span>
  );
}

function signedNumber(value: number): string {
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '-'}${formatNumber(Math.abs(value))}`;
}

function signedPctPoints(value: number): string {
  if (value === 0) return '0.0pp';
  return `${value > 0 ? '+' : '-'}${Math.abs(value).toFixed(1)}pp`;
}

function compareCallTimeAscending(left: CallRow, right: CallRow): number {
  return callTimestamp(left) - callTimestamp(right);
}

function callTimestamp(call: CallRow): number {
  const parsed = Date.parse(call.rawTime || call.time);
  return Number.isFinite(parsed) ? parsed : 0;
}
