# Threads Inline Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Threads table's detached inspector and implicit latest-call navigation with a single-open inline accordion that progressively loads and virtualizes every aggregate call in the selected thread.

**Architecture:** Keep query and URL orchestration in `ThreadsPage`, but replace Table mode's generic fixed-height grid with a thread-specific `ThreadAccordionGrid`. The new grid flattens parent thread rows, one expansion summary, child calls, and loading/error status into a single `@tanstack/react-virtual` sequence, so the entire interaction uses one scroll container and a bounded DOM. Existing `/api/threads` and `/api/thread-calls` contracts, Cache Frontier, Lifecycle, exports, and explicit Call Investigator routes remain unchanged.

**Tech Stack:** React 19, TypeScript, TanStack React Table, TanStack React Query, TanStack React Virtual, CSS Modules, Vitest/Testing Library, Playwright, Vite, Python release checks.

## Global Constraints

- Keep the dashboard aggregate-only; do not call raw-context APIs or embed indexed snippets.
- Keep exactly one expanded thread; clicking the same row collapses it and clicking another row switches it.
- Parent thread click, double-click, Enter, and Space must never open Call Investigator.
- Load all `/api/thread-calls` pages progressively in the selected sort order, with visible progress, partial-error preservation, and retry.
- Keep rendered child-call elements bounded for very large threads and avoid nested vertical scroll containers.
- Preserve Threads filters, sorting, column preferences, exports, legacy URL hydration, direct `thread=` links, Cache Frontier, and Lifecycle.
- Keep per-call **Open investigator** and **Copy link** actions explicit and record-specific.
- Preserve synthetic-only fixtures, screenshots, and documentation assets.
- Do not change server schemas, thread attachment semantics, privacy semantics, or Call Investigator.

---

## File Structure

- Create `frontend/dashboard/src/features/threads/threadCallLoading.ts`: deduplicate paged call rows and decide when progressive loading should continue.
- Create `frontend/dashboard/src/features/threads/threadCallLoading.test.ts`: pure pagination/deduplication/error-stop tests.
- Create `frontend/dashboard/src/features/explore/EvidenceGridControls.tsx`: reusable density/column chooser extracted without changing grid behavior.
- Modify `frontend/dashboard/src/features/explore/EvidenceGrid.tsx`: consume the extracted controls; retain its fixed-height virtualization unchanged.
- Create `frontend/dashboard/src/features/threads/ThreadAccordionGrid.tsx`: table header, flattened virtual sequence, disclosure rows, child calls, status/retry row, and responsive roles.
- Create `frontend/dashboard/src/features/threads/ThreadAccordionGrid.test.tsx`: interaction, accessibility, virtualization, and mobile tests.
- Rename `frontend/dashboard/src/features/threads/ThreadInspector.tsx` to `frontend/dashboard/src/features/threads/ThreadAccordionRows.tsx`: retain only call controls and compact child-call presentation; remove detached inspector analytics.
- Modify `frontend/dashboard/src/features/threads/ThreadsPage.tsx`: nullable expansion identity, progressive query loop, stale-key isolation, toggle/collapse logic, and new grid props.
- Modify `frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx`: render the accordion in Table mode and remove the detached inspector/row activation path.
- Modify `frontend/dashboard/src/features/threads/threadsUrlState.ts`: stop writing child-page counts while preserving legacy hydration and child sort state.
- Modify `frontend/dashboard/src/features/threads/threadsUrlState.test.ts`: pin collapse and legacy normalization behavior.
- Modify `frontend/dashboard/src/features/threads/ThreadsPage.module.css`: accordion hierarchy, responsive call cards, loading/error states, and 44px controls.
- Modify `frontend/dashboard/src/App.threads.test.tsx`: workspace-level toggle, progressive loading, stale result, partial retry, URL, and investigator-action coverage.
- Modify `tests/playwright/dashboard-react.spec.mjs`: browser flow for inline expansion and explicit child navigation at desktop and narrow widths.
- Modify `docs/dashboard-guide.md`: replace inspector/activation instructions with inline expansion behavior.
- Modify `scripts/capture_dashboard_screenshots.mjs`: ensure the synthetic Threads screenshot opens a real inline expansion.
- Regenerate `docs/assets/dashboard-threads.png`, packaged documentation copies, and `src/codex_usage_tracker/plugin_data/dashboard/react/assets/*` through the existing build/screenshot commands.

---

### Task 1: Progressive Call Loading And URL Contract

