import type { VisualizationSpecV1 } from '../spec';
import { buildEChartsVisualizationModel, type EChartsVisualizationModel, type VisualizationSelectionTarget } from './optionBuilder';
import { init, trackerVisualizationThemeName, type EChartsType } from './setupCore';

export type EChartsVisualizationRenderer = {
  dispose: () => void;
  exportSvgDataUrl: () => string;
  resize: () => void;
  select: (key: string | null) => void;
  setSpec: (spec: VisualizationSpecV1, options?: { animate?: boolean }) => void;
};

export function createRegisteredRenderer(
  element: HTMLElement,
  spec: VisualizationSpecV1,
  onSelectionChange: (key: string) => void,
  options: { animate?: boolean } = {},
): EChartsVisualizationRenderer {
  const chart = init(element, trackerVisualizationThemeName, { renderer: 'svg' });
  let model = buildEChartsVisualizationModel(spec, options);
  chart.setOption(model.option, { notMerge: true });

  chart.on('click', event => {
    const selectionKey = selectionKeyFromEvent(event);
    if (selectionKey) onSelectionChange(selectionKey);
  });
  chart.on('brushselected', event => {
    const target = firstBrushTarget(event);
    const key = target ? model.keyByTarget.get(targetKey(target)) : null;
    if (key) onSelectionChange(key);
  });

  return {
    dispose: () => chart.dispose(),
    exportSvgDataUrl: () => chart.getDataURL({ type: 'svg', excludeComponents: ['toolbox'], backgroundColor: '#ffffff' }),
    resize: () => chart.resize(),
    select: key => selectChartTarget(chart, model, key),
    setSpec: (nextSpec, nextOptions = {}) => {
      model = buildEChartsVisualizationModel(nextSpec, nextOptions);
      chart.setOption(model.option, { notMerge: true });
    },
  };
}

function selectChartTarget(chart: EChartsType, model: EChartsVisualizationModel, key: string | null) {
  chart.dispatchAction({ type: 'downplay' });
  if (!key) return;
  const target = model.targetByKey.get(key);
  if (!target) return;
  chart.dispatchAction({ type: 'highlight', ...target });
  chart.dispatchAction({ type: 'showTip', ...target });
}

function selectionKeyFromEvent(event: unknown): string | null {
  if (!event || typeof event !== 'object') return null;
  const data = (event as { data?: unknown }).data;
  if (!data || typeof data !== 'object') return null;
  const key = (data as { selectionKey?: unknown; id?: unknown }).selectionKey ?? (data as { id?: unknown }).id;
  return typeof key === 'string' && key ? key : null;
}

function firstBrushTarget(event: unknown): VisualizationSelectionTarget | null {
  if (!event || typeof event !== 'object') return null;
  const batch = (event as { batch?: unknown }).batch;
  if (!Array.isArray(batch)) return null;
  const selected = (batch[0] as { selected?: unknown } | undefined)?.selected;
  if (!Array.isArray(selected)) return null;
  const selection = selected.find(item => Array.isArray((item as { dataIndex?: unknown }).dataIndex)) as
    | { seriesIndex?: unknown; dataIndex?: unknown }
    | undefined;
  const firstIndex = Array.isArray(selection?.dataIndex) ? selection.dataIndex[0] : null;
  return typeof selection?.seriesIndex === 'number' && typeof firstIndex === 'number'
    ? { seriesIndex: selection.seriesIndex, dataIndex: firstIndex }
    : null;
}

function targetKey(target: VisualizationSelectionTarget) {
  return `${target.seriesIndex}:${target.dataIndex}:${target.dataType ?? ''}`;
}
