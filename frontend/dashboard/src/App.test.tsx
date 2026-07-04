import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen } from './test-utils/appTestHarness';

describe('React dashboard shell overview', () => {
  installAppTestHooks();

  it('renders overview workspace by default', () => {
    render(<App />);

expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
expect(screen.getAllByText('Total Tokens').length).toBeGreaterThan(0);
expect(screen.getByRole('heading', { name: 'Needs Attention' })).toBeInTheDocument();
expect(screen.getByText('Long Thread: data-engine-refactor')).toBeInTheDocument();
expect(screen.getByRole('table', { name: 'Recent calls' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'Showing latest 6 visible aggregate calls from 8 loaded of 8 available active-history rows (500 row request). Rows open Call Investigator. - Stored snapshot loaded just now',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }),
    ).toBeInTheDocument();
    const investigatorRow = screen.getByLabelText('Open call row in investigator for thread-9f3a1c codex-1');
    expect(investigatorRow.tagName).toBe('TR');
    fireEvent.click(investigatorRow);
expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
});

it('opens the investigator workbench from overview findings', () => {
render(<App />);
fireEvent.click(screen.getByRole('button', { name: 'Review finding 1: Long Thread: data-engine-refactor' }));
expect(screen.getByRole('heading', { name: 'Investigator Workbench' })).toBeInTheDocument();
expect(window.location.search).toContain('view=investigator');
expect(window.location.search).toContain('finding=1');
});

});
