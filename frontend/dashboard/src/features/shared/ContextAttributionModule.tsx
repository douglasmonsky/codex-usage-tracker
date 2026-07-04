import type { CallContextPayload, CallRow } from '../../api/types';
import { formatNumber } from './format';

type ContextAttributionStats = {
  visibleChars: number;
  visibleTokenEstimate: number;
  serializedTokens: number;
  serializedChars: number;
  serializedLineCount: number;
  serializedEstimator: string;
  serializedBound: number;
  visibleGap: number;
  serializedCandidate: number;
  remainingAfterSerialized: number;
  serializedDeferred: boolean;
  serializedBuckets: Array<{
    key?: string;
    label?: string;
    note?: string;
    count?: number;
    char_count?: number;
    token_estimate?: number;
  }>;
};

export function ContextAttributionModule({
call,
payload,
onRunFullAnalysis,
showHeading = true,
}: {
call: CallRow;
payload: CallContextPayload | null;
onRunFullAnalysis?: () => void;
showHeading?: boolean;
}) {
  const stats = contextAttributionStats(call, payload);
  return (
    <div className="context-attribution-module">
      {showHeading ? (
        <div className="serialized-breakdown-heading context-attribution-heading">
          <strong>Context Attribution</strong>
          <span>Estimated from visible log volume</span>
        </div>
      ) : null}
      <div className="drilldown-metric-grid wide context-attribution-grid">
        <ContextMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="exact aggregate row" />
        <ContextMetric
          label="Visible new context estimate"
          value={stats ? `~${formatNumber(stats.visibleTokenEstimate)}` : 'Not loaded yet'}
          detail={stats ? `${formatNumber(stats.visibleChars)} analyzed chars` : 'Runtime evidence'}
        />
        <ContextMetric
          label="Serialized local upper bound"
          value={stats?.serializedTokens ? `~${formatNumber(stats.serializedBound)}` : 'Not loaded yet'}
          detail={stats?.serializedTokens ? serializedDetail(stats) : 'Runtime evidence'}
        />
        <ContextMetric
          label="Unexplained hidden/serialized input estimate"
          value={stats ? `~${formatNumber(stats.visibleGap)}` : 'Not loaded yet'}
          detail={stats ? 'uncached input minus visible estimate' : 'Runtime evidence'}
        />
        <ContextMetric
          label="Possible serialized overhead"
          value={stats ? `~${formatNumber(stats.serializedCandidate)}` : 'Not loaded yet'}
          detail={stats ? 'serialized upper bound minus visible estimate' : 'Runtime evidence'}
        />
        <ContextMetric
          label="Remaining after serialized bound"
          value={stats ? `~${formatNumber(stats.remainingAfterSerialized)}` : 'Not loaded yet'}
          detail={stats ? 'not covered by serialized upper bound' : 'Runtime evidence'}
        />
      </div>
<SerializedEvidenceBreakdown stats={stats} onRunFullAnalysis={payload?.context_mode === 'full' ? undefined : onRunFullAnalysis} />
      <p className="privacy-note">
        Compare exact uncached input with tokenizer-counted visible log evidence. Treat the gap as hidden scaffolding,
        serialization, or tokenizer estimate error.
      </p>
    </div>
  );
}

function ContextMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <span className="drilldown-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
    </span>
  );
}

function SerializedEvidenceBreakdown({
  stats,
  onRunFullAnalysis,
}: {
stats: ContextAttributionStats | null;
onRunFullAnalysis?: () => void;
}) {
  if (!stats?.serializedTokens) return null;
  if (stats.serializedDeferred) {
    return (
      <div className="serialized-breakdown deferred">
        <div className="serialized-breakdown-heading">
          <strong>Serialized evidence groups</strong>
          <span>Fast estimate loaded; full serialized grouping is deferred.</span>
        </div>
        {onRunFullAnalysis ? (
          <div className="context-followup-actions">
            <button className="toolbar-button serialized-action" type="button" onClick={onRunFullAnalysis}>
              Run full serialized analysis
            </button>
          </div>
        ) : null}
      </div>
    );
  }
  const buckets = stats.serializedBuckets.slice(0, 6);
  return (
    <div className="serialized-breakdown">
      <div className="serialized-breakdown-heading">
        <strong>Serialized evidence groups</strong>
        <span>Upper-bound local JSONL structure; not exact prompt text.</span>
      </div>
      <div className="serialized-bucket-grid">
        {buckets.length ? (
          buckets.map(bucket => (
            <div className="serialized-bucket" key={bucket.key ?? bucket.label ?? String(bucket.token_estimate ?? 0)}>
              <span>{bucket.label || bucket.key || 'Unknown'}</span>
              <strong>{formatNumber(Number(bucket.token_estimate ?? 0))}</strong>
              <small>
                {formatNumber(Number(bucket.count ?? 0))} fields · {formatNumber(Number(bucket.char_count ?? 0))} chars
              </small>
              {bucket.note ? <small>{bucket.note}</small> : null}
            </div>
          ))
        ) : (
          <p className="empty-state">No serialized evidence groups returned.</p>
        )}
      </div>
    </div>
  );
}

function serializedDetail(stats: ContextAttributionStats) {
  const detailParts = [`${formatNumber(stats.serializedChars)} raw JSON chars`, stats.serializedEstimator];
  if (stats.serializedDeferred) detailParts.push('fast estimate');
  if (stats.serializedLineCount) detailParts.push(`${formatNumber(stats.serializedLineCount)} raw lines`);
  return detailParts.join(' · ');
}

function contextAttributionStats(call: CallRow, payload: CallContextPayload | null): ContextAttributionStats | null {
  if (!payload) return null;
  const entries = payload.entries ?? [];
  const visibleChars = Number(payload.visible_char_count ?? entries.reduce((sum, entry) => sum + String(entry.text ?? '').length, 0));
  const visibleTokenEstimate = Number(payload.visible_token_estimate ?? Math.ceil(visibleChars / 4));
  const serialized = payload.serialized_evidence ?? {};
  const serializedTokens = Number(serialized.raw_json_token_estimate ?? serialized.token_estimate ?? 0);
  const serializedChars = Number(serialized.raw_json_char_count ?? serialized.total_chars ?? 0);
  const serializedLineCount = Number(serialized.raw_line_count ?? 0);
  const serializedEstimator = serialized.token_estimator || payload.visible_token_estimator || 'chars_per_4_fallback';
  const serializedBuckets = Array.isArray(serialized.buckets) ? serialized.buckets : [];
  const serializedBound = serializedTokens > 0 ? Math.min(serializedTokens, call.uncachedInput) : 0;
  const visibleGap = Math.max(call.uncachedInput - visibleTokenEstimate, 0);
  const serializedCandidate = serializedBound > visibleTokenEstimate ? serializedBound - visibleTokenEstimate : 0;
  const remainingAfterSerialized =
    serializedTokens > 0 ? Math.max(call.uncachedInput - Math.max(visibleTokenEstimate, serializedBound), 0) : visibleGap;
  return {
    visibleChars,
    visibleTokenEstimate,
    serializedTokens,
    serializedChars,
    serializedLineCount,
    serializedEstimator,
    serializedBound,
    visibleGap,
    serializedCandidate,
    remainingAfterSerialized,
    serializedDeferred: Boolean(serialized.deferred || serialized.deferred_buckets),
    serializedBuckets,
  };
}
