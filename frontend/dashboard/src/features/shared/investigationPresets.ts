import type { CallRow } from '../../api/types';

type InvestigationPresetKey =
  | 'highest-cost'
  | 'context-bloat'
  | 'cache-misses'
  | 'pricing-gaps'
  | 'codex-credits'
  | 'reasoning-spike';

const presetLabels: Record<InvestigationPresetKey, string> = {
  'highest-cost': 'Highest Cost Threads',
  'context-bloat': 'Context Bloat',
  'cache-misses': 'Cache Misses',
  'pricing-gaps': 'Pricing Gaps',
  'codex-credits': 'Codex Credits',
  'reasoning-spike': 'Reasoning Spike',
};

export function callMatchesInvestigationPreset(call: CallRow, presetKey: string): boolean {
  if (presetKey === 'context-bloat') {
    return Number(call.contextWindowPct ?? 0) >= 60 || call.totalTokens >= 200_000;
  }
  if (presetKey === 'cache-misses') {
    return call.signal === 'cache-risk' || call.cachedPct < 30 || call.uncachedInput >= 50_000;
  }
  if (presetKey === 'pricing-gaps') {
    return call.pricingEstimated || !Number.isFinite(call.cost);
  }
  if (presetKey === 'codex-credits') {
    return call.credits > 0;
  }
  if (presetKey === 'reasoning-spike') {
    return call.reasoningOutput > 0;
  }
  return true;
}

export function presetLabel(presetKey: string): string {
  return presetLabels[presetKey as InvestigationPresetKey] ?? presetKey;
}