**Files:**
- Create: `frontend/dashboard/src/features/threads/threadCallLoading.ts`
- Create: `frontend/dashboard/src/features/threads/threadCallLoading.test.ts`
- Modify: `frontend/dashboard/src/features/threads/threadsUrlState.ts`
- Modify: `frontend/dashboard/src/features/threads/threadsUrlState.test.ts`

**Interfaces:**
- Produces: `dedupeThreadCallPages(pages: ExploreCallsPage[], fallback: CallRow[]): CallRow[]`
- Produces: `shouldFetchNextThreadCallPage(state: ProgressiveThreadCallState): boolean`
- Preserves: `readInitialSelectedThreadParam`, `readThreadCallSortParam`, `readThreadCallSortDirectionParam`
- Changes: `ThreadsViewLinkState` no longer accepts `visibleThreadCallCount`; `buildThreadsViewLink` always deletes `thread_call_page`

- [ ] **Step 1: Write failing progressive-loading tests**

Create `threadCallLoading.test.ts` with concrete duplicate-boundary and error-stop cases:

```ts
import { describe, expect, it } from 'vitest';
import type { CallRow } from '../../api/types';
import type { ExploreCallsPage } from '../../data/contracts/explore';
import { dedupeThreadCallPages, shouldFetchNextThreadCallPage } from './threadCallLoading';

const call = (id: string): CallRow => ({ id } as CallRow);
const page = (rows: CallRow[]): ExploreCallsPage => ({
  schema: 'codex-usage-tracker-thread-calls-v1',
  rows,
  rowCount: rows.length,
  totalMatchedRows: 3,
  limit: 100,
  offset: 0,
  hasMore: false,
  nextOffset: null,
  rawContextIncluded: false,
  threadKey: 'thread-alpha',
});

describe('thread call progressive loading', () => {
  it('deduplicates page boundaries by record id while preserving first-seen order', () => {
    expect(dedupeThreadCallPages([
      page([call('a'), call('b')]),
      page([call('b'), call('c')]),
    ], [])).map(row => row.id)).toEqual(['a', 'b', 'c']);
  });

  it('uses snapshot calls only before focused pages arrive', () => {
    expect(dedupeThreadCallPages([], [call('snapshot')]).map(row => row.id)).toEqual(['snapshot']);
    expect(dedupeThreadCallPages([page([call('live')])], [call('snapshot')]).map(row => row.id)).toEqual(['live']);
  });

  it('continues only for an expanded, healthy, idle query with another page', () => {
    const ready = {
      expanded: true,
      enabled: true,
      hasNextPage: true,
      isFetchingNextPage: false,
      isFetchNextPageError: false,
    };
    expect(shouldFetchNextThreadCallPage(ready)).toBe(true);
    expect(shouldFetchNextThreadCallPage({ ...ready, expanded: false })).toBe(false);
    expect(shouldFetchNextThreadCallPage({ ...ready, isFetchingNextPage: true })).toBe(false);
    expect(shouldFetchNextThreadCallPage({ ...ready, isFetchNextPageError: true })).toBe(false);
  });
});
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/threads/threadCallLoading.test.ts
```

Expected: FAIL because `threadCallLoading.ts` does not exist.

- [ ] **Step 3: Implement the minimal loading helpers**

Create `threadCallLoading.ts`:

```ts
import type { CallRow } from '../../api/types';
import type { ExploreCallsPage } from '../../data/contracts/explore';

export type ProgressiveThreadCallState = {
  expanded: boolean;
  enabled: boolean;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFetchNextPageError: boolean;
};

export function dedupeThreadCallPages(pages: ExploreCallsPage[], fallback: CallRow[]): CallRow[] {
  const source = pages.length ? pages.flatMap(page => page.rows) : fallback;
  const seen = new Set<string>();
  return source.filter(row => {
    if (seen.has(row.id)) return false;
    seen.add(row.id);
    return true;
  });
}

export function shouldFetchNextThreadCallPage(state: ProgressiveThreadCallState): boolean {
  return state.expanded
    && state.enabled
    && state.hasNextPage
    && !state.isFetchingNextPage
    && !state.isFetchNextPageError;
}
```

- [ ] **Step 4: Write failing URL normalization tests**

Add cases to `threadsUrlState.test.ts` proving that direct and legacy expansion hydrate one name, while link building removes obsolete child paging on both expanded and collapsed URLs:

