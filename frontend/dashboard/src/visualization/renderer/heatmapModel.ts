import type { HeatmapVisualizationSpecV1, VisualizationRecord, VisualizationValue } from '../spec';
import { baseOption, brushOptions, selectionKey, targetKey, toolboxOptions } from './modelShared';
import type { EChartsVisualizationModel, VisualizationSelectionTarget } from './modelTypes';
import { trackerVisualizationPalette } from './theme';

export function buildHeatmapModel(spec: HeatmapVisualizationSpecV1, animate: boolean): EChartsVisualizationModel {
  const targetByKey = new Map<string, VisualizationSelectionTarget>();
  const keyByTarget = new Map<string, string>();
  const selectionField = spec.interactions?.selection?.keyField;
  const xCategories = uniqueValues(spec.data.rows.map(row => row[spec.encoding.x.field]));
  const yCategories = uniqueValues(spec.data.rows.map(row => row[spec.encoding.y.field]));
  const data = spec.data.rows.map((row, dataIndex) => {
    const key = selectionKey(row, selectionField, dataIndex);
    const target = { seriesIndex: 0, dataIndex };
    targetByKey.set(key, target);
    keyByTarget.set(targetKey(target), key);
    return {
      value: [row[spec.encoding.x.field], row[spec.encoding.y.field], row[spec.encoding.value.field]],
      selectionKey: key,
    };
  });

  const brush = brushOptions(spec);
  const toolbox = toolboxOptions(spec);
  return {
    option: {
      ...baseOption(spec, animate),
      grid: {
        top: 32,
        right: 90,
        bottom: 56,
        left: 120,
        outerBoundsMode: 'same',
        outerBoundsContain: 'axisLabel',
      },
      xAxis: { type: 'category', data: xCategories, name: spec.encoding.x.label, nameLocation: 'middle', nameGap: 38 },
      yAxis: { type: 'category', data: yCategories, name: spec.encoding.y.label, nameLocation: 'middle', nameGap: 92 },
      visualMap: {
        min: spec.encoding.min ?? 0,
        max: spec.encoding.max ?? maxNumericValue(spec.data.rows, spec.encoding.value.field),
        orient: 'vertical',
        right: 4,
        top: 'middle',
        calculable: true,
        inRange: { color: ['#eef1f5', '#9db9f6', '#2f6fed', '#c84652'] },
      },
      ...(brush ? { brush } : {}),
      ...(toolbox ? { toolbox } : {}),
      series: [{
        id: spec.id,
        name: spec.encoding.value.label,
        type: 'heatmap',
        data,
        label: { show: true, color: trackerVisualizationPalette.ink },
        emphasis: { itemStyle: { borderColor: trackerVisualizationPalette.ink, borderWidth: 2 } },
      }],
      media: [{
        query: { maxWidth: 520 },
        option: {
          grid: { top: 48, right: 44, bottom: 82, left: 116, outerBoundsMode: 'none' },
          xAxis: { axisLabel: { interval: 0, rotate: 28 } },
          yAxis: { axisLabel: { width: 104, overflow: 'truncate' } },
          visualMap: {
            orient: 'vertical',
            left: null,
            right: 4,
            top: 'middle',
            bottom: null,
            calculable: false,
            itemWidth: 10,
            itemHeight: 120,
          },
        },
      }],
    },
    targetByKey,
    keyByTarget,
  };
}

function uniqueValues(values: VisualizationValue[]) {
  return [...new Set(values.map(value => String(value ?? 'Not available')))];
}

function maxNumericValue(rows: VisualizationRecord[], field: string) {
  return Math.max(1, ...rows.map(row => (typeof row[field] === 'number' ? row[field] : 0)));
}
