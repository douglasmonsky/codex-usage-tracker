import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import type { ColumnDef, SortingState } from '@tanstack/react-table';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EvidenceGrid } from './EvidenceGrid';
import {
  useEvidenceGridPreferences,
  type EvidenceGridDensity,
  type EvidenceGridPreferenceDefaults,
} from './useEvidenceGridPreferences';

type Evidence = {
  id: string;
  call: string;
  detail: string;
  tokens: number;
};

const columns: Array<ColumnDef<Evidence, unknown>> = [
  { accessorKey: 'call', id: 'call', header: 'Call', size: 260 },
  { accessorKey: 'detail', id: 'detail', header: 'Context', size: 320 },
  { accessorKey: 'tokens', id: 'tokens', header: 'Tokens', size: 180 },
];

const rows: Evidence[] = [
  { id: 'a', call: 'Alpha call', detail: 'First evidence detail', tokens: 120 },
  { id: 'b', call: 'Beta call', detail: 'Second evidence detail', tokens: 80 },
];

const defaults: EvidenceGridPreferenceDefaults = {
  density: 'comfortable',
  columnVisibility: { call: true, detail: true, tokens: true },
};

function mockViewport(matches: boolean) {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); },
  };
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches,
    media: '(max-width: 700px)',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })));
}

type HarnessProps = {
  data?: Evidence[];
  storageKey?: string;
  initialDensity?: EvidenceGridDensity;
  onSelect?: (row: Evidence) => void;
  onActivate?: (row: Evidence) => void;
};

function GridHarness({ data = rows, storageKey = 'test-evidence-grid', initialDensity, onSelect, onActivate }: HarnessProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const preferences = useEvidenceGridPreferences(storageKey, defaults, initialDensity);
  return (
    <EvidenceGrid
      ariaLabel="Calls evidence"
      columns={columns}
      data={data}
      identityColumnId="call"
      getRowId={row => row.id}
      mobile={{
        primary: row => row.call,
        secondary: row => `${row.detail} · ${row.tokens} tokens`,
        actionLabel: (row, rank) => `Rank ${rank}: ${row.call}`,
      }}
      sorting={sorting}
      onSortingChange={setSorting}
      columnVisibility={preferences.columnVisibility}
      onColumnVisibilityChange={preferences.setColumnVisibility}
      density={preferences.density}
      onDensityChange={preferences.setDensity}
      onRestoreDefaults={preferences.restoreDefaults}
      selectedRowId="a"
      onRowSelect={onSelect}
      onRowActivate={onActivate}
      viewportHeight={160}
    />
  );
}

afterEach(() => {
  globalThis.localStorage?.clear();
  vi.unstubAllGlobals();
});

describe('EvidenceGrid', () => {
  it('renders only a virtual window while exposing the full row count', () => {
    mockViewport(false);
    const manyRows = Array.from({ length: 100 }, (_, index) => ({
      id: String(index),
      call: `Call ${index}`,
      detail: `Evidence ${index}`,
      tokens: index,
    }));

    render(<GridHarness data={manyRows} />);

    const scroller = screen.getByRole('table', { name: 'Calls evidence' }).parentElement;
    expect(scroller).toHaveAttribute('data-virtualized', 'true');
    expect(screen.getByRole('table', { name: 'Calls evidence' })).toHaveAttribute('aria-rowcount', '101');
    expect(screen.getAllByRole('row').length).toBeLessThan(101);
  });

  it('keeps the 100k-row performance fixture bounded to one virtual window', () => {
    mockViewport(false);
    const manyRows = Array.from({ length: 100_000 }, (_, index) => ({
      id: String(index),
      call: `Call ${index}`,
      detail: `Evidence ${index}`,
      tokens: index,
    }));
    const started = performance.now();

    render(<GridHarness data={manyRows} />);

    const table = screen.getByRole('table', { name: 'Calls evidence' });
    expect(table).toHaveAttribute('aria-rowcount', '100001');
    expect(screen.getAllByRole('row').length).toBeLessThan(40);
    expect(performance.now() - started).toBeLessThan(8_000);
  }, 12_000);

  it('selects with Space and activates with Enter', () => {
    mockViewport(false);
    const onSelect = vi.fn();
    const onActivate = vi.fn();
    render(<GridHarness onSelect={onSelect} onActivate={onActivate} />);
    const alphaRow = screen.getByRole('row', { name: /Alpha call/ });

    fireEvent.keyDown(alphaRow, { key: ' ' });
    fireEvent.keyDown(alphaRow, { key: 'Enter' });

    expect(onSelect).toHaveBeenCalledWith(rows[0]);
    expect(onActivate).toHaveBeenCalledWith(rows[0]);
  });

  it('uses a semantic two-line ranked list on mobile', () => {
    mockViewport(true);
    const onActivate = vi.fn();
    render(<GridHarness onActivate={onActivate} />);

    const list = screen.getByRole('list', { name: 'Calls evidence ranked list' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Alpha call')).toBeInTheDocument();
    expect(within(list).getByText('First evidence detail · 120 tokens')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    fireEvent.keyDown(within(list).getByRole('button', { name: 'Rank 1: Alpha call' }), { key: 'Enter' });
    expect(onActivate).toHaveBeenCalledWith(rows[0]);
  });

  it('shows a useful empty state', () => {
    mockViewport(false);
    render(<GridHarness data={[]} />);
    expect(screen.getByRole('status')).toHaveTextContent('No evidence matches the current filters.');
  });

  it('persists density and column visibility, then restores defaults', async () => {
    mockViewport(false);
    const { unmount } = render(<GridHarness storageKey="persisted-grid" />);

    fireEvent.click(screen.getByRole('button', { name: 'Dense' }));
    fireEvent.click(screen.getByText('Columns'));
    fireEvent.click(screen.getByLabelText('Tokens'));

    await waitFor(() => expect(window.localStorage.getItem('persisted-grid')).toContain('compact'));
    unmount();
    render(<GridHarness storageKey="persisted-grid" />);
    expect(screen.getByRole('button', { name: 'Dense' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByText('Columns'));
    expect(screen.getByLabelText('Tokens')).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: 'Restore defaults' }));
    expect(screen.getByRole('button', { name: 'Roomy' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Tokens')).toBeChecked();
  });
});

describe('useEvidenceGridPreferences', () => {
  it('lets an explicit initial density override a stored density without discarding columns', () => {
    mockViewport(false);
    globalThis.localStorage.setItem('shared-grid', JSON.stringify({
      density: 'compact',
      columnVisibility: { tokens: false },
    }));
    render(<GridHarness storageKey="shared-grid" initialDensity="comfortable" />);
    expect(screen.getByRole('button', { name: 'Roomy' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByText('Columns'));
    expect(screen.getByLabelText('Tokens')).not.toBeChecked();
  });

  it('ignores malformed stored values', () => {
    mockViewport(false);
    globalThis.localStorage.setItem('malformed-grid', JSON.stringify({
      density: 'tiny' as EvidenceGridDensity,
      columnVisibility: { call: 'yes', tokens: false },
    }));
    render(<GridHarness storageKey="malformed-grid" />);
    expect(screen.getByRole('button', { name: 'Roomy' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByText('Columns'));
    expect(screen.getByLabelText('Call')).toBeChecked();
    expect(screen.getByLabelText('Tokens')).not.toBeChecked();
  });
});
