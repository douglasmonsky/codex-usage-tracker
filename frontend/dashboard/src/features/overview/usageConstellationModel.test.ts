import { describe, expect, it } from 'vitest';

import type { CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { buildUsageConstellationModel } from './usageConstellationModel';

describe('usage constellation model', () => {
  it('maps loaded calls onto deterministic bounded semantic axes', () => {
    const result = buildUsageConstellationModel(fixtureModel.calls);

    expect(result.points).toHaveLength(fixtureModel.calls.length);
    expect(result.sampled).toBe(false);
    expect(result.accessibleSummary).toContain('largest plotted call');
    result.points.forEach(point => {
      expect(point.position[0]).toBeGreaterThanOrEqual(-7.5);
      expect(point.position[0]).toBeLessThanOrEqual(7.5);
      expect(point.position[1]).toBeGreaterThanOrEqual(0.45);
      expect(point.position[1]).toBeLessThanOrEqual(5.2);
      expect(point.position[2]).toBeGreaterThanOrEqual(-4.2);
      expect(point.position[2]).toBeLessThanOrEqual(4.2);
    });
  });

  it('retains chronological edges and high-token outliers in a large deterministic sample', () => {
    const calls = Array.from({ length: 1_200 }, (_, index) => syntheticCall(index));
    calls[777] = { ...calls[777], totalTokens: 9_000_000, uncachedInput: 8_900_000 };

    const first = buildUsageConstellationModel(calls, 120);
    const second = buildUsageConstellationModel(calls, 120);

    expect(first.points).toHaveLength(120);
    expect(first.sampled).toBe(true);
    expect(first.points.map(point => point.id)).toEqual(second.points.map(point => point.id));
    expect(first.points.map(point => point.id)).toEqual(expect.arrayContaining(['call-0', 'call-777', 'call-1199']));
  });

  it('never exceeds a deliberately small point budget', () => {
    const calls = Array.from({ length: 20 }, (_, index) => syntheticCall(index));

    const result = buildUsageConstellationModel(calls, 3);

    expect(result.points).toHaveLength(3);
    expect(result.points.map(point => point.id)).toEqual(expect.arrayContaining(['call-0', 'call-19']));
  });

  it('uses cache reuse for depth and produces only valid sampled thread links', () => {
    const calls = [
      syntheticCall(0, { cachedPct: 0, threadKey: 'shared' }),
      syntheticCall(1, { cachedPct: 100, threadKey: 'shared' }),
      syntheticCall(2, { cachedPct: 50, threadKey: 'other' }),
    ];
    const result = buildUsageConstellationModel(calls);

    expect(result.points[0].position[2]).toBe(-4.2);
    expect(result.points[1].position[2]).toBe(4.2);
    expect(result.links).toEqual([{ sourceIndex: 0, targetIndex: 1 }]);
    result.links.forEach(link => {
      expect(result.points[link.sourceIndex].threadKey).toBe(result.points[link.targetIndex].threadKey);
    });
  });
});

function syntheticCall(index: number, overrides: Partial<CallRow> = {}): CallRow {
  const base = fixtureModel.calls[index % fixtureModel.calls.length];
  return {
    ...base,
    id: `call-${index}`,
    eventTimestamp: new Date(Date.UTC(2026, 0, 1, 0, index)).toISOString(),
    thread: `Thread ${index % 12}`,
    threadKey: `thread-${index % 12}`,
    totalTokens: 1_000 + index,
    uncachedInput: 600 + index,
    cachedPct: index % 101,
    ...overrides,
  };
}
