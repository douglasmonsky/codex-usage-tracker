import type { VisualizationSpecV1 } from '../spec';
import { baseOption, targetKey } from './modelShared';
import type { EChartsVisualizationModel, VisualizationSelectionTarget } from './modelTypes';
import { trackerVisualizationPalette } from './theme';

export function buildFlowModel(
  spec: Extract<VisualizationSpecV1, { kind: 'flow' }>,
  animate: boolean,
): EChartsVisualizationModel {
  const targetByKey = new Map<string, VisualizationSelectionTarget>();
  const keyByTarget = new Map<string, string>();
  const links = spec.data.links.map((link, dataIndex) => {
    const target = { seriesIndex: 0, dataIndex, dataType: 'edge' as const };
    targetByKey.set(link.id, target);
    keyByTarget.set(targetKey(target), link.id);
    return { ...link, selectionKey: link.id };
  });
  return {
    option: {
      ...baseOption(spec, animate),
      series: [{
        id: spec.id,
        type: 'sankey',
        data: spec.data.nodes.map(node => ({ name: node.id, label: { formatter: node.label }, itemStyle: { color: node.color } })),
        links,
        left: 24,
        right: 112,
        top: 24,
        bottom: 24,
        nodeWidth: 18,
        nodeGap: 16,
        draggable: false,
        emphasis: { focus: 'adjacency' },
        lineStyle: { color: 'gradient', opacity: 0.42, curveness: 0.5 },
        label: { color: trackerVisualizationPalette.ink, fontSize: 12 },
      }],
    },
    targetByKey,
    keyByTarget,
  };
}
