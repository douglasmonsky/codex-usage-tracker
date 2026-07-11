import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen } from './test-utils/appTestHarness';

describe('React dashboard shell global filters', () => {
  installAppTestHooks();

  it('ports legacy shell model, effort, confidence, date filters onto Overview', () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText('Global model filter'), { target: { value: 'o4-mini' } });
    fireEvent.change(screen.getByLabelText('Global effort filter'), { target: { value: 'medium' } });
    fireEvent.change(screen.getByLabelText('Global confidence filter'), { target: { value: 'cost-estimated' } });

    const params = new URLSearchParams(window.location.search);
    expect(params.get('model')).toBe('o4-mini');
    expect(params.get('effort')).toBe('medium');
    expect(params.get('confidence')).toBe('cost-estimated');
    expect(screen.getByText('thread-7b2e91')).toBeInTheDocument();
    expect(screen.queryByText('thread-9f3a1c')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Global start date'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('Global end date'), { target: { value: '2026-05-01' } });

    const dateParams = new URLSearchParams(window.location.search);
    expect(dateParams.get('date')).toBe('custom');
    expect(dateParams.get('time')).toBe('custom');
    expect(dateParams.get('from')).toBe('2026-05-01');
    expect(dateParams.get('to')).toBe('2026-05-01');
    expect(screen.getByText('Custom: 2026-05-01 to 2026-05-01')).toHaveAttribute('data-state', 'active');
    expect(screen.getByText('No loaded calls match the current search.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Clear filters/i }));

    const clearedParams = new URLSearchParams(window.location.search);
    expect(clearedParams.get('model')).toBeNull();
    expect(clearedParams.get('effort')).toBeNull();
    expect(clearedParams.get('confidence')).toBeNull();
    expect(clearedParams.get('date')).toBeNull();
    expect(clearedParams.get('time')).toBeNull();
    expect(clearedParams.get('from')).toBeNull();
    expect(clearedParams.get('to')).toBeNull();
    expect(screen.queryByText('Custom: 2026-05-01 to 2026-05-01')).not.toBeInTheDocument();
    expect(screen.getByText('thread-9f3a1c')).toBeInTheDocument();
  });

  it('ports the legacy invalid custom date range status', () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText('Global start date'), { target: { value: '2026-06-02' } });
    fireEvent.change(screen.getByLabelText('Global end date'), { target: { value: '2026-06-01' } });

    expect(screen.getByText('Invalid date range')).toHaveAttribute('data-state', 'error');
    expect(screen.getByText('No loaded calls match the current search.')).toBeInTheDocument();
  });

  it('ports legacy preset date range status labels', () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText('Global time filter'), { target: { value: 'last-7-days' } });

    expect(screen.getByText(/^Last 7 days: \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}$/)).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('clears stale legacy pricing aliases when confidence is reset', () => {
    window.history.replaceState(null, '', '/?view=overview&pricing=official');
    render(<App />);

    expect(screen.getByLabelText('Global confidence filter')).toHaveValue('cost-exact');

    fireEvent.change(screen.getByLabelText('Global confidence filter'), { target: { value: 'all' } });

    const params = new URLSearchParams(window.location.search);
    expect(params.get('confidence')).toBeNull();
    expect(params.get('pricing')).toBeNull();
  });

  it('keeps detailed Calls filters in Calls workspace instead duplicating shell strip', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));

    expect(screen.queryByLabelText('Global model filter')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Time filter')).toBeInTheDocument();
  });
});
