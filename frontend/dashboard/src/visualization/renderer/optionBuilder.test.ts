import { describe, expect, it } from 'vitest';

import { allowanceChangePointSpec, evidenceLedgerSpec, tokenFlowSpec, wasteMatrixSpec } from '../fixtures';
import { buildEChartsVisualizationModel } from './optionBuilder';

describe('ECharts visualization adapter', () => {
  it('builds confidence bands, annotations, zoom, and deterministic selection targets', () => {
    const model = buildEChartsVisualizationModel(allowanceChangePointSpec);
    const option = model.option as Record<string, unknown>;
    const series = option.series as Array<Record<string, unknown>>;

    expect(series.map(item => item.id)).toEqual(['estimate-confidence-low', 'estimate-confidence-band', 'estimate']);
    expect(series[2].markLine).toBeTruthy();
    expect(series[2].markArea).toBeTruthy();
    expect(series[2].markLine).toMatchObject({ data: [{ label: { width: 88, overflow: 'break' } }] });
    expect(series[2].markArea).toMatchObject({ label: { position: 'insideTopLeft', width: 80 } });
    expect(option.dataZoom).toHaveLength(2);
    expect(option.media).toEqual([{ query: { maxWidth: 520 }, option: { grid: { top: 88 } } }]);
    expect(model.targetByKey.get('week-07-07')).toEqual({ seriesIndex: 2, dataIndex: 7 });
  });

  it('keeps flow-link selection keys table-equivalent', () => {
    const model = buildEChartsVisualizationModel(tokenFlowSpec);
    const option = model.option as Record<string, unknown>;
    const [series] = option.series as Array<Record<string, unknown>>;

    expect(model.targetByKey.get('flow-3')).toEqual({ seriesIndex: 0, dataIndex: 2, dataType: 'edge' });
    expect(model.keyByTarget.get('0:2:edge')).toBe('flow-3');
    expect(series.right).toBeGreaterThanOrEqual(100);
  });

  it('builds heatmap categories and a bounded visual scale', () => {
    const option = buildEChartsVisualizationModel(wasteMatrixSpec).option as Record<string, unknown>;
    expect((option.xAxis as { data: string[] }).data).toEqual(['File rediscovery', 'Shell churn', 'Low output']);
    expect((option.yAxis as { data: string[] }).data).toHaveLength(5);
    expect(option.visualMap).toMatchObject({ min: 0, max: 100 });
    expect(option.media).toEqual([{
      query: { maxWidth: 520 },
      option: expect.objectContaining({
        grid: { top: 48, right: 44, bottom: 82, left: 116, outerBoundsMode: 'none' },
        visualMap: expect.objectContaining({ orient: 'vertical', right: 4 }),
      }),
    }]);
  });

  it('keeps long evidence labels visible with responsive horizontal bars', () => {
    const option = buildEChartsVisualizationModel(evidenceLedgerSpec).option as Record<string, unknown>;
    const yAxis = option.yAxis as Record<string, unknown>;
    const media = option.media as Array<{ option: { grid: Record<string, unknown>; yAxis: Record<string, unknown> } }>;
    const [series] = option.series as Array<{ data: Array<{ value: [number, string] }> }>;

    expect(option.xAxis).toMatchObject({ type: 'value', name: 'Impact score' });
    expect(yAxis).toMatchObject({ type: 'category', name: 'Finding', inverse: true, axisLabel: { width: 190, overflow: 'truncate' } });
    expect(series.data[0].value).toEqual([94, 'Repeated file rediscovery']);
    expect(media[0].option.grid).toMatchObject({ left: 140, right: 20, outerBoundsMode: 'none' });
    expect(media[0].option.yAxis).toMatchObject({ name: '', axisLabel: { width: 124, overflow: 'truncate' } });
  });
});
