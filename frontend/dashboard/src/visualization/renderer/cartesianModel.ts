import type {
  CartesianVisualizationSpecV1,
  VisualizationAnnotation,
  VisualizationValue,
} from '../spec';
import { baseOption, brushOptions, selectionKey, targetKey, toolboxOptions } from './modelShared';
import type { EChartsVisualizationModel, VisualizationSelectionTarget } from './modelTypes';
import { trackerVisualizationPalette } from './theme';

export function buildCartesianModel(spec: CartesianVisualizationSpecV1, animate: boolean): EChartsVisualizationModel {
  const series: Array<Record<string, unknown>> = [];
  const targetByKey = new Map<string, VisualizationSelectionTarget>();
  const keyByTarget = new Map<string, string>();
  const selectionField = spec.interactions?.selection?.keyField;

  for (const seriesSpec of spec.series) {
    if (seriesSpec.lowerField && seriesSpec.upperField) {
      const confidenceStack = `confidence-${seriesSpec.id}`;
      series.push({
        id: `${seriesSpec.id}-confidence-low`,
        type: 'line',
        data: spec.data.rows.map(row => [row[seriesSpec.xField], row[seriesSpec.lowerField as string]]),
        stack: confidenceStack,
        symbol: 'none',
        silent: true,
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
      });
      series.push({
        id: `${seriesSpec.id}-confidence-band`,
        type: 'line',
        data: spec.data.rows.map(row => [
          row[seriesSpec.xField],
          numericDifference(row[seriesSpec.upperField as string], row[seriesSpec.lowerField as string]),
        ]),
        stack: confidenceStack,
        symbol: 'none',
        silent: true,
        lineStyle: { opacity: 0 },
        areaStyle: { color: seriesSpec.color ?? trackerVisualizationPalette.selection, opacity: 0.16 },
      });
    }

    const seriesIndex = series.length;
    const data = spec.data.rows.map((row, dataIndex) => {
      const key = selectionKey(row, selectionField, dataIndex);
      const target = { seriesIndex, dataIndex };
      if (!targetByKey.has(key)) targetByKey.set(key, target);
      keyByTarget.set(targetKey(target), key);
      return {
        value: [row[seriesSpec.xField], row[seriesSpec.yField]],
        selectionKey: key,
        itemStyle: seriesSpec.color ? { color: seriesSpec.color } : undefined,
      };
    });
    series.push({
      id: seriesSpec.id,
      name: seriesSpec.label,
      type: markToSeriesType(seriesSpec.mark),
      data,
      smooth: seriesSpec.smooth,
      stack: seriesSpec.stack,
      symbolSize: seriesSpec.mark === 'point' ? 12 : 7,
      showSymbol: seriesSpec.mark !== 'line' || spec.data.rows.length <= 24,
      emphasis: { focus: 'series', scale: 1.35 },
      lineStyle: seriesSpec.color ? { color: seriesSpec.color, width: 3 } : { width: 3 },
      itemStyle: seriesSpec.color ? { color: seriesSpec.color } : undefined,
      ...annotationOptions(spec.annotations ?? []),
    });
  }

  const legend = spec.series.length > 1 ? { top: 4, left: 8 } : null;
  const dataZoom = dataZoomOptions(spec);
  const brush = brushOptions(spec);
  const toolbox = toolboxOptions(spec);
  return {
    option: {
      ...baseOption(spec, animate),
      grid: {
        top: 52,
        right: 28,
        bottom: spec.interactions?.zoom ? 78 : 48,
        left: 64,
        outerBoundsMode: 'same',
        outerBoundsContain: 'axisLabel',
      },
      ...(legend ? { legend } : {}),
      xAxis: axisOption(spec.axes.x, 'x'),
      yAxis: axisOption(spec.axes.y, 'y'),
      ...(dataZoom ? { dataZoom } : {}),
      ...(brush ? { brush } : {}),
      ...(toolbox ? { toolbox } : {}),
      series,
      media: [{ query: { maxWidth: 520 }, option: mobileCartesianOption(spec) }],
    },
    targetByKey,
    keyByTarget,
  };
}

