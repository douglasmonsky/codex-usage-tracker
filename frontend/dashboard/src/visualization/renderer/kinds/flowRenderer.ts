import 'echarts/lib/chart/sankey';

import type { FlowVisualizationSpecV1 } from '../../spec';
import { createRegisteredRenderer } from '../runtime';

export function createFlowRenderer(
  element: HTMLElement,
  spec: FlowVisualizationSpecV1,
  onSelectionChange: (key: string) => void,
  options: { animate?: boolean } = {},
) {
  return createRegisteredRenderer(element, spec, onSelectionChange, options);
}
