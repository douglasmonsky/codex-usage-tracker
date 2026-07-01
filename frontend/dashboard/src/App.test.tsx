import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('React dashboard shell', () => {
  it('renders the overview workspace by default', () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('switches between feature workspaces and preserves active navigation state', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /Usage Drain Lab/i }));
    expect(screen.getByRole('heading', { name: 'Usage Drain Lab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Usage Drain Lab/i })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));
    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument();
  });
});
