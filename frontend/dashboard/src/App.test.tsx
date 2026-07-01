import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { rowsToCsv } from './features/shared/exportCsv';

describe('React dashboard shell', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    delete window.__CODEX_USAGE_BOOT__;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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
    expect(screen.getByText(/localhost dashboard server API token/i)).toBeInTheDocument();
  });

  it('sorts table columns through accessible header controls', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    const sortButton = screen.getByRole('button', { name: 'Sort by Est. Cost' });
    fireEvent.click(sortButton);
    expect(sortButton.closest('th')).toHaveAttribute('aria-sort', 'descending');
  });

  it('toggles call and thread columns while keeping identity columns locked', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
    expect(screen.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('Calls columns')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Signal' }));
    expect(screen.queryByRole('columnheader', { name: /Signal/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
    expect(screen.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Productivity' }));
    expect(screen.queryByRole('columnheader', { name: /Productivity/i })).not.toBeInTheDocument();
  });

  it('loads selected-call context evidence through the localhost API', async () => {
    window.history.replaceState(null, '', '/?view=calls');
    window.__CODEX_USAGE_BOOT__ = {
      api_token: 'test-token',
      context_api_enabled: true,
      loaded_row_count: 1,
      rows: [
        {
          record_id: 'record-context-1',
          call_started_at: '2026-07-01T12:00:00Z',
          thread_name: 'context-thread',
          model: 'gpt-5.5',
          effort: 'high',
          input_tokens: 1000,
          cached_input_tokens: 500,
          output_tokens: 100,
          total_tokens: 1100,
          estimated_cost_usd: 0.1,
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'codex-usage-tracker-context-v1',
        record_id: 'record-context-1',
        context_mode: 'quick',
        visible_char_count: 42,
        visible_token_estimate: 11,
        omitted: { older_entries: 0 },
        entries: [{ type: 'message', label: 'User prompt', line_number: 14, text: 'redacted context sample' }],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/i }));
    fireEvent.click(screen.getByRole('button', { name: /Show turn evidence/i }));

    expect(await screen.findByText('redacted context sample')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/context?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('record_id=record-context-1');
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Codex-Usage-Token': 'test-token',
        }),
      }),
    );
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
