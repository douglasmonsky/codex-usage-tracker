import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineChart } from './LineChart';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('LineChart', () => {
  it('fills the available viewport for sparse chart data', () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(920);

    render(
      <LineChart
        yLabel="Credits"
        series={[
          {
            id: 'weekly',
            label: 'Projected',
            color: '#2563eb',
            points: [],
          },
        ]}
      />,
    );

    const chart = screen.getByRole('img', { name: 'Credits line chart' });
    expect(chart.querySelector('svg.chart')).toHaveAttribute('width', '920');
  });

  it('shows recent-history scroll affordance while keeping dense date labels available', () => {
    const points = Array.from({ length: 14 }, (_, index) => ({
      label: `Jul ${index + 1}`,
      value: (index + 1) * 100,
    }));

    render(
      <LineChart
        yLabel="Tokens"
        series={[
          {
            id: 'tokens',
            label: 'Input',
            color: '#2563eb',
            points,
          },
        ]}
      />,
    );

    const chart = screen.getByRole('img', { name: 'Tokens line chart' });
    expect(within(chart).getByText('Recent dates shown. Scroll left for earlier dates.')).toBeInTheDocument();
    expect(within(chart).getByLabelText('Tokens history. Recent dates are shown first; scroll left for earlier dates.')).toHaveAttribute(
      'tabindex',
      '0',
    );
    points.forEach(point => expect(within(chart).getByText(point.label)).toBeInTheDocument());
    expect(chart.querySelector('svg.chart')).toHaveAttribute('width', '760');
  });

  it('keeps long daily histories compact so fewer labeled dates are skipped in the first viewport', () => {
    const points = Array.from({ length: 31 }, (_, index) => ({
      label: `Jul ${index + 1}`,
      value: (index + 1) * 100,
    }));

    render(
      <LineChart
        yLabel="Tokens"
        series={[
          {
            id: 'tokens',
            label: 'Input',
            color: '#2563eb',
            points,
          },
        ]}
      />,
    );

    const chart = screen.getByRole('img', { name: 'Tokens line chart' });
    expect(chart.querySelector('svg.chart')).toHaveAttribute('width', '1178');
    points.forEach(point => expect(within(chart).getByText(point.label)).toBeInTheDocument());
  });
});
