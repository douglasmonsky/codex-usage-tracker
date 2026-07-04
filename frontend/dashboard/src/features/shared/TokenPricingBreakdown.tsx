import type { CallRow } from '../../api/types';
import { formatNumber, money } from './format';

export function TokenPricingBreakdown({ call }: { call: CallRow }) {
  return (
    <dl className="detail-list">
      <DetailRow label="Last call total" value={formatNumber(call.totalTokens)} />
      <DetailRow label="Last call input" value={formatNumber(call.input)} />
      <DetailRow label="Cached input" value={formatNumber(call.cachedInput)} />
      <DetailRow label="Output tokens" value={formatNumber(call.output)} />
      <DetailRow label="Reasoning output" value={formatNumber(call.reasoningOutput)} />
      <DetailRow label="Session cumulative" value={call.cumulativeTotalTokens ? formatNumber(call.cumulativeTotalTokens) : 'Not reported'} />
      <DetailRow label="Pricing model" value={pricingModelLabel(call)} />
      <DetailRow label="Credit model" value={call.usageCreditModel || 'No mapped rate'} />
      <DetailRow label="Credit confidence" value={call.usageCreditConfidence || 'unknown'} />
      <DetailRow label="Credit source" value={call.usageCreditSource || 'None'} />
      <DetailRow label="Credit source fetched" value={call.usageCreditFetchedAt || 'Unknown'} />
      <DetailRow label="Credit tier" value={call.usageCreditTier || 'Unknown'} />
      <DetailRow label="Cache savings" value={money(call.estimatedCacheSavings)} />
      <DetailRow label="Efficiency signals" value={efficiencySignalText(call)} />
    </dl>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function pricingModelLabel(call: CallRow): string {
  if (call.pricingModel) return call.pricingModel;
  if (call.cost <= 0) return 'No configured price';
  return call.pricingEstimated ? 'Best-guess estimate' : 'Configured price';
}

function efficiencySignalText(call: CallRow): string {
  if (call.efficiencyFlags.length) return call.efficiencyFlags.join(', ');
  if (call.signal && call.signal !== 'aggregate') return call.signal;
  if (call.recommendation) return 'recommendation';
  return 'None';
}