function axisOption(axis: CartesianVisualizationSpecV1['axes']['x'], orientation: 'x' | 'y') {
  const isCategory = axis.type === 'category' || axis.type === 'text';
  return {
    type: axis.type === 'time' ? 'time' : isCategory ? 'category' : 'value',
    name: axis.label,
    nameLocation: 'middle',
    nameGap: orientation === 'y' && isCategory ? 198 : axis.type === 'number' ? 48 : 36,
    min: axis.min,
    max: axis.max,
    ...(orientation === 'y' && isCategory ? { inverse: true } : {}),
    axisLabel: {
      hideOverlap: true,
      ...(orientation === 'y' && isCategory ? { width: 190, overflow: 'truncate' } : {}),
    },
  };
}

function mobileCartesianOption(spec: CartesianVisualizationSpecV1) {
  const yIsCategory = spec.axes.y.type === 'category' || spec.axes.y.type === 'text';
  if (!yIsCategory) return { grid: { top: 88 } };
  return {
    grid: { top: 52, right: 20, bottom: 56, left: 140, outerBoundsMode: 'none' },
    yAxis: {
      name: '',
      axisLabel: { hideOverlap: true, width: 124, overflow: 'truncate' },
    },
  };
}

function annotationOptions(annotations: VisualizationAnnotation[]) {
  const referenceLines = annotations.filter(annotation => annotation.kind === 'reference-line');
  const ranges = annotations.filter(annotation => annotation.kind === 'range');
  const points = annotations.filter(annotation => annotation.kind === 'point');
  return {
    ...(referenceLines.length ? { markLine: {
      symbol: 'none',
      data: referenceLines.map(annotation => ({
        name: annotation.label,
        [annotation.axis === 'y' ? 'yAxis' : 'xAxis']: annotation.value,
        label: {
          formatter: annotation.label,
          position: 'insideEndTop',
          align: annotation.axis === 'y' ? 'right' : 'left',
          rotate: 0,
          width: 88,
          overflow: 'break',
          padding: annotation.axis === 'y' ? [0, 6, 4, 0] : [0, 0, 4, 6],
        },
        lineStyle: { color: annotationColor(annotation), type: 'dashed', width: 2 },
      })),
    } } : {}),
    ...(ranges.length ? { markArea: {
      silent: true,
      label: {
        position: 'insideTopLeft',
        align: 'left',
        width: 80,
        overflow: 'break',
        padding: [4, 0, 0, 4],
      },
      data: ranges.map(annotation => [
        { name: annotation.label, [annotation.axis === 'y' ? 'yAxis' : 'xAxis']: annotation.start },
        { [annotation.axis === 'y' ? 'yAxis' : 'xAxis']: annotation.end },
      ]),
      itemStyle: { color: trackerVisualizationPalette.line, opacity: 0.28 },
    } } : {}),
    ...(points.length ? { markPoint: {
      data: points.map(annotation => ({ name: annotation.label, coord: [annotation.x, annotation.y], value: annotation.label })),
    } } : {}),
  };
}

function dataZoomOptions(spec: CartesianVisualizationSpecV1) {
  const zoom = spec.interactions?.zoom;
  if (!zoom) return undefined;
  const axisIndex = zoom.axis === 'y' ? { yAxisIndex: [0] } : { xAxisIndex: [0] };
  return [
    { type: 'inside', ...axisIndex, start: zoom.startPercent ?? 0, end: zoom.endPercent ?? 100 },
    { type: 'slider', ...axisIndex, start: zoom.startPercent ?? 0, end: zoom.endPercent ?? 100, height: 18, bottom: 12 },
  ];
}

function markToSeriesType(mark: CartesianVisualizationSpecV1['series'][number]['mark']) {
  if (mark === 'bar') return 'bar';
  if (mark === 'point') return 'scatter';
  return 'line';
}

function numericDifference(high: VisualizationValue, low: VisualizationValue) {
  return typeof high === 'number' && typeof low === 'number' ? Math.max(0, high - low) : 0;
}

function annotationColor(annotation: VisualizationAnnotation) {
  if (annotation.severity === 'critical') return trackerVisualizationPalette.risk;
  if (annotation.severity === 'warning') return trackerVisualizationPalette.caution;
  if (annotation.severity === 'info') return trackerVisualizationPalette.selection;
  return trackerVisualizationPalette.lineStrong;
}
