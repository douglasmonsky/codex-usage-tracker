import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { allowanceChangePointSpec } from '../fixtures';
import { Visualization } from './Visualization';

const renderer = {
  dispose: vi.fn(),
  exportSvgDataUrl: vi.fn(() => 'data:image/svg+xml;base64,PHN2Zy8+'),
  resize: vi.fn(),
  select: vi.fn(),
  setSpec: vi.fn(),
};

vi.mock('../renderer/echartsRenderer', () => ({
  createEChartsVisualizationRenderer: vi.fn(async () => renderer),
}));

describe('Visualization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(640);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(360);
  });

  afterEach(() => vi.restoreAllMocks());

  it('keeps chart and table selection synchronized through keyboard controls', () => {
    const onSelectionChange = vi.fn();
    render(<Visualization spec={allowanceChangePointSpec} defaultView="table" onSelectionChange={onSelectionChange} />);

    const table = screen.getByRole('table', { name: 'Weekly allowance regime evidence' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows[0]).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(rows[0], { key: 'ArrowDown' });
    expect(rows[1]).toHaveAttribute('aria-selected', 'true');
    expect(onSelectionChange).toHaveBeenCalledWith('week-05-26');
  });

  it('signals additional table columns until horizontal scrolling reaches the end', () => {
    render(<Visualization spec={allowanceChangePointSpec} defaultView="table" />);

    const region = screen.getByRole('region', { name: 'Weekly allowance regime evidence table' });
    Object.defineProperties(region, {
      clientWidth: { configurable: true, value: 320 },
      scrollWidth: { configurable: true, value: 720 },
    });

    fireEvent.scroll(region);
    expect(region.parentElement).toHaveAttribute('data-overflow-right', 'true');

    Object.defineProperty(region, 'scrollLeft', { configurable: true, value: 400 });
    fireEvent.scroll(region);
    expect(region.parentElement).toHaveAttribute('data-overflow-right', 'false');
  });

  it('lazy-loads the chart renderer and exports SVG through the icon control', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<Visualization spec={allowanceChangePointSpec} />);

    const exportButton = screen.getByRole('button', { name: 'Export visualization as SVG' });
    await waitFor(() => expect(exportButton).toBeEnabled());
    fireEvent.click(exportButton);

    expect(renderer.exportSvgDataUrl).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('renders non-ready state messages without initializing chart data', () => {
    render(
      <Visualization
        spec={{
          ...allowanceChangePointSpec,
          id: 'allowance-empty',
          state: { kind: 'empty', message: 'No observations match this scope.' },
          scope: { ...allowanceChangePointSpec.scope, rowCount: 0 },
          data: { rows: [] },
        }}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('No observations match this scope.');
    expect(screen.queryByRole('region', { name: 'Weekly allowance regime evidence chart' })).not.toBeInTheDocument();
  });
});
