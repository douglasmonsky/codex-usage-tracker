import {
  App,
  describe,
  expect,
  fireEvent,
  installAppTestHooks,
  it,
  render,
  screen,
  waitFor,
  within,
} from './test-utils/appTestHarness';

describe('React dashboard Explore workspace', () => {
  installAppTestHooks();

  it('offers only Calls and Threads and preserves each mode URL state', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=explore&mode=calls&call_q=thread-9f3a&sort=cache&page=3'
        + '&thread_q=thread-0e16&risk=Low&threads_page=2',
    );

    render(<App />);

    const tabs = within(screen.getByRole('tablist', { name: 'Explore mode' }));
    expect(tabs.getAllByRole('tab')).toHaveLength(2);
    expect(tabs.queryByRole('tab', { name: 'Tools' })).not.toBeInTheDocument();
    expect(tabs.queryByRole('tab', { name: 'Files' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();

    fireEvent.click(tabs.getByRole('tab', { name: 'Threads' }));
    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('view')).toBe('explore');
      expect(params.get('mode')).toBe('threads');
      expect(params.get('call_q')).toBe('thread-9f3a');
      expect(params.get('calls_sort')).toBe('cache');
      expect(params.get('calls_page')).toBe('3');
      expect(params.get('thread_q')).toBe('thread-0e16');
      expect(params.get('risk')).toBe('Low');
      expect(params.get('page')).toBe('2');
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Calls' }));
    expect(screen.getByRole('heading', { name: 'Calls' })).toBeInTheDocument();
    await waitFor(() => {
      const params = new URLSearchParams(window.location.search);
      expect(params.get('mode')).toBe('calls');
      expect(params.get('sort')).toBe('cache');
      expect(params.get('page')).toBe('3');
      expect(params.get('threads_page')).toBe('2');
    });
  });

  it('normalizes legacy Threads URLs without mounting Calls first', () => {
    window.history.replaceState(null, '', '/?view=threads&thread_key=fixture-thread-key-0');

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Calls' })).not.toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('view')).toBe('explore');
    expect(new URLSearchParams(window.location.search).get('mode')).toBe('threads');
  });
});
