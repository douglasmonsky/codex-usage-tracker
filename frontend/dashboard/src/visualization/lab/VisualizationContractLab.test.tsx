import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { VisualizationContractLab } from './VisualizationContractLab';

describe('VisualizationContractLab', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/?lab=visualization-contract&mode=table');
  });

  it('switches semantic fixtures and contract states through URL-backed controls', () => {
    render(<VisualizationContractLab />);

    fireEvent.change(screen.getByLabelText('Example'), { target: { value: 'waste-matrix' } });
    fireEvent.change(screen.getByLabelText('Data state'), { target: { value: 'insufficient-data' } });

    expect(screen.getByRole('heading', { name: 'Waste fingerprint matrix' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('More observations are required for this result.');
    const params = new URLSearchParams(window.location.search);
    expect(params.get('example')).toBe('waste-matrix');
    expect(params.get('state')).toBe('insufficient-data');
    expect(params.get('mode')).toBe('table');
  });
});