```ts
it('normalizes legacy expansion while dropping obsolete child page state', () => {
  expect(readInitialSelectedThreadParam('http://localhost/?view=threads&threads=alpha,beta')).toBe('alpha');
  expect(readInitialSelectedThreadParam('http://localhost/?view=threads&expand=first')).toBe(detailFirstSelectedThreadName);

  const url = buildThreadsViewLink({
    localQuery: 'cache',
    riskFilter: 'High',
    selectedThreadName: 'alpha',
    sorting: [{ id: 'totalTokens', desc: true }],
    visibleRowCount: threadsTablePageSize,
    threadCallSort: 'tokens',
    threadCallSortDirection: 'desc',
  }, 'http://localhost/?view=threads&thread_call_page=9');

  expect(url.searchParams.get('thread')).toBe('alpha');
  expect(url.searchParams.get('thread_call_sort')).toBe('tokens');
  expect(url.searchParams.has('thread_call_page')).toBe(false);
});

it('removes thread-only state when the accordion is collapsed', () => {
  const url = buildThreadsViewLink({
    localQuery: '',
    riskFilter: 'all',
    selectedThreadName: null,
    sorting: [],
    visibleRowCount: threadsTablePageSize,
    threadCallSort: 'newest',
    threadCallSortDirection: 'desc',
  }, 'http://localhost/?view=threads&thread=alpha&thread_call_page=4');

  expect(url.searchParams.has('thread')).toBe(false);
  expect(url.searchParams.has('thread_call_page')).toBe(false);
});
```

- [ ] **Step 5: Run URL tests and verify RED**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/threads/threadsUrlState.test.ts
```

Expected: FAIL because `ThreadsViewLinkState` still requires and serializes `visibleThreadCallCount`.

- [ ] **Step 6: Update URL state and verify GREEN**

In `threadsUrlState.ts`:

- remove `threadCallPageSize` and `readThreadCallPageVisibleRowsParam`; progressive loading supersedes five-row disclosure, and legacy `thread_call_page` is accepted as inert input then removed by canonical URL synchronization;
- remove `visibleThreadCallCount` from `ThreadsViewLinkState`;
- delete `thread_call_page` at the start of `buildThreadsViewLink`;
- preserve `thread_call_sort` and `thread_call_direction` only while `selectedThreadName` is non-null;
- normalize `detail`, `expand`, and `threads` exactly once into `thread`.

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/threads/threadCallLoading.test.ts src/features/threads/threadsUrlState.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add -- frontend/dashboard/src/features/threads/threadCallLoading.ts frontend/dashboard/src/features/threads/threadCallLoading.test.ts frontend/dashboard/src/features/threads/threadsUrlState.ts frontend/dashboard/src/features/threads/threadsUrlState.test.ts
git commit -m "feat: define progressive thread call state"
```

---

### Task 2: Virtualized Thread Accordion Grid

**Files:**
- Create: `frontend/dashboard/src/features/explore/EvidenceGridControls.tsx`
- Modify: `frontend/dashboard/src/features/explore/EvidenceGrid.tsx`
- Create: `frontend/dashboard/src/features/threads/ThreadAccordionGrid.tsx`
- Create: `frontend/dashboard/src/features/threads/ThreadAccordionGrid.test.tsx`
- Rename: `frontend/dashboard/src/features/threads/ThreadInspector.tsx` to `frontend/dashboard/src/features/threads/ThreadAccordionRows.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.module.css`

**Interfaces:**
- Produces: `EvidenceGridControls<TData>` accepting a TanStack `Table<TData>`, locked column ids, density state, and restore callback.
- Produces: `ThreadAccordionGridProps` with threads, expanded calls, progress/error state, table/call sort state, preferences, and explicit call actions.
- Produces: `ThreadCallControls` and `ThreadCallEvidenceRow` from `ThreadAccordionRows.tsx`.
- Does not modify: `EvidenceGridProps`, `EvidenceGrid` virtualization model, or shared Cache Context usage.

Use this exact accordion boundary:

```ts
export type ThreadAccordionGridProps = {
  ariaLabel: string;
  threads: ThreadRow[];
  columns: Array<ColumnDef<ThreadRow, unknown>>;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  preferences: EvidenceGridPreferences;
  expandedThreadName: string | null;
  expandedCalls: CallRow[];
  totalCallCount: number;
  loadingCalls: boolean;
  loadingMoreCalls: boolean;
  partialError: string | null;
  callSort: ThreadCallSortKey;
  callSortDirection: ThreadCallSortDirection;
  viewportHeight?: number;
  onToggleThread(threadName: string): void;
  onRetryCalls(): void;
  onCallSortChange(value: string): void;
  onCallSortDirectionChange(value: string): void;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
};
```

