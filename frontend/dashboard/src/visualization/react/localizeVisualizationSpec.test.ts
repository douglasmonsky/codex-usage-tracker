import { describe, expect, it } from 'vitest';

import type { CartesianVisualizationSpecV1 } from '../spec';
import { localizeVisualizationSpec } from './localizeVisualizationSpec';

const fixture: CartesianVisualizationSpecV1 = {
  schema: 'codex-usage-visualization/v1',
  id: 'localization-fixture',
  kind: 'cartesian',
  title: 'Recent token movement',
  description: 'Daily input',
  state: { kind: 'empty', message: 'No matching evidence' },
  scope: { label: 'All time', rowCount: 0 },
  freshness: { generatedAt: '2026-07-15T00:00:00Z' },
  caveats: ['Local data only'],
  accessibility: { summary: 'No data' },
  table: {
    caption: 'Token table',
    columns: [{ field: 'value', label: 'Total Tokens', type: 'number', unit: 'tokens' }],
  },
  data: { rows: [] },
  axes: {
    x: { field: 'date', label: 'Date', type: 'time' },
    y: { field: 'value', label: 'Total Tokens', type: 'number', unit: 'tokens' },
  },
  series: [{ id: 'total', label: 'Total Tokens', mark: 'line', xField: 'date', yField: 'value' }],
};

describe('localizeVisualizationSpec', () => {
  it('localizes chart, table, state, and accessibility labels while preserving data contracts', () => {
    const translations: Record<string, string> = {
      'Recent token movement': '近期token变化',
      'Daily input': '每日输入',
      'No matching evidence': '没有匹配的证据',
      'All time': '全部时间',
      'Local data only': '仅使用本地数据',
      'No data': '暂无数据',
      'Token table': 'token表',
      'Total Tokens': 'token总数',
      Date: '日期',
    };
    const localized = localizeVisualizationSpec(fixture, value => translations[value] ?? value);

    expect(localized.title).toBe('近期token变化');
    expect(localized.state).toEqual({ kind: 'empty', message: '没有匹配的证据' });
    expect(localized.table.columns[0].label).toBe('token总数');
    expect(localized.kind).toBe('cartesian');
    if (localized.kind === 'cartesian') {
      expect(localized.axes.x.label).toBe('日期');
      expect(localized.series[0].label).toBe('token总数');
      expect(localized.data).toBe(fixture.data);
    }
  });

  it('localizes known categorical UI values while preserving user identity fields', () => {
    const categorical: CartesianVisualizationSpecV1 = {
      ...fixture,
      data: { rows: [{ id: 'one', finding: 'Tool output pressure', thread: 'Overview' }] },
      table: {
        ...fixture.table,
        columns: [
          { field: 'finding', label: 'Finding', type: 'category' },
          { field: 'thread', label: 'Thread', type: 'text' },
        ],
      },
    };
    const localized = localizeVisualizationSpec(categorical, value => ({
      'Tool output pressure': '工具输出压力',
      Overview: '概览',
    })[value] ?? value);

    expect(localized.kind).toBe('cartesian');
    if (localized.kind === 'cartesian') {
      expect(localized.data.rows[0].finding).toBe('工具输出压力');
      expect(localized.data.rows[0].thread).toBe('Overview');
    }
  });
});
