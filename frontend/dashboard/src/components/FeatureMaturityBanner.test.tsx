import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FeatureMaturityBanner } from './FeatureMaturityBanner';

describe('FeatureMaturityBanner', () => {
  it('exposes experimental maturity details as an accessible note', () => {
    render(
      <FeatureMaturityBanner
        kind="experimental"
        title="Highly experimental"
        description="Useful for technical exploration; methods and presentation may change."
      />,
    );

    const note = screen.getByRole('note', { name: 'Feature maturity: Highly experimental' });
    expect(within(note).getByText('Highly experimental')).toBeInTheDocument();
    expect(within(note).getByText(
      'Useful for technical exploration; methods and presentation may change.',
    )).toBeInTheDocument();
    expect(within(note).queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers an optional replacement action for transitioning features', () => {
    const onSelect = vi.fn();
    render(
      <FeatureMaturityBanner
        kind="transitioning"
        title="Transition planning"
        description="This workspace remains available in Release N."
        replacementAction={{ label: 'Open replacement', onSelect }}
      />,
    );

    const note = screen.getByRole('note', { name: 'Feature maturity: Transition planning' });
    fireEvent.click(within(note).getByRole('button', { name: 'Open replacement' }));
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it('names and links the core replacement for direct-only workbenches', () => {
    render(
      <FeatureMaturityBanner
        kind="transitioning"
        title="Available during transition"
        description="This workspace remains available in Release N."
        replacement={{
          operation: 'usage_analyze(goal="usage_spike") → usage_evidence',
          href: '?view=explore&mode=calls',
        }}
      />,
    );

    const note = screen.getByRole('note', {
      name: 'Feature maturity: Available during transition',
    });
    expect(within(note).getByText('usage_analyze(goal="usage_spike") → usage_evidence'))
      .toBeInTheDocument();
    expect(within(note).getByRole('link', { name: 'Open evidence' }))
      .toHaveAttribute('href', '?view=explore&mode=calls');
  });
});