- [ ] **Step 1: Extract display controls under existing regression coverage**

Move the existing density buttons, column chooser, Escape/outside-click behavior, locked-column handling, and restore button from `EvidenceGrid.tsx` into `EvidenceGridControls.tsx` with this complete implementation shape:

```ts
import type { Table } from '@tanstack/react-table';
import { useEffect, useRef, useState } from 'react';
import type { EvidenceGridDensity } from './useEvidenceGridPreferences';
import styles from './EvidenceGrid.module.css';

export type EvidenceGridControlsProps<TData> = {
  ariaLabel: string;
  table: Table<TData>;
  lockedColumnIds: ReadonlySet<string>;
  density: EvidenceGridDensity;
  onDensityChange(density: EvidenceGridDensity): void;
  onRestoreDefaults(): void;
};

function headerText(header: unknown, fallback: string): string {
  return typeof header === 'string' ? header : fallback;
}

export function EvidenceGridControls<TData>({
  ariaLabel,
  table,
  lockedColumnIds,
  density,
  onDensityChange,
  onRestoreDefaults,
}: EvidenceGridControlsProps<TData>) {
  const chooserRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent && event.key === 'Escape') {
        setOpen(false);
        return;
      }
      if (event instanceof PointerEvent && !chooserRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', close);
    document.addEventListener('pointerdown', close);
    return () => {
      document.removeEventListener('keydown', close);
      document.removeEventListener('pointerdown', close);
    };
  }, [open]);

  return <div className={styles.toolbar} aria-label={`${ariaLabel} display controls`}>
    <div className={styles.densityControl} role="group" aria-label="Density">
      <button type="button" aria-pressed={density === 'compact'} onClick={() => onDensityChange('compact')}>Dense</button>
      <button type="button" aria-pressed={density === 'comfortable'} onClick={() => onDensityChange('comfortable')}>Roomy</button>
    </div>
    <div className={styles.columnChooser} ref={chooserRef}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(current => !current)}>Columns</button>
      {open ? <fieldset>
        <legend>Visible columns</legend>
        {table.getAllLeafColumns().map(column => {
          const locked = lockedColumnIds.has(column.id);
          return <label key={column.id}>
            <input
              type="checkbox"
              checked={locked || column.getIsVisible()}
              disabled={locked}
              onChange={column.getToggleVisibilityHandler()}
            />
            {headerText(column.columnDef.header, column.id)}
          </label>;
        })}
      </fieldset> : null}
    </div>
    <button type="button" className={styles.restoreButton} onClick={onRestoreDefaults}>Restore defaults</button>
  </div>;
}
```

Do not add a second column-visibility state; continue using `table.getAllLeafColumns()` and each column's existing toggle handler.

- [ ] **Step 2: Run shared grid regression tests**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/explore/EvidenceGrid.test.tsx
```

Expected: PASS with the same eight grid/preference tests and no changed labels.

- [ ] **Step 3: Write failing accordion component tests**

Create `ThreadAccordionGrid.test.tsx` with a small harness and these concrete assertions:

```ts
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
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
```

Add cases for the progress label, partial error plus retry button, focus retention, and narrow-screen stacked call copy.

- [ ] **Step 4: Run accordion tests and verify RED**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/threads/ThreadAccordionGrid.test.tsx
```

Expected: FAIL because the component does not exist.

- [ ] **Step 5: Implement flattened accordion items and virtualization**

Implement `ThreadAccordionGrid.tsx` around this discriminated union:

```ts
type ThreadAccordionItem =
  | { key: string; kind: 'thread'; thread: ThreadRow }
  | { key: string; kind: 'summary'; thread: ThreadRow }
  | { key: string; kind: 'call'; call: CallRow }
  | { key: string; kind: 'status' };

function accordionItems(
  threads: ThreadRow[],
  expandedThreadName: string | null,
  expandedCalls: CallRow[],
): ThreadAccordionItem[] {
  return threads.flatMap(thread => {
    const parent: ThreadAccordionItem = { key: `thread:${thread.name}`, kind: 'thread', thread };
    if (thread.name !== expandedThreadName) return [parent];
    return [
      parent,
      { key: `summary:${thread.name}`, kind: 'summary', thread },
      ...expandedCalls.map(call => ({ key: `call:${call.id}`, kind: 'call' as const, call })),
      { key: `status:${thread.name}`, kind: 'status' as const },
    ];
  });
}
```

