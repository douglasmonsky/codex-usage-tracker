import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen } from './test-utils/appTestHarness';

describe('React dashboard shell overview', () => {
  installAppTestHooks();

  it('renders overview workspace by default', () => {
    render(<App />);

expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
expect(screen.getByText('Total tokens')).toBeInTheDocument();
expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument();
expect(screen.getByText('Long Thread: data-engine-refactor')).toBeInTheDocument();
expect(screen.getByRole('table', { name: 'Recent calls' })).toBeInTheDocument();
    expect(screen.getByText('Loaded 8 of 8 available calls')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }),
    ).toBeInTheDocument();
    const investigatorRow = screen.getByRole('row', { name: 'Open Call Investigator for thread-9f3a1c' });
    fireEvent.click(investigatorRow);
expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
});

it('opens the investigator workbench from overview findings', () => {
render(<App />);
fireEvent.click(screen.getByRole('button', { name: 'Inspect evidence' }));
expect(screen.getByRole('heading', { name: 'Investigate' })).toBeInTheDocument();
expect(window.location.search).toContain('view=investigator');
expect(window.location.search).toContain('finding=1');
});

});
