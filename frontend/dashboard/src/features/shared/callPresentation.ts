import { formatCompact, pct } from './format';

type CacheStateInput = {
  cachedPct: number;
};

type SourceLineInput = {
  sourceFile?: string | null;
  lineNumber?: number | null;
};

type ContextWindowInput = {
  contextWindowPct?: number | null;
  modelContextWindow?: number | null;
};

type TopCountStyle = 'parenthetical' | 'x';

type ServiceTierInput = {
  serviceTier: string;
  fast: boolean | null;
  serviceTierConfidence: string;
  fastProxyCandidate: boolean;
};

type BillingBasisInput = {
  billingBasis: string;
  pricingServiceTier: string;
};

const knownServiceTierLabels: Record<string, string> = {
  priority: 'Priority / Fast',
  fast: 'Fast',
  default: 'Default / Standard',
  standard: 'Standard',
  flex: 'Flex',
  batch: 'Batch',
};

function exactServiceTierLabel(value: string): string | null {
  const normalized = value.trim().toLowerCase().replace(/[\s_]+/g, '-');
  if (!normalized) return null;
  const known = knownServiceTierLabels[normalized];
  if (known) return known;
  if (normalized.length > 48 || !/^[a-z0-9.-]+$/.test(normalized)) return 'Other';
  return normalized
    .split(/[-.]+/)
    .filter(Boolean)
    .map(part => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}

export function serviceTierLabel(call: ServiceTierInput): string {
  const exactLabel = exactServiceTierLabel(call.serviceTier);
  if (exactLabel) return exactLabel;
  if (call.fast === true) return 'Fast';
  if (call.fast === false) return 'Standard';
  return 'Unknown';
}

export function serviceTierDetail(call: ServiceTierInput): string {
  if (exactServiceTierLabel(call.serviceTier)) {
    return `observed ${serviceTierLabel(call)} · ${call.serviceTierConfidence || 'exact'}`;
  }
  if (call.fast !== null) {
    return `confirmed ${serviceTierLabel(call)} · ${call.serviceTierConfidence || 'exact'}`;
  }
  return call.fastProxyCandidate
    ? 'tier unknown · Fast proxy candidate'
    : 'tier unknown · normal throughput proxy';
}

export function billingBasisDetail(call: BillingBasisInput): string {
  if (call.billingBasis === 'api_tokens') {
    const tier = call.pricingServiceTier.trim();
    const label = tier
      ? `${tier.charAt(0).toUpperCase()}${tier.slice(1).toLowerCase()} rates`
      : 'configured rates';
    return `API token estimate · ${label}`;
  }
  if (call.billingBasis === 'chatgpt_credits') {
    return 'API-equivalent scenario · ChatGPT credits selected';
  }
  return 'API-equivalent scenario · billing basis unknown';
}

export function cacheState(call: CacheStateInput): string {
  if (call.cachedPct < 25) return 'cold or weak cache';
  if (call.cachedPct < 50) return 'partial cache reuse';
  return 'healthy cache reuse';
}

export function sourceLine(call: SourceLineInput): string {
  if (!call.sourceFile) return 'Not available';
  return `${call.sourceFile}${call.lineNumber ? `:${call.lineNumber}` : ''}`;
}

export function contextWindowLabel(call: ContextWindowInput): string {
  if (call.contextWindowPct === null || call.contextWindowPct === undefined) return 'Not reported';
  const windowSize = call.modelContextWindow ? ` of ${formatCompact(call.modelContextWindow)}` : '';
  return `${pct(call.contextWindowPct)}${windowSize}`;
}

export function summarizeTopCounts(
  values: string[],
  {
    limit = 2,
    emptyLabel = 'No related calls',
    unknownLabel = 'Unknown',
    style = 'parenthetical',
  }: {
    limit?: number;
    emptyLabel?: string;
    unknownLabel?: string;
    style?: TopCountStyle;
  } = {},
): string {
  const counts = new Map<string, number>();
  for (const value of values) {
    const key = value || unknownLabel;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const labels = [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([value, count]) => (style === 'x' ? `${value} x${count}` : `${value} (${count})`));
  return labels.length ? labels.join(', ') : emptyLabel;
}
