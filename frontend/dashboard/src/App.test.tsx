import { App, describe, expect, fireEvent, installAppTestHooks, it, render, screen } from './test-utils/appTestHarness';

describe('React dashboard shell overview', () => {
  installAppTestHooks();

  it('renders overview workspace by default', () => {
    render(<App />);

expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
expect(screen.getAllByText('Total Tokens').length).toBeGreaterThan(0);
expect(screen.queryByRole('heading', { name: 'Needs attention' })).not.toBeInTheDocument();
expect(screen.getByRole('table', { name: 'Overview calls' })).toBeInTheDocument();
    expect(screen.getByText('Loaded 8 of 8 available calls')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText('thread-9f3a1c'));
expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
});

it('opens the investigator workbench from primary navigation', () => {
render(<App />);
fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));
expect(screen.getByRole('heading', { name: 'Investigate' })).toBeInTheDocument();
expect(window.location.search).toContain('view=investigator');
});

});
