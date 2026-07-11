import type { CallRow } from '../../api/types';
import type {
  UsageConstellationLegendItem,
  UsageConstellationLink,
  UsageConstellationModel,
  UsageConstellationPoint,
} from '../../visualization/three/types';

const DEFAULT_POINT_LIMIT = 800;
const MAX_LEGEND_MODELS = 5;
const MODEL_COLORS = ['#55d6be', '#5aa9ff', '#f6c85f', '#ef6f6c', '#a78bfa'] as const;
const OTHER_MODEL_COLOR = '#93a4b8';

type IndexedCall = {
  call: CallRow;
  chronologyIndex: number;
  timestampMs: number;
  wastePressure: number;
};

export function buildUsageConstellationModel(
  calls: readonly CallRow[],
  pointLimit = DEFAULT_POINT_LIMIT,
): UsageConstellationModel {
  const normalizedLimit = Math.max(3, Math.floor(pointLimit));
  const ordered = calls
    .map((call, sourceIndex) => ({
      call,
      sourceIndex,
      timestampMs: finiteTimestamp(call.eventTimestamp, sourceIndex),
    }))
    .sort((left, right) => left.timestampMs - right.timestampMs || left.call.id.localeCompare(right.call.id))
    .map((entry, chronologyIndex): IndexedCall => ({
      call: entry.call,
      chronologyIndex,
      timestampMs: entry.timestampMs,
      wastePressure: callWastePressure(entry.call),
    }));

  if (!ordered.length) {
    return {
      accessibleSummary: 'No loaded calls are available for the usage constellation.',
      legend: [],
      links: [],
      points: [],
      sampled: false,
      totalCalls: 0,
    };
  }

  const selected = selectRepresentativeCalls(ordered, normalizedLimit);
  const colorModel = buildModelColors(ordered);
  const tokenLogs = selected.map(entry => Math.log1p(Math.max(0, entry.call.totalTokens)));
  const minTokenLog = Math.min(...tokenLogs);
  const maxTokenLog = Math.max(...tokenLogs);
  const firstTimestamp = ordered[0].timestampMs;
  const lastTimestamp = ordered.at(-1)?.timestampMs ?? firstTimestamp;

  const points = selected.map((entry): UsageConstellationPoint => {
    const tokenScale = normalize(Math.log1p(Math.max(0, entry.call.totalTokens)), minTokenLog, maxTokenLog);
    const timeScale = normalize(entry.timestampMs, firstTimestamp, lastTimestamp);
    const cachedPercent = clamp(entry.call.cachedPct, 0, 100);
    const modelColor = colorModel.colors.get(entry.call.model) ?? OTHER_MODEL_COLOR;
    return {
      cachedPercent,
      color: modelColor,
      credits: Math.max(0, entry.call.credits),
      effort: entry.call.effort || 'unknown',
      id: entry.call.id,
      model: entry.call.model || 'unknown',
      position: [
        lerp(-7.5, 7.5, timeScale),
        lerp(0.45, 5.2, tokenScale),
        lerp(-4.2, 4.2, cachedPercent / 100),
      ],
      recordId: entry.call.id,
      size: lerp(8, 20, tokenScale),
      thread: entry.call.thread || 'Unassigned thread',
      threadKey: entry.call.threadKey || entry.call.thread || entry.call.id,
      timestamp: entry.call.eventTimestamp,
      totalTokens: Math.max(0, entry.call.totalTokens),
      wastePressure: entry.wastePressure,
    };
  });
  const links = buildThreadLinks(points);

  return {
    accessibleSummary: buildAccessibleSummary(points, ordered.length),
    legend: colorModel.legend,
    links,
    points,
    sampled: points.length < ordered.length,
    totalCalls: ordered.length,
  };
}

