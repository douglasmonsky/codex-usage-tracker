import {
  App,
  describe,
  expect,
  installAppTestHooks,
  it,
  render,
  screen,
} from './test-utils/appTestHarness';

describe('React dashboard shell global filters', () => {
  installAppTestHooks();

  it('keeps detailed filters inside the canonical Calls workspace', () => {
    window.history.replaceState(null, '', '/?view=explore&mode=calls');

    render(<App />);

    expect(screen.queryByLabelText('Global model filter')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Time filter')).toBeInTheDocument();
  });
});