Use one `useVirtualizer`:

```ts
const virtualizer = useVirtualizer({
  count: items.length,
  getScrollElement: () => scrollRef.current,
  getItemKey: index => items[index]?.key ?? index,
  estimateSize: index => items[index]?.kind === 'call' ? 112 : items[index]?.kind === 'summary' ? 132 : 52,
  measureElement: element => element.getBoundingClientRect().height,
  overscan: 8,
  initialRect: { width: 1000, height: viewportHeight },
});
```

Render all items inside the same scroll container. Parent items use TanStack table cells and the persisted visible-column set. Summary, call, and status items span the full content width. Set `aria-expanded`, `aria-controls`, and a disclosure label on parent rows. Route click, double-click, Enter, and Space through `onToggleThread`; arrow keys retain row-to-row navigation. Attach `virtualizer.measureElement` to variable-height items.

- [ ] **Step 6: Reduce the old inspector to reusable call rows**

Rename the file with Git, then replace the detached `<aside>` implementation:

```bash
git mv frontend/dashboard/src/features/threads/ThreadInspector.tsx frontend/dashboard/src/features/threads/ThreadAccordionRows.tsx
```

Export only:

```ts
export type ThreadCallControlsProps = {
  callSort: ThreadCallSortKey;
  callSortDirection: ThreadCallSortDirection;
  onCallSortChange(value: string): void;
  onCallSortDirectionChange(value: string): void;
};

export function ThreadCallControls(props: ThreadCallControlsProps): React.ReactElement;

export function ThreadCallEvidenceRow(props: {
  call: CallRow;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
}): React.ReactElement;
```

Keep existing call formatting, signal pucks, context bar, and explicit Open/Copy handlers. Remove the donut, lifecycle, relationship, impact, status, secondary fields, local five-row pager, and click-to-open behavior on the call container. Only the explicit buttons navigate or copy.

- [ ] **Step 7: Implement responsive accordion styles**

In `ThreadsPage.module.css`, add styles for:

- sticky header and virtual canvas;
- visually distinct expanded parent row;
- full-width summary strip;
- desktop call grid and narrow-screen stacked call card;
- progress, partial, retry, and empty states;
- visible focus and a non-color chevron/expanded indicator;
- minimum 44px button targets at `max-width: 760px`.

Use the existing dashboard tokens and this structural baseline; tune only spacing and token choice during browser verification:

```css
.accordionScroller {
  position: relative;
  height: 620px;
  overflow: auto;
  border: 1px solid var(--line-subtle, var(--dashboard-border));
  border-radius: 8px;
  background: var(--surface-panel, var(--dashboard-surface));
}

.accordionItem {
  position: absolute;
  inset-inline: 0;
  display: grid;
  min-width: 720px;
}

.expandedThreadRow {
  box-shadow: inset 4px 0 0 var(--signal-info, var(--dashboard-accent));
  background: var(--surface-selected, var(--dashboard-surface-soft));
}

.threadExpansionSummary,
.threadCallEvidence,
.threadLoadStatus {
  padding: 12px 16px;
  border-bottom: 1px solid var(--line-subtle, var(--dashboard-border));
}

.threadCallEvidence {
  display: grid;
  grid-template-columns: minmax(180px, 1.4fr) repeat(4, minmax(100px, .8fr)) auto;
  gap: 10px;
  align-items: center;
}

@media (max-width: 760px) {
  .accordionItem { min-width: 0; }
  .threadCallEvidence { grid-template-columns: minmax(0, 1fr); }
  .threadCallEvidence button,
  .threadExpansionSummary button,
  .threadLoadStatus button { min-height: 44px; }
}
```

Remove `.splitWorkspace` and detached `.side-panel` rules after integration no longer uses them.

