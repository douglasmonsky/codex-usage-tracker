import 'echarts/lib/chart/bar';
import 'echarts/lib/chart/line';
import 'echarts/lib/chart/scatter';
import 'echarts/lib/component/grid';

import type { CartesianVisualizationSpecV1 } from '../../spec';
import { createRegisteredRenderer } from '../runtime';

export function createCartesianRenderer(
  element: HTMLElement,
  spec: CartesianVisualizationSpecV1,
  onSelectionChange: (key: string) => void,
  options: { animate?: boolean } = {},
) {
  return createRegisteredRenderer(element, spec, onSelectionChange, options);
}
