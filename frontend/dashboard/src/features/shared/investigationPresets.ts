import type { CallRow, DashboardModel } from '../../api/types';
import type { ViewId } from '../../app/navigation';
import { formatCompact, formatNumber, money, pct } from './format';

export type InvestigationPresetKey =
  | 'highest-cost'
  | 'context-bloat'
  | 'cache-misses'
  | 'pricing-gaps'
  | 'codex-credits'
  | 'reasoning-spike';

export type InvestigationPresetAction = {
  presetKey: InvestigationPresetKey;
  view: ViewId;
  query?: string;
};

export type InvestigationPresetCard = InvestigationPresetAction & {
  label: string;
  description: string;
  count: number;
  value: string;
  primaryRecordId?: string;
  primaryLabel: string;
};

const presetLabels: Record<InvestigationPresetKey, string> = {
  'highest-cost': 'Highest Cost Threads',
  'context-bloat': 'Context Bloat',
  'cache-misses': 'Cache Misses',
  'pricing-gaps': 'Pricing Gaps',
  'codex-credits': 'Codex Credits',
  'reasoning-spike': 'Reasoning Spike',
};

export function buildInvestigationPresetCards(model: DashboardModel): InvestigationPresetCard[] {
  const cacheMisses = callsForPreset(model.calls, 'cache-misses');
  const contextBloat = callsForPreset(model.calls, 'context-bloat');
  const pricingGaps = callsForPreset(model.calls, 'pricing-gaps');
  const creditCalls = callsForPreset(model.calls, 'codex-credits');
  const reasoningCalls = callsForPreset(model.calls, 'reasoning-spike');
  const topThread = topThreadByCost(model.calls);
  return [
    {
      presetKey: 'highest-cost',
      view: 'threads',
      query: topThread?.thread,
      label: 'Highest Cost Threads',
      description: 'Open thread concentration and cost-per-call review.',
      count: topThread?.calls.length ?? 0,
      value: topThread ? money(topThread.cost) : '$0.00',
      primaryLabel: topThread?.thread ?? 'No thread',
    },
    presetCard('context-bloat', 'calls', 'Context Bloat', 'Calls near context-window pressure or very large token totals.', contextBloat),
    presetCard('cache-misses', 'calls', 'Cache Misses', 'Large uncached inputs and weak cache reuse candidates.', cacheMisses),
    presetCard('pricing-gaps', 'calls', 'Pricing Gaps', 'Estimated or missing pricing confidence rows.', pricingGaps),
    presetCard('codex-credits', 'calls', 'Codex Credits', 'Rows with the highest estimated Codex credit impact.', creditCalls),
    presetCard('reasoning-spike', 'calls', 'Reasoning Spike', 'Calls with concentrated reasoning output.', reasoningCalls),
  ];
}

export function callsForPreset(calls: CallRow[], presetKey: string): CallRow[] {
  return calls.filter(call => callMatchesInvestigationPreset(call, presetKey)).sort((left, right) => {
    if (presetKey === 'cache-misses') {
      return right.uncachedInput - left.uncachedInput || left.cachedPct - right.cachedPct;
    }
    if (presetKey === 'context-bloat') {
      return Number(right.contextWindowPct ?? 0) - Number(left.contextWindowPct ?? 0) || right.totalTokens - left.totalTokens;
    }
    if (presetKey === 'codex-credits') {
      return right.credits - left.credits || right.totalTokens - left.totalTokens;
    }
    if (presetKey === 'reasoning-spike') {
      return right.reasoningOutput - left.reasoningOutput || right.totalTokens - left.totalTokens;
    }
    return right.totalTokens - left.totalTokens || right.cost - left.cost;
  });
}

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

function presetCard(
  presetKey: InvestigationPresetKey,
  view: ViewId,
  label: string,
  description: string,
  calls: CallRow[],
): InvestigationPresetCard {
  const top = calls[0];
  return {
    presetKey,
    view,
    label,
    description,
    count: calls.length,
    value: valueForPreset(presetKey, calls),
    primaryRecordId: top?.id,
    primaryLabel: top ? `${top.thread} / ${top.model}` : 'No matching call',
  };
}

function valueForPreset(presetKey: InvestigationPresetKey, calls: CallRow[]): string {
  if (!calls.length) {
    return '0';
  }
  if (presetKey === 'cache-misses') {
    return `${formatCompact(calls[0].uncachedInput)} uncached`;
  }
  if (presetKey === 'context-bloat') {
    return calls[0].contextWindowPct === null ? formatCompact(calls[0].totalTokens) : pct(calls[0].contextWindowPct);
  }
  if (presetKey === 'codex-credits') {
    return formatNumber(calls.reduce((sum, call) => sum + call.credits, 0));
  }
  if (presetKey === 'reasoning-spike') {
    return formatCompact(calls[0].reasoningOutput);
  }
  return formatCompact(calls[0].totalTokens);
}

function topThreadByCost(calls: CallRow[]): { thread: string; calls: CallRow[]; cost: number } | null {
  const groups = new Map<string, CallRow[]>();
  for (const call of calls) {
    groups.set(call.thread, [...(groups.get(call.thread) ?? []), call]);
  }
  return (
    [...groups.entries()]
      .map(([thread, groupCalls]) => ({
        thread,
        calls: groupCalls,
        cost: groupCalls.reduce((sum, call) => sum + call.cost, 0),
      }))
      .sort((left, right) => right.cost - left.cost)[0] ?? null
  );
}
