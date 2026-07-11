import type { VisualizationDataState, VisualizationSpecV1 } from '../spec';
import { allowanceChangePointSpec } from './analyticalExamples';

export const visualizationContractStates: VisualizationDataState[] = [
  { kind: 'loading', message: 'Loading local evidence...' },
  { kind: 'empty', message: 'No observations match this scope.' },
  { kind: 'partial', message: 'Only part of the requested evidence is available.', availableRows: 6, expectedRows: 8 },
  { kind: 'insufficient-data', message: 'More observations are required for this result.', availableRows: 2, requiredRows: 4 },
  { kind: 'stale', message: 'Showing the last successful local snapshot.', lastUpdatedAt: '2026-07-10T11:00:00Z' },
  { kind: 'error', message: 'The local evidence request failed.', retryable: true },
];

export function allowanceSpecForState(state: VisualizationDataState): VisualizationSpecV1 {
  return visualizationSpecForState(allowanceChangePointSpec, state);
}

export function visualizationSpecForState(spec: VisualizationSpecV1, state: VisualizationDataState): VisualizationSpecV1 {
  const keepsAllData = state.kind === 'stale';
  const keepsPartialData = state.kind === 'partial';
  if (spec.kind === 'flow') {
    const links = keepsAllData ? spec.data.links : keepsPartialData ? spec.data.links.slice(0, Math.max(1, Math.ceil(spec.data.links.length * 0.6))) : [];
    const nodes = links.length ? spec.data.nodes : [];
    return { ...spec, id: `${spec.id}-${state.kind}`, state, scope: { ...spec.scope, rowCount: links.length }, data: { nodes, links } };
  }
  const rows = keepsAllData ? spec.data.rows : keepsPartialData ? spec.data.rows.slice(0, Math.max(1, Math.ceil(spec.data.rows.length * 0.6))) : [];
  return { ...spec, id: `${spec.id}-${state.kind}`, state, scope: { ...spec.scope, rowCount: rows.length }, data: { rows } };
}
