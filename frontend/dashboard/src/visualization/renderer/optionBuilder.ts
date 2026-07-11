import type { VisualizationSpecV1 } from '../spec';
import { buildCartesianModel } from './cartesianModel';
import { buildFlowModel } from './flowModel';
import { buildHeatmapModel } from './heatmapModel';

export type { EChartsVisualizationModel, VisualizationSelectionTarget } from './modelTypes';

export function buildEChartsVisualizationModel(
  spec: VisualizationSpecV1,
  options: { animate?: boolean } = {},
) {
  const animate = options.animate ?? false;
  if (spec.kind === 'cartesian') return buildCartesianModel(spec, animate);
  if (spec.kind === 'heatmap') return buildHeatmapModel(spec, animate);
  return buildFlowModel(spec, animate);
}
