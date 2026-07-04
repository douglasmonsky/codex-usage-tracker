import type { DashboardModel } from './types';

type DailySeriesValue = {
  timestamp: number;
  cached: number;
  cost: number;
  input: number;
  output: number;
};

type DailyBucket = {
  label: string;
  timestamp: number;
  cached: number;
  cost: number;
  input: number;
  output: number;
};

export function buildOverviewSeriesFromDailyValues(
  values: DailySeriesValue[],
): Pick<DashboardModel, 'tokenSeries' | 'costSeries' | 'cacheSeries'> {
  const buckets = new Map<string, DailyBucket>();
  for (const value of values) {
    if (!Number.isFinite(value.timestamp)) continue;
    const key = localDayKey(value.timestamp);
    const bucket =
      buckets.get(key) ??
      ({
        label: formatSeriesDate(value.timestamp),
        timestamp: localDayTimestamp(value.timestamp),
        cached: 0,
        cost: 0,
        input: 0,
        output: 0,
      } satisfies DailyBucket);
    bucket.cached += value.cached;
    bucket.cost += value.cost;
    bucket.input += value.input;
    bucket.output += value.output;
    buckets.set(key, bucket);
  }

  const points = fillDailyGaps(buckets);
  if (!points.length) return { tokenSeries: [], costSeries: [], cacheSeries: [] };

  return {
    tokenSeries: [
      { id: 'input', label: 'Input', color: '#2563eb', points: points.map(point => ({ label: point.label, value: point.input })) },
      { id: 'output', label: 'Output', color: '#059669', points: points.map(point => ({ label: point.label, value: point.output })) },
      {
        id: 'cached',
        label: 'Cached',
        color: '#7c3aed',
        dashed: true,
        points: points.map(point => ({ label: point.label, value: point.cached })),
      },
    ],
    costSeries: [
      { id: 'cost', label: 'Estimated Cost', color: '#f59e0b', points: points.map(point => ({ label: point.label, value: point.cost })) },
    ],
    cacheSeries: [
      {
        id: 'cache',
        label: 'Cache hit %',
        color: '#2563eb',
        points: points.map(point => ({
          label: point.label,
          value: point.input > 0 ? (point.cached / point.input) * 100 : 0,
        })),
      },
    ],
  };
}

function fillDailyGaps(buckets: Map<string, DailyBucket>): DailyBucket[] {
  const sorted = [...buckets.values()].sort((left, right) => left.timestamp - right.timestamp);
  const first = sorted.at(0);
  const last = sorted.at(-1);
  if (!first || !last) return [];

  const points: DailyBucket[] = [];
  for (const date = new Date(first.timestamp); date.getTime() <= last.timestamp; date.setDate(date.getDate() + 1)) {
    const timestamp = date.getTime();
    const key = localDayKey(timestamp);
    points.push(
      buckets.get(key) ?? {
        label: formatSeriesDate(timestamp),
        timestamp,
        cached: 0,
        cost: 0,
        input: 0,
        output: 0,
      },
    );
  }
  return points;
}

function localDayKey(timestamp: number): string {
  const date = new Date(timestamp);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function localDayTimestamp(timestamp: number): number {
  const date = new Date(timestamp);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function formatSeriesDate(timestamp: number): string {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(timestamp));
}
