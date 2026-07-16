import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useEffect, useRef, type CSSProperties } from 'react';
import type { CallRow, ThreadRow } from '../../api/types';
import { EvidenceGridControls } from '../explore/EvidenceGridControls';
import type { EvidenceGridPreferences } from '../explore/useEvidenceGridPreferences';
import { ThreadCallControls, ThreadCallEvidenceRow } from './ThreadAccordionRows';
import type { ThreadCallSortDirection, ThreadCallSortKey } from './threadsUrlState';
import styles from './ThreadsPage.module.css';

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

function headerText(header: unknown, fallback: string): string {
  return typeof header === 'string' ? header : fallback;
}

export function ThreadAccordionGrid({
  ariaLabel,
  threads,
  columns,
  sorting,
  onSortingChange,
  preferences,
  expandedThreadName,
  expandedCalls,
  totalCallCount,
  loadingCalls,
  loadingMoreCalls,
  partialError,
  callSort,
  callSortDirection,
  viewportHeight = 620,
  onToggleThread,
  onRetryCalls,
  onCallSortChange,
  onCallSortDirectionChange,
  onOpenInvestigator,
  onCopyCallLink,
}: ThreadAccordionGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const table = useReactTable({
    columns,
    data: threads,
    state: { sorting, columnVisibility: preferences.columnVisibility },
    onSortingChange,
    onColumnVisibilityChange: preferences.setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: row => row.name,
    enableSortingRemoval: false,
  });
  const rows = table.getRowModel().rows;
  const items = accordionItems(rows.map(row => row.original), expandedThreadName, expandedCalls);
  const roomy = preferences.density === 'comfortable';
  const estimatedSize = (index: number) => {
    const kind = items[index]?.kind;
    if (kind === 'call') return roomy ? 128 : 96;
    if (kind === 'summary') return roomy ? 140 : 116;
    if (kind === 'status') return roomy ? 56 : 48;
    return roomy ? 56 : 44;
  };
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    getItemKey: index => items[index]?.key ?? index,
    estimateSize: estimatedSize,
    measureElement: element => element.getBoundingClientRect().height,
    overscan: 8,
    initialRect: { width: 1000, height: viewportHeight },
  });
  useEffect(() => virtualizer.measure(), [preferences.density, virtualizer]);
  const measuredVirtualItems = virtualizer.getVirtualItems();
  let estimatedStart = 0;
  const estimatedItems = items.map((item, index) => {
    const size = estimatedSize(index);
    const virtualItem = { key: item.key, index, start: estimatedStart, end: estimatedStart + size, size, lane: 0 };
    estimatedStart += size;
    return virtualItem;
  });
  const virtualItems = measuredVirtualItems.length
    ? measuredVirtualItems
    : estimatedItems.filter(item => item.start < viewportHeight + 896);
  const totalSize = virtualizer.getTotalSize() || estimatedStart;
  const tableWidth = Math.max(table.getTotalSize(), 720);
  const expandedThreadId = expandedThreadName ? `thread-row-${encodeURIComponent(expandedThreadName)}` : undefined;
  const regionId = expandedThreadName ? `thread-calls-${encodeURIComponent(expandedThreadName)}` : undefined;
  const regionLabelId = regionId ? `${regionId}-label` : undefined;

  function toggleKeyDown(event: React.KeyboardEvent<HTMLDivElement>, name: string, itemIndex: number) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onToggleThread(name);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      let next = itemIndex + direction;
      while (items[next] && items[next].kind !== 'thread') next += direction;
      if (!items[next]) return;
      virtualizer.scrollToIndex(next, { align: 'auto' });
      window.setTimeout(() => scrollRef.current?.querySelector<HTMLElement>(`[data-item-index="${next}"]`)?.focus());
    }
  }

  return (
    <section className={styles.accordionGrid}>
      <EvidenceGridControls
        ariaLabel={ariaLabel}
        table={table}
        lockedColumnIds={new Set(['name'])}
        density={preferences.density}
        onDensityChange={preferences.setDensity}
        onRestoreDefaults={preferences.restoreDefaults}
      />
      <div
        ref={scrollRef}
        className={styles.accordionScroller}
        style={{ height: viewportHeight }}
        role="treegrid"
        aria-label={ariaLabel}
        aria-rowcount={items.length + 1}
        data-density={preferences.density}
        data-testid="thread-accordion-scroller"
        data-layout-scroll="true"
        data-virtualized="true"
      >
        <div role="rowgroup" className={styles.accordionHeaderGroup}>
          <div className={styles.accordionHeader} role="row" style={{ width: tableWidth }}>
            {table.getHeaderGroups()[0]?.headers.map(header => {
              const sorted = header.column.getIsSorted();
              const label = headerText(header.column.columnDef.header, header.column.id);
              return <div key={header.id} role="columnheader" aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined} style={{ width: header.getSize() }}>
                {header.column.getCanSort() ? <button type="button" aria-label={`Sort by ${label}`} onClick={header.column.getToggleSortingHandler()}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  <span aria-hidden="true">{sorted === 'asc' ? ' ↑' : sorted === 'desc' ? ' ↓' : ' ↕'}</span>
                </button> : flexRender(header.column.columnDef.header, header.getContext())}
              </div>;
            })}
          </div>
        </div>
        <div
          className={styles.accordionCanvas}
          role="rowgroup"
          style={{ height: totalSize, width: tableWidth }}
        >
          {virtualItems.map(virtualItem => {
            const item = items[virtualItem.index];
            if (!item) return null;
            const itemStyle = { transform: `translateY(${virtualItem.start}px)`, width: tableWidth } as CSSProperties;
            if (item.kind === 'thread') {
              const row = rows.find(candidate => candidate.original.name === item.thread.name);
              if (!row) return null;
              const expanded = item.thread.name === expandedThreadName;
              const threadId = `thread-row-${encodeURIComponent(item.thread.name)}`;
              return <div
                key={item.key}
                ref={virtualizer.measureElement}
                id={threadId}
                role="row"
                className={`${styles.accordionItem} ${styles.threadRow} ${expanded ? styles.expandedThreadRow : ''}`}
                style={{ ...itemStyle, minHeight: estimatedSize(virtualItem.index) }}
                tabIndex={0}
                aria-label={`${expanded ? 'Collapse' : 'Expand'} calls for ${item.thread.name}`}
                aria-expanded={expanded}
                aria-level={1}
                aria-controls={expanded ? regionId : undefined}
                data-accordion-item
                data-index={virtualItem.index}
                data-item-index={virtualItem.index}
                onClick={event => {
                  if (event.detail < 2) onToggleThread(item.thread.name);
                }}
                onKeyDown={event => toggleKeyDown(event, item.thread.name, virtualItem.index)}
              >
                <span className={styles.disclosureChevron} aria-hidden="true">›</span>
                {row.getVisibleCells().map(cell => <div key={cell.id} role="gridcell" style={{ width: cell.column.getSize() }}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </div>)}
              </div>;
            }
            if (item.kind === 'summary') {
              return <div key={item.key} ref={virtualizer.measureElement} id={`${regionId}-summary-row`} role="row" aria-level={2} aria-describedby={expandedThreadId} className={styles.accordionItem} style={{ ...itemStyle, minHeight: estimatedSize(virtualItem.index) }} data-accordion-item data-index={virtualItem.index}>
                <div role="gridcell">
                  <section
                    id={regionId}
                    role="region"
                    aria-labelledby={regionLabelId}
                    aria-describedby={expandedThreadId}
                    className={styles.threadExpansionSummary}
                  >
                    <span id={regionLabelId} className={styles.visuallyHidden}>Calls for {item.thread.name}</span>
                    <div><strong>{item.thread.name}</strong><span>{expandedCalls.length} of {totalCallCount} calls loaded</span></div>
                    <ThreadCallControls callSort={callSort} callSortDirection={callSortDirection} onCallSortChange={onCallSortChange} onCallSortDirectionChange={onCallSortDirectionChange} />
                  </section>
                </div>
              </div>;
            }
            if (item.kind === 'call') {
              return <div key={item.key} ref={virtualizer.measureElement} id={`thread-call-row-${encodeURIComponent(item.call.id)}`} role="row" aria-level={2} aria-describedby={expandedThreadId} className={styles.accordionItem} style={{ ...itemStyle, minHeight: estimatedSize(virtualItem.index) }} data-accordion-item data-index={virtualItem.index}>
                <div role="gridcell"><ThreadCallEvidenceRow call={item.call} onOpenInvestigator={onOpenInvestigator} onCopyCallLink={onCopyCallLink} /></div>
              </div>;
            }
            return <div key={item.key} ref={virtualizer.measureElement} id={`${regionId}-status-row`} role="row" aria-level={2} aria-describedby={expandedThreadId} className={styles.accordionItem} style={{ ...itemStyle, minHeight: estimatedSize(virtualItem.index) }} data-accordion-item data-index={virtualItem.index}>
              <div role="gridcell"><div className={styles.threadLoadStatus} role="status">
                {partialError ? <><span>{partialError}</span><button type="button" onClick={onRetryCalls} aria-label="Retry loading thread calls">Retry</button></> : null}
                {!partialError && loadingCalls ? <span>Loading calls</span> : null}
                {!partialError && loadingMoreCalls ? <span>Loading more calls</span> : null}
                {!partialError && !loadingCalls && !loadingMoreCalls && !expandedCalls.length ? <span>No loaded aggregate call rows belong to this thread.</span> : null}
                {!partialError && !loadingCalls && !loadingMoreCalls && expandedCalls.length && expandedCalls.length < totalCallCount ? <span>{totalCallCount - expandedCalls.length} more calls available</span> : null}
                {!partialError && !loadingCalls && !loadingMoreCalls && expandedCalls.length >= totalCallCount && expandedCalls.length ? <span>All loaded calls visible</span> : null}
              </div></div>
            </div>;
          })}
        </div>
      </div>
    </section>
  );
}