function selectRepresentativeCalls(ordered: readonly IndexedCall[], limit: number): IndexedCall[] {
  if (ordered.length <= limit) return [...ordered];

  const anchorCount = Math.max(2, Math.floor(limit * 0.18));
  const selected = new Map<number, IndexedCall>();
  const add = (entry: IndexedCall | undefined) => {
    if (entry) selected.set(entry.chronologyIndex, entry);
  };
  add(ordered[0]);
  add(ordered.at(-1));

  [...ordered]
    .sort((left, right) => right.call.totalTokens - left.call.totalTokens || left.chronologyIndex - right.chronologyIndex)
    .slice(0, anchorCount)
    .forEach(add);
  [...ordered]
    .sort((left, right) => right.wastePressure - left.wastePressure || left.chronologyIndex - right.chronologyIndex)
    .slice(0, anchorCount)
    .forEach(add);

  if (selected.size >= limit) {
    return [...selected.values()]
      .slice(0, limit)
      .sort((left, right) => left.chronologyIndex - right.chronologyIndex);
  }

  const remainingSlots = Math.max(0, limit - selected.size);
  for (let slot = 0; slot < remainingSlots; slot += 1) {
    const index = Math.round((slot / Math.max(1, remainingSlots - 1)) * (ordered.length - 1));
    add(ordered[index]);
  }
  for (const entry of ordered) {
    if (selected.size >= limit) break;
    add(entry);
  }

  return [...selected.values()].sort((left, right) => left.chronologyIndex - right.chronologyIndex);
}

function buildModelColors(ordered: readonly IndexedCall[]): {
  colors: Map<string, string>;
  legend: UsageConstellationLegendItem[];
} {
  const counts = new Map<string, number>();
  ordered.forEach(({ call }) => {
    const model = call.model || 'unknown';
    counts.set(model, (counts.get(model) ?? 0) + 1);
  });
  const ranked = [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
  const colors = new Map<string, string>();
  const legend: UsageConstellationLegendItem[] = ranked.slice(0, MAX_LEGEND_MODELS).map(([label, count], index) => {
    const color = MODEL_COLORS[index];
    colors.set(label, color);
    return { color, count, label };
  });
  const otherCount = ranked.slice(MAX_LEGEND_MODELS).reduce((sum, [, count]) => sum + count, 0);
  if (otherCount) legend.push({ color: OTHER_MODEL_COLOR, count: otherCount, label: 'Other models' });
  return { colors, legend };
}

function buildThreadLinks(points: readonly UsageConstellationPoint[]): UsageConstellationLink[] {
  const previousByThread = new Map<string, number>();
  const links: UsageConstellationLink[] = [];
  points.forEach((point, targetIndex) => {
    const sourceIndex = previousByThread.get(point.threadKey);
    if (sourceIndex !== undefined) links.push({ sourceIndex, targetIndex });
    previousByThread.set(point.threadKey, targetIndex);
  });
  return links;
}

function buildAccessibleSummary(points: readonly UsageConstellationPoint[], totalCalls: number): string {
  const largest = [...points].sort((left, right) => right.totalTokens - left.totalTokens)[0];
  const lowestCache = [...points].sort((left, right) => left.cachedPercent - right.cachedPercent)[0];
  const sampleLabel = points.length < totalCalls
    ? `${points.length.toLocaleString()} representative calls from ${totalCalls.toLocaleString()} loaded calls`
    : `${totalCalls.toLocaleString()} loaded calls`;
  return `The constellation plots ${sampleLabel}. The largest plotted call used ${largest.totalTokens.toLocaleString()} tokens. The lowest plotted cache reuse was ${Math.round(lowestCache.cachedPercent)} percent.`;
}

function callWastePressure(call: CallRow): number {
  const total = Math.max(1, call.totalTokens);
  const uncachedShare = clamp(call.uncachedInput / total, 0, 1);
  const usefulOutputShare = clamp((call.output + call.reasoningOutput) / total, 0, 1);
  return clamp((uncachedShare * 0.75) + ((1 - usefulOutputShare) * 0.25), 0, 1);
}

function finiteTimestamp(value: string, fallbackIndex: number): number {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : fallbackIndex;
}

function normalize(value: number, minimum: number, maximum: number): number {
  if (maximum <= minimum) return 0.5;
  return clamp((value - minimum) / (maximum - minimum), 0, 1);
}

function lerp(start: number, end: number, ratio: number): number {
  return start + ((end - start) * ratio);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
}