- [ ] **Step 8: Verify Task 2 GREEN**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/explore/EvidenceGrid.test.tsx src/features/threads/ThreadAccordionGrid.test.tsx
npm run dashboard:typecheck
npm run dashboard:lint
```

Expected: all commands PASS.

- [ ] **Step 9: Commit Task 2**

```bash
git add -- frontend/dashboard/src/features/explore/EvidenceGridControls.tsx frontend/dashboard/src/features/explore/EvidenceGrid.tsx frontend/dashboard/src/features/threads/ThreadAccordionGrid.tsx frontend/dashboard/src/features/threads/ThreadAccordionGrid.test.tsx frontend/dashboard/src/features/threads/ThreadAccordionRows.tsx frontend/dashboard/src/features/threads/ThreadsPage.module.css frontend/dashboard/src/features/threads/ThreadInspector.tsx
git commit -m "feat: add virtualized thread accordion grid"
```

Stage the tracked old path and new path together so Git records the rename; never use `git add .`.

---

### Task 3: Integrate Accordion Orchestration And Workspace Behavior

**Files:**
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx`
- Modify: `frontend/dashboard/src/App.threads.test.tsx`

**Interfaces:**
- Consumes: `dedupeThreadCallPages`, `shouldFetchNextThreadCallPage`, `ThreadAccordionGrid`.
- Produces: `toggleThread(threadName: string): void`, nullable expanded-thread state, progressive call state, and explicit retry.
- Removes from Threads: `visibleThreadCallCount`, `ThreadInspector`, `onActivateThread`, `openThreadInvestigator`, and parent `threadActionColumn`.
- Preserves for Cache Context: `threadActionColumn` and latest-call actions where that workspace still requires them.

- [ ] **Step 1: Replace old workspace tests with failing accordion behavior**

Update `App.threads.test.tsx` so the central behavior reads:

```ts
it('expands, switches, and collapses one thread inline', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  const table = screen.getByRole('table', { name: 'Thread leaderboard' });
  const first = within(table).getByRole('row', { name: /thread-9f3a/i });
  const second = within(table).getByRole('row', { name: /thread-7c2b/i });

  fireEvent.click(first);
  expect(first).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('region', { name: /Calls for thread-9f3a/i })).toBeInTheDocument();
  expect(window.location.search).toContain('thread=thread-9f3a');

  fireEvent.click(second);
  expect(second).toHaveAttribute('aria-expanded', 'true');
  expect(screen.queryByRole('region', { name: /Calls for thread-9f3a/i })).not.toBeInTheDocument();

  fireEvent.click(second);
  expect(screen.queryByRole('region', { name: /Calls for thread-7c2b/i })).not.toBeInTheDocument();
  expect(new URLSearchParams(window.location.search).has('thread')).toBe(false);
});

it('never opens a representative call from parent activation', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /^Threads$/i }));
  const row = screen.getByRole('row', { name: /thread-9f3a/i });
  fireEvent.doubleClick(row);
  fireEvent.keyDown(row, { key: 'Enter' });
  fireEvent.keyDown(row, { key: ' ' });
  expect(screen.getByRole('heading', { name: 'Threads' })).toBeInTheDocument();
  expect(window.location.search).not.toContain('view=call');
});
```

Add focused live-query tests that mock two `/api/thread-calls` pages, include a duplicate boundary id, delay the old thread response while switching, fail the second page once, and assert:

- progress reaches the API total;
- duplicate ids render once;
- old-thread rows never appear under the new thread;
- already loaded calls remain after a later-page error;
- **Retry loading calls** resumes and completes.

- [ ] **Step 2: Run Threads integration tests and verify RED**

Run:

```bash
npm --workspace frontend/dashboard test -- src/App.threads.test.tsx
```

Expected: FAIL because the current row activation opens a representative call and the inspector is detached.

- [ ] **Step 3: Implement nullable expansion and progressive query orchestration**

In `ThreadsPage.tsx`:

```ts
const selected = selectedThreadName === detailFirstSelectedThreadName
  ? sortedThreads[0] ?? null
  : sortedThreads.find(thread => thread.name === selectedThreadName) ?? null;

function toggleThread(threadName: string) {
  setSelectedThreadName(current => current === threadName ? null : threadName);
}
```

Remove the fallback to `sortedThreads[0]`, remove `visibleThreadCallCount`, and remove `placeholderData: previous => previous` from the selected-thread query. Define one boolean and use it both for React Query and the progressive loader:

```ts
const selectedThreadQueryEnabled = focusedEndpointsEnabled
  && !contextRuntime.fileMode
  && Boolean(contextRuntime.apiToken)
  && Boolean(selectedThreadKey);
const selectedThreadCallsQuery = useInfiniteQuery({
  ...threadCallsInfiniteQueryOptions({
    runtime: contextRuntime,
    includeArchived,
    sourceKey,
    sourceRevision,
    threadKey: selectedThreadKey,
    sort: threadCallSort === 'newest' ? 'time' : threadCallSort,
    direction: threadCallSortDirection,
  }),
  enabled: selectedThreadQueryEnabled,
});
```

