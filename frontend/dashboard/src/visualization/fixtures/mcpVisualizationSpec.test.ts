import { describe, expect, it } from 'vitest';

import { tableRowsForVisualization, validateVisualizationSpec, type VisualizationSpecV1 } from '../spec';
import fixture from './mcpTokenWasteSpec.json';

describe('MCP visualization contract fixture', () => {
  it('is accepted by the dashboard contract and preserves table-equivalent evidence', () => {
    const spec = fixture as VisualizationSpecV1;

    expect(validateVisualizationSpec(spec)).toEqual([]);
    expect(spec.kind).toBe('cartesian');
    if (spec.kind !== 'cartesian') throw new Error('Expected cartesian MCP fixture.');
    expect(tableRowsForVisualization(spec).map(row => row.values)).toEqual(spec.data.rows);
    expect(spec.axes.y.unit).toBe('tokens');
    expect(spec.interactions?.selection?.keyField).toBe('id');
  });
});
