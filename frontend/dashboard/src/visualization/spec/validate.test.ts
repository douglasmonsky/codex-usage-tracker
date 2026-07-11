import { describe, expect, it } from 'vitest';

import { visualizationSpecSchema, type CartesianVisualizationSpecV1 } from './types';
import { assertVisualizationSpec, validateVisualizationSpec } from './validate';
import { tableRowsForVisualization } from './table';
import { visualizationAriaDescription } from './accessibility';

const validSpec: CartesianVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'weekly-allowance',
  title: 'Weekly allowance estimate',
  state: { kind: 'ready' },
  scope: { label: 'All local history', rowCount: 2, historyScope: 'all' },
  freshness: { generatedAt: '2026-07-10T12:00:00Z', sourceRevision: 'fixture-v1' },
  accessibility: {
    summary: 'Estimated weekly credits declined between the two observed windows.',
    keyboardInstructions: 'Use the left and right arrow keys to move between windows.',
  },
  table: {
    caption: 'Weekly allowance evidence',
    columns: [
      { field: 'window', label: 'Window', type: 'time' },
      { field: 'credits', label: 'Estimated credits', type: 'number', unit: 'credits', align: 'right' },
    ],
  },
  interactions: { selection: { keyField: 'id', labelField: 'window' }, zoom: { axis: 'x' } },
  annotations: [{ id: 'candidate', label: 'Candidate change', kind: 'reference-line', axis: 'x', value: '2026-07-07' }],
  kind: 'cartesian',
  data: {
    rows: [
      { id: 'w1', window: '2026-06-30', credits: 111, low: 104, high: 118 },
      { id: 'w2', window: '2026-07-07', credits: 91, low: 85, high: 97 },
    ],
  },
  axes: {
    x: { field: 'window', label: 'Weekly window', type: 'time', unit: 'timestamp' },
    y: { field: 'credits', label: 'Estimated credits', type: 'number', unit: 'credits', min: 0 },
  },
  series: [
    {
      id: 'estimate',
      label: 'Estimated credits',
      mark: 'line',
      xField: 'window',
      yField: 'credits',
      lowerField: 'low',
      upperField: 'high',
    },
  ],
};

describe('VisualizationSpecV1', () => {
  it('accepts a semantic chart with confidence and table contracts', () => {
    expect(validateVisualizationSpec(validSpec)).toEqual([]);
    expect(assertVisualizationSpec(validSpec)).toBe(validSpec);
  });

  it('rejects renderer-shaped or missing semantic fields through referenced-field validation', () => {
    const invalid = {
      ...validSpec,
      series: [{ ...validSpec.series[0], yField: 'echartsOption' }],
      table: { ...validSpec.table, defaultSort: { field: 'missing', direction: 'desc' as const } },
    };

    expect(validateVisualizationSpec(invalid)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: 'series.0' }),
        expect.objectContaining({ path: 'table.defaultSort.field' }),
      ]),
    );
  });

  it('requires table-equivalent data for ready, partial, and stale states', () => {
    const invalid = { ...validSpec, data: { rows: [] } };
    expect(validateVisualizationSpec(invalid)).toContainEqual({
      path: 'data',
      message: 'ready visualizations must include table-equivalent data',
    });
  });

  it('keeps selection keys and accessible summaries synchronized with table rows', () => {
    expect(tableRowsForVisualization(validSpec).map(row => row.key)).toEqual(['w1', 'w2']);
    expect(visualizationAriaDescription(validSpec)).toContain('2 table rows available');
    expect(visualizationAriaDescription(validSpec)).toContain('left and right arrow keys');
  });
});
