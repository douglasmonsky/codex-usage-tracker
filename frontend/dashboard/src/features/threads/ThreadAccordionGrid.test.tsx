import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { expect, it, vi } from 'vitest';
import type { CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { threadColumns } from '../shared/tables';
import { ThreadAccordionGrid, type ThreadAccordionGridProps } from './ThreadAccordionGrid';
import {
  threadRowIdentity,
  threadRowSelector,
  threadSelectorIdentity,
} from './threadsUrlState';

const fixtureThread = fixtureModel.threads[0];
const fixtureCall = fixtureModel.calls[0];
const callFixture = (id: string): CallRow => ({ ...fixtureCall, id });
const defaultProps: ThreadAccordionGridProps = {
  ariaLabel: 'Thread leaderboard',
  threads: fixtureModel.threads,
  columns: threadColumns,
  sorting: [],
  onSortingChange: vi.fn(),
  preferences: {
    density: 'compact',
    setDensity: vi.fn(),
    columnVisibility: {},
    setColumnVisibility: vi.fn(),
    restoreDefaults: vi.fn(),
  },
  expandedThreadIdentity: null,
  expandedCalls: [],
  totalCallCount: 0,
  loadMoreCallCount: 100,
  canLoadMoreCalls: false,
  loadingCalls: false,
  loadingMoreCalls: false,
  partialError: null,
  callSort: 'newest',
  callSortDirection: 'desc',
  onToggleThread: vi.fn(),
  onRetryCalls: vi.fn(),
  onLoadMoreCalls: vi.fn(),
  onCallSortChange: vi.fn(),
  onCallSortDirectionChange: vi.fn(),
  onOpenInvestigator: vi.fn(),
  onCopyCallLink: vi.fn(),
};

function renderGrid(overrides: Partial<ThreadAccordionGridProps> = {}) {
  const props = { ...defaultProps, ...overrides };
  render(<ThreadAccordionGrid {...props} />);
  return props;
}

it('toggles one inline thread without activating an investigator', () => {
  const onToggleThread = vi.fn();
  const onOpenInvestigator = vi.fn();
  renderGrid({ expandedThreadIdentity: null, onToggleThread, onOpenInvestigator });
  const row = screen.getByRole('row', { name: `Expand calls for ${fixtureThread.name}` });

  fireEvent.click(row);
  fireEvent.keyDown(row, { key: 'Enter' });
  fireEvent.keyDown(row, { key: ' ' });

  expect(onToggleThread).toHaveBeenCalledTimes(3);
  expect(onToggleThread).toHaveBeenLastCalledWith(threadRowSelector(fixtureThread));
  expect(onOpenInvestigator).not.toHaveBeenCalled();
});

it('treats a real browser double-click sequence as one logical toggle', () => {
  const onToggleThread = vi.fn();
  const onOpenInvestigator = vi.fn();
  renderGrid({ onToggleThread, onOpenInvestigator });
  const row = screen.getByRole('row', { name: `Expand calls for ${fixtureThread.name}` });

  fireEvent.click(row, { detail: 1 });
  fireEvent.click(row, { detail: 2 });
  fireEvent.doubleClick(row, { detail: 2 });

  expect(onToggleThread).toHaveBeenCalledOnce();
  expect(onToggleThread).toHaveBeenCalledWith(threadRowSelector(fixtureThread));
  expect(onOpenInvestigator).not.toHaveBeenCalled();
});

it('keeps duplicate display labels distinct and emits canonical row selectors', () => {
  const onToggleThread = vi.fn();
  const duplicateThreads = [
    { ...fixtureThread, threadKey: 'session:019e374d-c19f-7da3-a44f-8de043a7a64e', name: 'Shared label' },
    { ...fixtureThread, threadKey: 'session:029e374d-c19f-7da3-a44f-8de043a7a64e', name: 'Shared label' },
  ];
  renderGrid({
    threads: duplicateThreads,
    expandedThreadIdentity: threadRowIdentity(duplicateThreads[1]),
    onToggleThread,
  });

  expect(screen.getAllByRole('row', { name: 'Expand calls for Shared label' })).toHaveLength(1);
  const expanded = screen.getByRole('row', { name: 'Collapse calls for Shared label' });
  expect(expanded.id).toContain(encodeURIComponent(duplicateThreads[1].threadKey));
  fireEvent.click(expanded);
  expect(onToggleThread).toHaveBeenCalledWith(threadRowSelector(duplicateThreads[1]));
});

it('aligns disclosure inside a truncated identity cell and quiets unloaded metadata', () => {
  const lazyThread = {
    ...fixtureThread,
    name: '019f6393-a720-7da2-bb96-5ee5f4b55506',
    initiatorSummary: 'mostly_user',
    modelSummary: 'Load thread calls',
    effortSummary: 'Load thread calls',
  };
  renderGrid({ threads: [lazyThread] });

  const row = screen.getByRole('row', { name: `Expand calls for ${lazyThread.name}` });
  const identityCell = within(row).getAllByRole('gridcell')[0];
  expect(within(identityCell).getByText('›')).toBeInTheDocument();
  expect(screen.getByTitle(lazyThread.name)).toHaveTextContent(lazyThread.name);
  expect(screen.getByText('Mostly User')).toBeInTheDocument();
  expect(screen.getByTitle('Expand this thread to load its model mix')).toHaveTextContent('—');
  expect(screen.getByTitle('Expand this thread to load its effort mix')).toHaveTextContent('—');
  expect(screen.queryByText('Load thread calls')).not.toBeInTheDocument();

  const threadHeader = screen.getByRole('columnheader', { name: 'Thread' });
  expect(threadHeader).toHaveStyle({ width: '280px' });
});

it('renders an associated expanded region and explicit child actions', () => {
  const onOpenInvestigator = vi.fn();
  const onCopyCallLink = vi.fn();
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    expandedCalls: [fixtureCall],
    onOpenInvestigator,
    onCopyCallLink,
  });

  expect(screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` })).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` })).toHaveAttribute('aria-level', '1');
  expect(screen.getByRole('treegrid', { name: 'Thread leaderboard' })).toBeInTheDocument();
  const callsRegion = screen.getByRole('region', { name: `Calls for ${fixtureThread.name}` });
  expect(callsRegion).toBeInTheDocument();
  expect(callsRegion).toHaveAttribute(
    'aria-describedby',
    screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` }).id,
  );
  expect(within(callsRegion).getByRole('button', { name: /Open investigator for thread call/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Open investigator for thread call/i }));
  fireEvent.click(screen.getByRole('button', { name: /Copy link for thread call/i }));
  expect(onOpenInvestigator).toHaveBeenCalledWith(fixtureCall.id);
  expect(onCopyCallLink).toHaveBeenCalledWith(fixtureCall.id);
});

it('uses density-specific estimates and rendered spacing for parents and calls', () => {
  const { rerender } = render(<ThreadAccordionGrid
    {...defaultProps}
    expandedThreadIdentity={threadRowIdentity(fixtureThread)}
    expandedCalls={[fixtureCall]}
  />);
  const compactParent = screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` });
  const compactCall = screen.getByRole('button', { name: /Open investigator for thread call/i }).closest('[data-accordion-item]');
  expect(compactParent).toHaveStyle({ minHeight: '44px' });
  expect(compactCall).toHaveStyle({ minHeight: '96px' });

  rerender(<ThreadAccordionGrid
    {...defaultProps}
    preferences={{ ...defaultProps.preferences, density: 'comfortable' }}
    expandedThreadIdentity={threadRowIdentity(fixtureThread)}
    expandedCalls={[fixtureCall]}
  />);
  expect(screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` })).toHaveStyle({ minHeight: '56px' });
  expect(screen.getByRole('button', { name: /Open investigator for thread call/i }).closest('[data-accordion-item]')).toHaveStyle({ minHeight: '128px' });
});

it('keeps a thousand child calls bounded to one virtual window', () => {
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    expandedCalls: Array.from({ length: 1_000 }, (_, index) => callFixture(`call-${index}`)),
    totalCallCount: 1_000,
  });
  const scroller = screen.getByTestId('thread-accordion-scroller');
  expect(scroller).toHaveAttribute('data-virtualized', 'true');
  expect(scroller.querySelectorAll('[data-accordion-item]').length).toBeLessThan(60);
});

it('shows loaded progress and a loading-more state', () => {
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    expandedCalls: [fixtureCall],
    totalCallCount: 3,
    loadingMoreCalls: true,
  });

  expect(screen.getByRole('status')).toHaveTextContent('1 of 3 calls loaded Loading more calls.');
});

it('shows the concise aggregate summary and explicit collapse action', () => {
  const onToggleThread = vi.fn();
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    expandedCalls: [fixtureCall],
    totalCallCount: fixtureThread.turns,
    onToggleThread,
  });

  const region = screen.getByRole('region', { name: `Calls for ${fixtureThread.name}` });
  expect(region).toHaveTextContent('Total tokens');
  expect(region).toHaveTextContent('Cached / uncached');
  expect(region).toHaveTextContent('Cache ratio');
  expect(region).toHaveTextContent('Cost / credits');
  expect(region).toHaveTextContent('Peak context');
  expect(region).toHaveTextContent('Duration');
  expect(region).toHaveTextContent('Latest');
  fireEvent.click(within(region).getByRole('button', { name: `Collapse calls for ${fixtureThread.name}` }));
  expect(onToggleThread).toHaveBeenCalledWith(threadRowSelector(fixtureThread));
});

it('shows a partial error with an explicit retry action', () => {
  const onRetryCalls = vi.fn();
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    partialError: 'The next page could not be loaded.',
    onRetryCalls,
  });

  expect(screen.getByText('The next page could not be loaded.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading thread calls' }));
  expect(onRetryCalls).toHaveBeenCalledOnce();
});

it('labels boot calls as a stored snapshot after an initial query failure', () => {
  renderGrid({
    expandedThreadIdentity: threadRowIdentity(fixtureThread),
    expandedCalls: [fixtureCall],
    totalCallCount: fixtureThread.turns,
    initialError: 'The focused call request failed.',
    storedSnapshot: true,
  });

  expect(screen.getByText('Stored snapshot')).toBeInTheDocument();
  expect(screen.getByText('The focused call request failed.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Retry loading thread calls' })).toBeInTheDocument();
});

it('uses the approved aggregate empty-state copy', () => {
  renderGrid({ expandedThreadIdentity: threadRowIdentity(fixtureThread) });
  expect(screen.getByText('No aggregate calls are available for this thread.')).toBeInTheDocument();
});

it('retains focus on the parent while its inline region opens', () => {
  function FocusHarness() {
    const [expandedThreadIdentity, setExpandedThreadIdentity] = useState<string | null>(null);
    return <ThreadAccordionGrid
      {...defaultProps}
      expandedThreadIdentity={expandedThreadIdentity}
      expandedCalls={expandedThreadIdentity ? [fixtureCall] : []}
      onToggleThread={selector => setExpandedThreadIdentity(current => {
        const identity = threadSelectorIdentity(selector);
        return current === identity ? null : identity;
      })}
    />;
  }
  render(<FocusHarness />);
  const row = screen.getByRole('row', { name: `Expand calls for ${fixtureThread.name}` });
  row.focus();
  fireEvent.keyDown(row, { key: 'Enter' });

  expect(screen.getByRole('row', { name: `Collapse calls for ${fixtureThread.name}` })).toHaveFocus();
});

it('keeps complete call copy in the stacked narrow-screen structure', () => {
  renderGrid({ expandedThreadIdentity: threadRowIdentity(fixtureThread), expandedCalls: [fixtureCall] });
  const region = screen.getByRole('treegrid', { name: 'Thread leaderboard' });

  expect(region).toHaveTextContent(fixtureCall.model);
  expect(region).toHaveTextContent(fixtureCall.effort);
  expect(region).toHaveTextContent('tokens');
  expect(region).toHaveTextContent('Context');
  expect(region).toHaveTextContent('Open');
  expect(region).toHaveTextContent('Copy');
});
