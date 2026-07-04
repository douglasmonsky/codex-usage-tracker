import { describe, expect, it } from 'vitest';
import { buildOverviewSeriesFromDailyValues } from './overviewSeries';

describe('buildOverviewSeriesFromDailyValues', () => {
  it('fills missing calendar dates between activity buckets', () => {
    const series = buildOverviewSeriesFromDailyValues([
      {
        timestamp: localNoonTimestamp(2026, 7, 1),
        cached: 50,
        cost: 1.25,
        input: 100,
        output: 25,
      },
      {
        timestamp: localNoonTimestamp(2026, 7, 4),
        cached: 100,
        cost: 4,
        input: 400,
        output: 50,
      },
    ]);

    expect(series.tokenSeries[0].points.map(point => point.label)).toEqual(['Jul 1', 'Jul 2', 'Jul 3', 'Jul 4']);
    expect(series.tokenSeries[0].points.map(point => point.value)).toEqual([100, 0, 0, 400]);
    expect(series.costSeries[0].points.map(point => point.value)).toEqual([1.25, 0, 0, 4]);
    expect(series.cacheSeries[0].points.map(point => point.value)).toEqual([50, 0, 0, 25]);
  });
});

function localNoonTimestamp(year: number, month: number, day: number): number {
  return new Date(year, month - 1, day, 12).getTime();
}
