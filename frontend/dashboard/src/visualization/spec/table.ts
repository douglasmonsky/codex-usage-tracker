import type {
  FlowVisualizationSpecV1,
  VisualizationRecord,
  VisualizationSpecV1,
  VisualizationTableColumn,
  VisualizationValue,
} from './types';

export type VisualizationTableRow = {
  key: string;
  values: VisualizationRecord;
};

export function tableRowsForVisualization(spec: VisualizationSpecV1): VisualizationTableRow[] {
  if (spec.kind === 'flow') return flowTableRows(spec);
  const keyField = spec.interactions?.selection?.keyField;
  return spec.data.rows.map((row, index) => ({
    key: keyField ? String(row[keyField] ?? index) : String(index),
    values: row,
  }));
}

export function formatVisualizationValue(value: VisualizationValue, column: VisualizationTableColumn): string {
  if (value === null || value === '') return 'Not available';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value !== 'number') return String(value);

  switch (column.unit) {
    case 'percent':
      return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
    case 'ratio':
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    case 'seconds':
      return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}s`;
    case 'usd':
      return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 });
    case 'tokens':
    case 'count':
      return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    case 'credits':
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    default:
      return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
}

function flowTableRows(spec: FlowVisualizationSpecV1): VisualizationTableRow[] {
  const nodeLabels = new Map(spec.data.nodes.map(node => [node.id, node.label]));
  return spec.data.links.map(link => ({
    key: link.id,
    values: {
      id: link.id,
      source: nodeLabels.get(link.source) ?? link.source,
      target: nodeLabels.get(link.target) ?? link.target,
      value: link.value,
      evidenceKey: link.evidenceKey ?? null,
    },
  }));
}