Build rows and progressive loading:

```ts
const focusedCallPages = selectedThreadCallsQuery.data?.pages ?? [];
const selectedCalls = useMemo(
  () => dedupeThreadCallPages(focusedCallPages, localSelectedCalls),
  [focusedCallPages, localSelectedCalls],
);

useEffect(() => {
  if (!shouldFetchNextThreadCallPage({
    expanded: Boolean(selected),
    enabled: selectedThreadQueryEnabled,
    hasNextPage: Boolean(selectedThreadCallsQuery.hasNextPage),
    isFetchingNextPage: selectedThreadCallsQuery.isFetchingNextPage,
    isFetchNextPageError: selectedThreadCallsQuery.isFetchNextPageError,
  })) return;
  void selectedThreadCallsQuery.fetchNextPage();
}, [
  selected,
  selectedThreadCallsQuery.data,
  selectedThreadCallsQuery.hasNextPage,
  selectedThreadQueryEnabled,
  selectedThreadCallsQuery.isFetchNextPageError,
  selectedThreadCallsQuery.isFetchingNextPage,
]);
```

Collapse when the selected parent disappears from `displayedThreads`; preserve global filters. Retry calls `selectedThreadCallsQuery.fetchNextPage()` once and lets the effect continue after success.

- [ ] **Step 4: Replace Table-mode presentation**

In `ThreadsExplorerView.tsx`:

- replace the Table branch's `EvidenceGrid` with `ThreadAccordionGrid`;
- remove `ThreadInspector` from the surrounding layout;
- remove `onActivateThread` and pass only `onToggleThread`;
- retain table footer, Load more threads, status badges, Cache Frontier, and Lifecycle;
- display `N of M calls loaded`, `Loading remaining calls`, `Partial result`, and retry in the accordion region.

Use `selected ?? sortedThreads[0]` only as a local analysis seed for Lifecycle; never serialize or render it as an expanded Table row.

- [ ] **Step 5: Preserve explicit child investigator navigation**

Remove the `threadActionColumn` import and usage from `ThreadsPage`'s leaderboard columns. Do not edit `features/shared/tables.tsx`; Cache Context continues to import and use the existing action. Verify the only Threads Call Investigator navigation comes from `ThreadCallEvidenceRow` buttons and that copied URLs preserve `return=threads` plus the selected `thread=` state.

- [ ] **Step 6: Verify Task 3 GREEN**

Run:

```bash
npm --workspace frontend/dashboard test -- src/App.threads.test.tsx src/features/threads/ThreadAccordionGrid.test.tsx src/features/threads/threadCallLoading.test.ts src/features/threads/threadsUrlState.test.ts
npm run dashboard:typecheck
npm run dashboard:lint
```

