import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  App,
  installAppTestHooks,
  navigateApp,
} from '../../test-utils/appTestHarness';
import { LegacyWorkbenchNotice } from './LegacyWorkbenchNotice';

const legacyRoutes = [
  ['investigator', 'Investigate'],
  ['compression-lab', 'Compression Lab'],
  ['cache-context', 'Cache And Context'],
  ['diagnostics', 'Diagnostics Notebook'],
  ['reports', 'Reports'],
] as const;

describe('LegacyWorkbenchNotice', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it.each(legacyRoutes)(
    'renders %s as a notice-only route without historical API calls',
    async (viewId, label) => {
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      render(<LegacyWorkbenchNotice viewId={viewId} onNavigate={vi.fn()} />);

      expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
      expect(screen.getByText('0.24.x')).toBeInTheDocument();
      expect(screen.getByText('0.25.0')).toBeInTheDocument();
      expect(
        screen.getByText(
          'CLI, HTTP API, export, and full-profile MCP compatibility remain available through 0.24.x.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Copy replacement prompt' })).toBeInTheDocument();
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it('copies the replacement prompt and opens supported console surfaces', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const onNavigate = vi.fn();

    render(<LegacyWorkbenchNotice viewId="compression-lab" onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole('button', { name: 'Copy replacement prompt' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('usage_analyze')));
    expect(screen.getByRole('status')).toHaveTextContent('Replacement prompt copied');

    fireEvent.click(screen.getByRole('button', { name: 'Open Evidence' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open Explore' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open Limits' }));

    expect(onNavigate.mock.calls).toEqual([['evidence'], ['explore'], ['limits']]);
  });
});

describe('legacy workbench direct routes', () => {
  installAppTestHooks();

  it.each(legacyRoutes)(
    'routes %s to the shared notice without historical API calls',
    async (viewId, label) => {
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);
      navigateApp(`/?view=${viewId}`);

      render(<App />);

      expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );
});
