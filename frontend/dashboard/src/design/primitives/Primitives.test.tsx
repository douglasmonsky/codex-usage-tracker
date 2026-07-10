import { fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  Button,
  IconButton,
  MetricReadout,
  ProgressBar,
  SegmentedControl,
  StatusBadge,
  Surface,
} from '../index';

describe('design primitives', () => {
  it('forwards native button props, refs, and variant styling', () => {
    const ref = createRef<HTMLButtonElement>();
    render(<Button ref={ref} variant="danger" disabled>Remove</Button>);

    const button = screen.getByRole('button', { name: 'Remove' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('type', 'button');
    expect(button.className).toContain('danger');
    expect(ref.current).toBe(button);
  });

  it('requires an accessible icon-button name and forwards events', () => {
    const onClick = vi.fn();
    render(<IconButton aria-label="Refresh usage" onClick={onClick}><span aria-hidden="true">R</span></IconButton>);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh usage' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('renders status, surface, and metric variants with semantic content', () => {
    render(
      <Surface tone="subtle" aria-label="Usage summary">
        <StatusBadge tone="positive">On track</StatusBadge>
        <MetricReadout label="Cached tokens" value="82%" detail="Up 4 points" />
      </Surface>,
    );

    expect(screen.getByLabelText('Usage summary').className).toContain('surfaceSubtle');
    expect(screen.getByText('On track').className).toContain('positive');
    expect(screen.getByText('82%')).toBeInTheDocument();
    expect(screen.getByText('Up 4 points')).toBeInTheDocument();
  });

  it('exposes segmented selection through a labelled group and pressed state', () => {
    const onValueChange = vi.fn();
    render(
      <SegmentedControl
        label="Density"
        value="compact"
        options={[{ label: 'Compact', value: 'compact' }, { label: 'Roomy', value: 'roomy' }]}
        onValueChange={onValueChange}
      />,
    );

    expect(screen.getByRole('group', { name: 'Density' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compact' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Roomy' }));
    expect(onValueChange).toHaveBeenCalledWith('roomy');
  });

  it('clamps progress while preserving accessible value metadata', () => {
    render(<ProgressBar label="Refresh progress" value={120} />);

    const progress = screen.getByRole('progressbar', { name: 'Refresh progress' });
    expect(progress).toHaveAttribute('aria-valuemin', '0');
    expect(progress).toHaveAttribute('aria-valuemax', '100');
    expect(progress).toHaveAttribute('aria-valuenow', '100');
    expect(screen.getByText('100%')).toHaveAttribute('aria-hidden', 'true');
  });
});
