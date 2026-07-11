import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PageLoadProgress } from './PageLoadProgress';

describe('PageLoadProgress', () => {
  it('renders determinate module progress', () => {
    render(<PageLoadProgress active completed={1} total={2} label="Loading allowance evidence" />);

    const progress = screen.getByRole('progressbar', { name: 'Loading allowance evidence' });
    expect(progress).toHaveAttribute('aria-valuemin', '0');
    expect(progress).toHaveAttribute('aria-valuemax', '2');
    expect(progress).toHaveAttribute('aria-valuenow', '1');
    expect(screen.getByText('1 of 2 modules ready')).toBeInTheDocument();
  });

  it('renders indeterminate progress without a fabricated value', () => {
    render(<PageLoadProgress active label="Loading report pack" />);

    const progress = screen.getByRole('progressbar', { name: 'Loading report pack' });
    expect(progress).not.toHaveAttribute('aria-valuenow');
    expect(screen.queryByText(/modules ready/i)).not.toBeInTheDocument();
  });

  it('keeps initial endpoint failures visible', () => {
    render(<PageLoadProgress active={false} label="Loading report pack" error="Report endpoint failed" />);

    expect(screen.getByRole('alert')).toHaveTextContent('Report endpoint failed');
  });

  it('renders nothing after successful completion', () => {
    const { container } = render(<PageLoadProgress active={false} label="Loading report pack" />);

    expect(container).toBeEmptyDOMElement();
  });
});
