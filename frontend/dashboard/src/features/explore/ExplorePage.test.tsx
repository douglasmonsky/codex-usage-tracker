import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExplorePage, type ExplorePageProps } from './ExplorePage';

const renderedModes: string[] = [];

vi.mock('../calls/CallsPage', () => ({
  CallsPage: () => {
    renderedModes.push('calls');
    return <h1>Calls workspace</h1>;
  },
}));

vi.mock('../threads/ThreadsPage', () => ({
  ThreadsPage: () => {
    renderedModes.push('threads');
    return <h1>Threads workspace</h1>;
  },
}));

const props = {} as ExplorePageProps;

describe('ExplorePage', () => {
  beforeEach(() => {
    renderedModes.length = 0;
    const values = new Map<string, string>();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
      },
    });
    window.history.replaceState(null, '', '/?view=explore');
  });

  it('renders a two-option accessible switch and mounts only Calls by default', () => {
    render(<ExplorePage {...props} />);

    const tabs = within(screen.getByRole('tablist', { name: 'Explore mode' }));
    expect(tabs.getAllByRole('tab')).toHaveLength(2);
    expect(tabs.getByRole('tab', { name: 'Calls' })).toHaveAttribute('aria-selected', 'true');
    expect(tabs.queryByRole('tab', { name: 'Tools' })).not.toBeInTheDocument();
    expect(tabs.queryByRole('tab', { name: 'Files' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Calls workspace' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Threads workspace' })).not.toBeInTheDocument();
    expect(renderedModes).toEqual(['calls']);
  });

  it('points out the Calls and Threads switch on the first Explore visit', () => {
    render(<ExplorePage {...props} />);

    expect(screen.getByRole('note', { name: 'Explore mode hint' })).toHaveTextContent(
      'Switch between individual calls and grouped threads here',
    );
    fireEvent.click(screen.getByRole('tab', { name: 'Threads' }));
    expect(screen.queryByText(/Switch between individual calls/i)).not.toBeInTheDocument();
    expect(window.localStorage.getItem('codexUsageExploreModeHintV1')).toBe('dismissed');
  });

  it('normalizes a legacy Threads deep link and does not mount Calls', () => {
    window.history.replaceState(null, '', '/?view=threads&thread_key=session%3Athread-4');
    render(<ExplorePage {...props} />);

    expect(screen.getByRole('heading', { name: 'Threads workspace' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Calls workspace' })).not.toBeInTheDocument();
    expect(window.location.search).toContain('view=explore');
    expect(window.location.search).toContain('mode=threads');
    expect(window.location.search).toContain('thread_key=session%3Athread-4');
    expect(renderedModes).toEqual(['threads']);
  });

  it('switches modes, restores browser history, and preserves inactive filters', () => {
    window.history.replaceState(
      null,
      '',
      '/?view=explore&mode=calls&call_q=cache&sort=cost&page=3&threads_page=2',
    );
    render(<ExplorePage {...props} />);

    fireEvent.click(screen.getByRole('tab', { name: 'Threads' }));
    expect(screen.getByRole('heading', { name: 'Threads workspace' })).toBeInTheDocument();
    expect(window.location.search).toContain('mode=threads');
    expect(window.location.search).toContain('call_q=cache');
    expect(window.location.search).toContain('calls_sort=cost');
    expect(window.location.search).toContain('calls_page=3');
    expect(window.location.search).toContain('page=2');

    act(() => {
      window.history.replaceState(null, '', '/?view=explore&mode=calls&call_q=cache&sort=cost&page=3');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(screen.getByRole('heading', { name: 'Calls workspace' })).toBeInTheDocument();
  });

  it('supports arrow, Home, and End keys without mounting both modes', () => {
    render(<ExplorePage {...props} />);

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Calls' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Threads' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: 'Threads workspace' })).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Threads' }), { key: 'Home' });
    expect(screen.getByRole('tab', { name: 'Calls' })).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Calls' }), { key: 'End' });
    expect(screen.getByRole('tab', { name: 'Threads' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('heading', { name: 'Calls workspace' })).not.toBeInTheDocument();
  });
});
