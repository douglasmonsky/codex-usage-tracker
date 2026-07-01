import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { App } from './App';
import { rowsToCsv } from './features/shared/exportCsv';

describe('React dashboard shell', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    delete window.__CODEX_USAGE_BOOT__;
  });

  it('renders overview workspace by default', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Recent calls' })).toBeInTheDocument();
  });

  it('switches between feature workspaces and preserves active navigation state', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Usage Drain Lab/i }));
    expect(screen.getByRole('heading', { name: 'Usage Drain Lab' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Usage Drain Lab/i })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: /^Reports$/i }));
    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument();
  });

  it('filters calls and shows the selected call drill-down panel', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    expect(screen.getByRole('heading', { name: 'Call Drill-Down' })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Search calls, threads, models...'), {
      target: { value: 'thread-3c8d4e' },
    });

    expect(screen.getByText('thread-3c8d4e')).toBeInTheDocument();
    expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();

    const row = screen.getByText('thread-3c8d4e').closest('tr');
    expect(row).not.toBeNull();
    fireEvent.click(row as HTMLTableRowElement);
    expect(screen.getByText('thread-3c8d4e / o3')).toBeInTheDocument();
    expect(screen.getAllByText('Uncached input').length).toBeGreaterThan(0);
    expect(screen.getByRole('tab', { name: /Summary/i })).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(screen.getByRole('tab', { name: /Tokens/i }));
    expect(screen.getByText('Reasoning output')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    expect(screen.getByText('Raw context is gated')).toBeInTheDocument();
    expect(screen.getByText(/explicit localhost context API/i)).toBeInTheDocument();
  });

  it('sorts table columns through accessible header controls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    const sortButton = screen.getByRole('button', { name: 'Sort by Est. Cost' });
    fireEvent.click(sortButton);
    expect(sortButton.closest('th')).toHaveAttribute('aria-sort', 'descending');
  });

  it('escapes CSV output for aggregate exports', () => {
    expect(
      rowsToCsv(
        [{ name: 'thread,with,commas', value: 42 }],
        [
          { header: 'Name', value: row => row.name },
          { header: 'Value', value: row => row.value },
        ],
      ),
    ).toBe('Name,Value\n"thread,with,commas",42');
  });
});
