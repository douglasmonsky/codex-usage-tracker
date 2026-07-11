import { tableRowsForVisualization } from './table';
import type { VisualizationSpecV1 } from './types';

export function visualizationAriaDescription(spec: VisualizationSpecV1): string {
  const rows = tableRowsForVisualization(spec);
  const parts = [spec.title, stateDescription(spec), spec.accessibility.summary];
  if (rows.length) parts.push(`${rows.length.toLocaleString()} table rows available.`);
  if (spec.caveats?.length) parts.push(`Caveats: ${spec.caveats.join(' ')}`);
  if (spec.accessibility.keyboardInstructions) parts.push(spec.accessibility.keyboardInstructions);
  return parts.filter(Boolean).join(' ');
}

export function stateDescription(spec: VisualizationSpecV1): string {
  switch (spec.state.kind) {
    case 'ready':
      return 'Data is ready.';
    case 'loading':
      return spec.state.message ?? 'Visualization is loading.';
    case 'empty':
    case 'insufficient-data':
    case 'partial':
    case 'stale':
    case 'error':
      return spec.state.message;
  }
}
