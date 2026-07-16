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
  fast: boolean | null;
  serviceTierConfidence: string;
  fastProxyCandidate: boolean;
};

export function serviceTierLabel(call: ServiceTierInput): 'Fast' | 'Standard' | 'Unknown' {
  if (call.fast === true) return 'Fast';
  if (call.fast === false) return 'Standard';
  return 'Unknown';
}

export function serviceTierDetail(call: ServiceTierInput): string {
  if (call.fast !== null) {
    return `confirmed ${serviceTierLabel(call)} · ${call.serviceTierConfidence || 'exact'}`;
  }
  return call.fastProxyCandidate
    ? 'tier unknown · Fast proxy candidate'
    : 'tier unknown · normal throughput proxy';
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