Expected: all commands PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add -- frontend/dashboard/src/features/threads/ThreadsPage.tsx frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx frontend/dashboard/src/App.threads.test.tsx
git commit -m "feat: expand thread calls inline"
```

---

### Task 4: Browser QA, Documentation, Generated Assets, And Release Gates

**Files:**
- Modify: `tests/playwright/dashboard-react.spec.mjs`
- Modify: `docs/dashboard-guide.md`
- Modify: `scripts/capture_dashboard_screenshots.mjs`
- Regenerate: `docs/assets/dashboard-threads.png`
- Regenerate: `src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/*`

**Interfaces:**
- Verifies: built dashboard behavior, responsive layout, explicit child navigation, return state, and synthetic documentation.
- Produces: updated bundled React assets and synthetic Threads screenshot.

- [ ] **Step 1: Add the failing Playwright flow**

Replace the old latest-call parent action with an inline flow:

```js
test('threads expand inline before an explicit child call opens', async ({ page }) => {
  await page.goto('/?view=threads');
  const threadRow = page.getByRole('row', { name: /thread-9f3a/i });
  await threadRow.click();

  await expect(threadRow).toHaveAttribute('aria-expanded', 'true');
  await expect(page).toHaveURL(/view=threads/);
  await expect(page).not.toHaveURL(/view=call/);
  const region = page.getByRole('region', { name: /Calls for thread-9f3a/i });
  await expect(region).toBeVisible();
  await region.getByRole('button', { name: /Open investigator for thread call/i }).first().click();
  await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
  await page.getByRole('button', { name: /Back to Threads/i }).click();
  await expect(page.getByRole('row', { name: /thread-9f3a/i })).toHaveAttribute('aria-expanded', 'true');
});
```

Add a narrow-viewport case at 390px asserting the call evidence stacks, the Open action remains visible, and no horizontal page overflow appears.

- [ ] **Step 2: Run the browser test and verify RED**

Run the existing Vite dev server and targeted Playwright command through repository scripts:

```bash
npm run dashboard:smoke -- --grep "threads expand inline"
```

Expected: FAIL before the built interaction is available.

- [ ] **Step 3: Update user documentation and synthetic screenshot route**

In `docs/dashboard-guide.md`, replace the inspector bullets with:

- click a thread row to expand all of its aggregate calls directly beneath it;
- only one thread stays expanded;
- remaining call pages load progressively with visible progress and retry;
- parent rows never open a representative call;
- explicit child Open/Copy actions reach Call Investigator;
- Cache Frontier and Lifecycle remain secondary analysis modes.

In `scripts/capture_dashboard_screenshots.mjs`, keep the existing synthetic `?view=threads&thread=thread-9f3a1c` query and add an explicit wait for the labeled `Calls for thread-9f3a1c` region before capture.

- [ ] **Step 4: Build and regenerate packaged assets**

Run:

```bash
npm run dashboard:build
npm run dashboard:screenshots
```

Expected:

- TypeScript and Vite build PASS;
- bundled assets in `src/codex_usage_tracker/plugin_data/dashboard/react/assets/` update;
- screenshot script confirms the synthetic fixture payload;
- `docs/assets/dashboard-threads.png` and its packaged copy show one polished inline expansion.

- [ ] **Step 5: Run focused and broad validation**

Run focused checks first:

```bash
npm --workspace frontend/dashboard test -- src/App.threads.test.tsx src/features/threads/ThreadAccordionGrid.test.tsx src/features/threads/threadCallLoading.test.ts src/features/threads/threadsUrlState.test.ts src/features/explore/EvidenceGrid.test.tsx
npm run dashboard:typecheck
npm run dashboard:lint
npm run dashboard:stylelint
python3 scripts/check_dashboard_source_budgets.py
```

Then run the repository's compact dashboard gate and release checks:

```bash
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
python scripts/check_release.py
git diff --check
```

Run the targeted Playwright smoke after the build:

```bash
npm run dashboard:smoke -- --grep "threads expand inline"
```

Expected: every command PASS. If the full dashboard gate is long, run the named task once in a background exec session and poll that same session.

- [ ] **Step 6: Perform the final privacy and diff review**

Review only intentional files:

```bash
git status --short --branch
git diff --stat
git diff -- docs/dashboard-guide.md scripts/capture_dashboard_screenshots.mjs frontend/dashboard/src/features/threads frontend/dashboard/src/features/explore/EvidenceGrid.tsx frontend/dashboard/src/features/explore/EvidenceGridControls.tsx frontend/dashboard/src/App.threads.test.tsx tests/playwright/dashboard-react.spec.mjs
```

Confirm no real session logs, prompts, context snippets, databases, local HTML dashboards, secrets, `.env` files, or non-synthetic screenshots are staged. Leave the tool-created `.idea/` directory untracked.

- [ ] **Step 7: Commit Task 4**

Stage exact paths reported by the build and screenshot commands, then commit:

```bash
git add -- tests/playwright/dashboard-react.spec.mjs docs/dashboard-guide.md scripts/capture_dashboard_screenshots.mjs docs/assets/dashboard-threads.png src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "docs: update threads expansion workflow"
```

After committing, rerun `git status --short --branch` and report the remaining untracked `.idea/` separately; do not include it in any commit.

---

## Plan Self-Review Checklist

- The plan covers all approved requirements: inline single-open expansion, progressive all-page loading, stale isolation, partial retry, bounded rendering, responsive/accessibility behavior, explicit child navigation, URL compatibility, docs, synthetic screenshot, bundled assets, and release gates.
- No server or privacy contract changes are included.
- Shared `EvidenceGrid` keeps its existing virtualization behavior; only its controls are extracted for reuse.
- Cache Context retains `threadActionColumn`; Threads removes the representative latest-call action.
- The call-query key already includes thread key, sort, direction, scope, and source, so late pages remain isolated by cache key once placeholder reuse is removed.
- Every implementation task begins with a failing test, verifies RED, implements the smallest behavior, verifies GREEN, and ends with a focused Conventional Commit.
