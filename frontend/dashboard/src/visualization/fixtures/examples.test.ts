import { describe, expect, it } from 'vitest';

import { tableRowsForVisualization, validateVisualizationSpec } from '../spec';
import { allowanceSpecForState, visualizationContractStates, visualizationExampleSpecs } from './index';

describe('visualization contract fixtures', () => {
  it('keeps all six analytical examples valid and table-equivalent', () => {
    expect(visualizationExampleSpecs.map(spec => spec.id)).toEqual([
      'allowance-change-point',
      'token-flow',
      'cache-frontier',
      'thread-lifecycle',
      'waste-matrix',
      'evidence-ledger',
    ]);
    for (const spec of visualizationExampleSpecs) {
      expect(validateVisualizationSpec(spec), spec.id).toEqual([]);
      expect(tableRowsForVisualization(spec).length, spec.id).toBeGreaterThan(0);
    }
  });

  it('covers every non-ready contract state with valid semantic specs', () => {
    expect(visualizationContractStates.map(state => state.kind)).toEqual([
      'loading',
      'empty',
      'partial',
      'insufficient-data',
      'stale',
      'error',
    ]);
    for (const state of visualizationContractStates) {
      const spec = allowanceSpecForState(state);
      expect(validateVisualizationSpec(spec), state.kind).toEqual([]);
    }
  });
});
