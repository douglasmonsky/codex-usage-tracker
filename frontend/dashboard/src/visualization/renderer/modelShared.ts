import type { EChartsCoreOption } from 'echarts/core';

import { visualizationAriaDescription } from '../spec';
import type { VisualizationRecord, VisualizationSpecV1 } from '../spec';
import type { VisualizationSelectionTarget } from './modelTypes';

export function baseOption(spec: VisualizationSpecV1, animate: boolean): EChartsCoreOption {
  return {
    animation: animate,
    aria: { enabled: true, description: visualizationAriaDescription(spec) },
    tooltip: { trigger: spec.kind === 'flow' ? 'item' : 'axis', confine: true },
  };
}

export function brushOptions(spec: VisualizationSpecV1) {
  const brush = spec.interactions?.brush;
  if (!brush || spec.kind === 'flow') return undefined;
  return {
    toolbox: brush.axis === 'both' ? ['rect', 'clear'] : [brush.axis === 'x' ? 'lineX' : 'lineY', 'clear'],
    brushMode: 'single',
    transformable: true,
    throttleType: 'debounce',
    throttleDelay: 160,
  };
}

export function toolboxOptions(spec: VisualizationSpecV1) {
  if (!spec.interactions?.zoom && !spec.interactions?.brush) return undefined;
  const feature = {
    ...(spec.interactions?.zoom
      ? { dataZoom: { yAxisIndex: spec.interactions.zoom.axis === 'y' ? 'all' : 'none' } }
      : {}),
    ...(spec.interactions?.brush ? { brush: { type: ['rect', 'clear'] } } : {}),
    restore: {},
  };
  return { right: 8, top: 4, feature };
}

export function selectionKey(row: VisualizationRecord, field: string | undefined, index: number) {
  return field ? String(row[field] ?? index) : String(index);
}

export function targetKey(target: VisualizationSelectionTarget) {
  return `${target.seriesIndex}:${target.dataIndex}:${target.dataType ?? ''}`;
}
