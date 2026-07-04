import type { CallRow } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import { formatCompact, pct } from './format';

type CallDecision = {
  allowanceImpact: string;
  contextUse: string;
  nextAction: string;
  pricingStatus: string;
  whyFlagged: string;
};

export function CallDecisionCard({ call }: { call: CallRow }) {
const shellI18n = useShellI18n();
const decision = callDecision(call);
  return (
    <div className="call-decision-card">
      <div className="section-heading compact">
        <h3>Call Decision</h3>
        <span>{decision.nextAction}</span>
      </div>
      <dl className="detail-list compact">
        <div>
          <dt>Pricing status</dt>
          <dd>{decision.pricingStatus}</dd>
        </div>
<div>
<dt>{shellI18n.t('detail.next_action', 'Next action')}</dt>
<dd>{decision.nextAction}</dd>
</div>
        <div>
          <dt>Why flagged</dt>
          <dd>{decision.whyFlagged}</dd>
        </div>
        <div>
          <dt>Allowance impact</dt>
          <dd>{decision.allowanceImpact}</dd>
        </div>
        <div>
          <dt>Context use</dt>
          <dd>{decision.contextUse}</dd>
        </div>
      </dl>
    </div>
  );
}

function callDecision(call: CallRow): CallDecision {
  return {
    allowanceImpact: `${formatCredits(call.credits)} counted`,
    contextUse: call.contextWindowPct == null ? 'Not reported' : pct(call.contextWindowPct),
    nextAction: callNextAction(call),
    pricingStatus: callPricingStatus(call),
    whyFlagged: whyFlagged(call),
  };
}

function callPricingStatus(call: CallRow): string {
  if (call.cost <= 0) return 'No configured price';
  return call.pricingEstimated ? 'Best-guess estimate' : 'Configured price';
}

function callNextAction(call: CallRow): string {
  if (call.recommendation) return call.recommendation;
  if (call.cost <= 0) return 'Configure pricing';
  if (call.cachedPct < 30 && call.input > 0) return 'Compare fresh input';
  if ((call.contextWindowPct ?? 0) >= 60) return 'Inspect thread timeline';
  if (call.reasoningOutput > call.output) return 'Review reasoning effort';
  return 'Use aggregate first';
}

function whyFlagged(call: CallRow): string {
  if (call.recommendation) return call.recommendation;
  if (call.signal && call.signal !== 'aggregate') return `${call.signal} aggregate signal`;
  if ((call.contextWindowPct ?? 0) >= 60) return 'High reported context use.';
  if (call.cachedPct < 30 && call.input > 0) return `${formatCompact(call.uncachedInput)} uncached input with weak cache reuse.`;
  if (call.reasoningOutput > call.output) return 'Reasoning output exceeds visible output.';
  if (call.cost > 0 || call.credits > 0) return 'Review cost and credit impact before loading raw context.';
  return 'No aggregate efficiency flag on this row.';
}

function formatCredits(value: number): string {
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)} credits`;
}
