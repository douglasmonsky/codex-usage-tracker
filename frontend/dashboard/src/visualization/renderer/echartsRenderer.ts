import type { VisualizationSpecV1 } from '../spec';
import type { EChartsVisualizationRenderer } from './runtime';

export type { EChartsVisualizationRenderer } from './runtime';

export async function createEChartsVisualizationRenderer(
  element: HTMLElement,
  spec: VisualizationSpecV1,
  onSelectionChange: (key: string) => void,
  options: { animate?: boolean; signal?: AbortSignal } = {},
): Promise<EChartsVisualizationRenderer | null> {
  const rendererOptions = { animate: options.animate };
  const features: Array<Promise<unknown>> = [
    import('./features/accessibilityFeature'),
    import('./features/tooltipFeature'),
  ];
  if (spec.interactions?.zoom || spec.interactions?.brush) features.push(import('./features/interactionFeature'));
  if (spec.annotations?.length) features.push(import('./features/annotationFeature'));
  if (spec.kind === 'cartesian' && spec.series.length > 1) features.push(import('./features/legendFeature'));
  if (spec.kind === 'heatmap') features.push(import('./features/visualMapFeature'));

  if (spec.kind === 'cartesian') {
    const [{ createCartesianRenderer }] = await Promise.all([import('./kinds/cartesianRenderer'), ...features]);
    return options.signal?.aborted ? null : createCartesianRenderer(element, spec, onSelectionChange, rendererOptions);
  }
  if (spec.kind === 'heatmap') {
    const [{ createHeatmapRenderer }] = await Promise.all([import('./kinds/heatmapRenderer'), ...features]);
    return options.signal?.aborted ? null : createHeatmapRenderer(element, spec, onSelectionChange, rendererOptions);
  }
  const [{ createFlowRenderer }] = await Promise.all([import('./kinds/flowRenderer'), ...features]);
  return options.signal?.aborted ? null : createFlowRenderer(element, spec, onSelectionChange, rendererOptions);
}
