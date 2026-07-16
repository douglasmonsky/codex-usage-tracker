import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, it, vi } from 'vitest';
import type { CallRow } from '../../api/types';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { threadColumns } from '../shared/tables';
import { ThreadAccordionGrid, type ThreadAccordionGridProps } from './ThreadAccordionGrid';

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
  expandedThreadName: null,
  expandedCalls: [],
  totalCallCount: 0,
  loadingCalls: false,
  loadingMoreCalls: false,
  partialError: null,
  callSort: 'newest',
  callSortDirection: 'desc',
  onToggleThread: vi.fn(),
  onRetryCalls: vi.fn(),
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
  renderGrid({ expandedThreadName: null, onToggleThread, onOpenInvestigator });
  const row = screen.getByRole('row', { name: new RegExp(fixtureThread.name, 'i') });

  fireEvent.click(row);
  fireEvent.doubleClick(row);
  fireEvent.keyDown(row, { key: 'Enter' });
  fireEvent.keyDown(row, { key: ' ' });

  expect(onToggleThread).toHaveBeenCalledTimes(4);
  expect(onToggleThread).toHaveBeenLastCalledWith(fixtureThread.name);
  expect(onOpenInvestigator).not.toHaveBeenCalled();
});

it('renders an associated expanded region and explicit child actions', () => {
  const onOpenInvestigator = vi.fn();
  const onCopyCallLink = vi.fn();
  renderGrid({
    expandedThreadName: fixtureThread.name,
    expandedCalls: [fixtureCall],
    onOpenInvestigator,
    onCopyCallLink,
  });

  expect(screen.getByRole('row', { name: new RegExp(fixtureThread.name, 'i') })).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('region', { name: `Calls for ${fixtureThread.name}` })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Open investigator for thread call/i }));
  fireEvent.click(screen.getByRole('button', { name: /Copy link for thread call/i }));
  expect(onOpenInvestigator).toHaveBeenCalledWith(fixtureCall.id);
  expect(onCopyCallLink).toHaveBeenCalledWith(fixtureCall.id);
});

it('keeps a thousand child calls bounded to one virtual window', () => {
  renderGrid({
    expandedThreadName: fixtureThread.name,
    expandedCalls: Array.from({ length: 1_000 }, (_, index) => callFixture(`call-${index}`)),
    totalCallCount: 1_000,
  });
  const scroller = screen.getByTestId('thread-accordion-scroller');
  expect(scroller).toHaveAttribute('data-virtualized', 'true');
  expect(scroller.querySelectorAll('[data-accordion-item]').length).toBeLessThan(60);
});

it('shows loaded progress and a loading-more state', () => {
  renderGrid({
    expandedThreadName: fixtureThread.name,
    expandedCalls: [fixtureCall],
    totalCallCount: 3,
    loadingMoreCalls: true,
  });

  expect(screen.getByText('1 of 3 calls loaded')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Loading more calls');
});

it('shows a partial error with an explicit retry action', () => {
  const onRetryCalls = vi.fn();
  renderGrid({
    expandedThreadName: fixtureThread.name,
    partialError: 'The next page could not be loaded.',
    onRetryCalls,
  });

  expect(screen.getByText('The next page could not be loaded.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading thread calls' }));
  expect(onRetryCalls).toHaveBeenCalledOnce();
});

it('retains focus on the parent while its inline region opens', () => {
  function FocusHarness() {
    const [expandedThreadName, setExpandedThreadName] = useState<string | null>(null);
    return <ThreadAccordionGrid
      {...defaultProps}
      expandedThreadName={expandedThreadName}
      expandedCalls={expandedThreadName ? [fixtureCall] : []}
      onToggleThread={name => setExpandedThreadName(current => current === name ? null : name)}
    />;
  }
  render(<FocusHarness />);
  const row = screen.getByRole('row', { name: new RegExp(fixtureThread.name, 'i') });
  row.focus();
  fireEvent.keyDown(row, { key: 'Enter' });

  expect(screen.getByRole('row', { name: new RegExp(fixtureThread.name, 'i') })).toHaveFocus();
});

it('keeps complete call copy in the stacked narrow-screen structure', () => {
  renderGrid({ expandedThreadName: fixtureThread.name, expandedCalls: [fixtureCall] });
  const region = screen.getByRole('region', { name: `Calls for ${fixtureThread.name}` });

  expect(region).toHaveTextContent(fixtureCall.model);
  expect(region).toHaveTextContent(fixtureCall.effort);
  expect(region).toHaveTextContent('tokens');
  expect(region).toHaveTextContent('Context');
  expect(region).toHaveTextContent('Open');
  expect(region).toHaveTextContent('Copy');
});
