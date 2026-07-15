import { describe, expect, it } from 'vitest';

import { formatVisualizationValue } from './table';

describe('visualization table formatting', () => {
  it('formats credits per allowance percentage point explicitly', () => {
    expect(formatVisualizationValue(105.11, {
      field: 'capacity',
      label: 'Capacity',
      type: 'number',
      unit: 'credits_per_percent',
    })).toBe('105.11 credits / 1%');
  });
});
