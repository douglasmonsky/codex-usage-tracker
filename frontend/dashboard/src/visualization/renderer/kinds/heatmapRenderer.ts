import 'echarts/lib/chart/heatmap';
import 'echarts/lib/component/grid';

import type { HeatmapVisualizationSpecV1 } from '../../spec';
import { createRegisteredRenderer } from '../runtime';

export function createHeatmapRenderer(
  element: HTMLElement,
  spec: HeatmapVisualizationSpecV1,
  onSelectionChange: (key: string) => void,
  options: { animate?: boolean } = {},
) {
  return createRegisteredRenderer(element, spec, onSelectionChange, options);
}
