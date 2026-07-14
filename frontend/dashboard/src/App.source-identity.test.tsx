import { dashboardSourceIdentityFromPayload } from './data/queryRuntime';
import {
  App,
  describe,
  expect,
  fireEvent,
  installAppTestHooks,
  it,
  render,
  screen,
} from './test-utils/appTestHarness';

describe('React dashboard source identity and route preservation', () => {
  installAppTestHooks();

  it('derives stable source identity without including API credentials', () => {
    const payload = {
      api_token: 'first-secret',
      latest_refresh_at: 'revision-1',
      payload_cache_key: 'source-a',
      payload_cache_version: 1,
      rows: [],
    };
    const first = dashboardSourceIdentityFromPayload(payload);
    const second = dashboardSourceIdentityFromPayload({ ...payload, api_token: 'rotated-secret' });

    expect(first).toEqual({ sourceKey: '1:source-a', sourceRevision: 'revision-1' });
    expect(second).toEqual(first);
    expect(JSON.stringify(first)).not.toContain('secret');
  });

  it('preserves calls drill-down state across same-route browser navigation', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /^Calls$/i }));
    fireEvent.click(screen.getByRole('button', { name: /Call Details/i }));
    const row = screen.getByText('thread-7b2e91').closest('tr');
    expect(row).not.toBeNull();
    fireEvent.mouseEnter(row as HTMLTableRowElement);
    expect(screen.getByText('thread-7b2e91 / o4-mini')).toBeInTheDocument();

    window.history.replaceState(null, '', '/?view=calls&qa=route-preservation');
    fireEvent.popState(window);

    expect(screen.getByText('thread-7b2e91 / o4-mini')).toBeInTheDocument();
  });
});
