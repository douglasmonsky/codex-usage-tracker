import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronsRight } from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

import styles from './EvidenceGrid.module.css';
import { EvidenceGridControls } from './EvidenceGridControls';
import type { EvidenceGridDensity } from './useEvidenceGridPreferences';

type EvidenceGridMobilePresentation<TData> = {
  primary: (row: TData, rank: number) => ReactNode;
  secondary: (row: TData, rank: number) => ReactNode;
  actionLabel: (row: TData, rank: number) => string;
};

export type EvidenceGridProps<TData> = {
  ariaLabel: string;
  columns: Array<ColumnDef<TData, unknown>>;
  data: TData[];
  identityColumnId: string;
  lockedColumnIds?: string[];
  getRowId: (row: TData, index: number) => string;
  mobile: EvidenceGridMobilePresentation<TData>;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  columnVisibility: VisibilityState;
  onColumnVisibilityChange: OnChangeFn<VisibilityState>;
  density: EvidenceGridDensity;
  onDensityChange: (density: EvidenceGridDensity) => void;
  onRestoreDefaults: () => void;
  emptyLabel?: string;
  selectedRowId?: string;
  onRowSelect?: (row: TData) => void;
  onRowActivate?: (row: TData) => void;
  activateOnClick?: boolean;
  selectOnHover?: boolean;
  viewportHeight?: number;
  mobileBreakpoint?: string;
  manualSorting?: boolean;
};

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false
  ));

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mediaQuery = window.matchMedia(query);
    const update = () => setMatches(mediaQuery.matches);
    update();
    mediaQuery.addEventListener('change', update);
    return () => mediaQuery.removeEventListener('change', update);
  }, [query]);

  return matches;
}

function headerText(header: unknown, fallback: string): string {
  return typeof header === 'string' ? header : fallback;
}

export function EvidenceGrid<TData>({
  ariaLabel,
  columns,
  data,
  identityColumnId,
  lockedColumnIds = [],
  getRowId,
  mobile,
  sorting,
  onSortingChange,
  columnVisibility,
  onColumnVisibilityChange,
  density,
  onDensityChange,
  onRestoreDefaults,
  emptyLabel = 'No evidence matches the current filters.',
  selectedRowId,
  onRowSelect,
  onRowActivate,
  activateOnClick = false,
  selectOnHover = false,
  viewportHeight = 480,
  mobileBreakpoint = '(max-width: 700px)',
  manualSorting = false,
}: EvidenceGridProps<TData>) {
  const isMobile = useMediaQuery(mobileBreakpoint);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const table = useReactTable({
    columns,
    data,
    state: { sorting, columnVisibility },
    onSortingChange,
    onColumnVisibilityChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting,
    getRowId,
    enableSortingRemoval: false,
  });
  const rows = table.getRowModel().rows;
  const rowHeight = isMobile ? 64 : density === 'compact' ? 38 : 52;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    getItemKey: index => rows[index]?.id ?? index,
    overscan: 6,
    initialRect: { width: 800, height: viewportHeight },
  });
  const measuredVirtualRows = virtualizer.getVirtualItems();
  const initialWindowSize = Math.min(rows.length, Math.ceil(viewportHeight / rowHeight) + 6);
  const virtualRows = measuredVirtualRows.length
    ? measuredVirtualRows
    : rows.slice(0, initialWindowSize).map((row, index) => ({
        key: row.id,
        index,
        start: index * rowHeight,
        end: (index + 1) * rowHeight,
        size: rowHeight,
        lane: 0,
      }));

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || isMobile) {
      setCanScrollRight(false);
      return undefined;
    }
    const update = () => setCanScrollRight(scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 2);
    update();
    scroller.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      scroller.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [columns, data.length, isMobile, columnVisibility]);

  const lockedColumns = new Set([identityColumnId, ...lockedColumnIds]);

  function clickRow(row: TData) {
    if (activateOnClick && onRowActivate) {
      onRowSelect?.(row);
      onRowActivate(row);
      return;
    }
    (onRowSelect ?? onRowActivate)?.(row);
  }

  function rowKeyDown(event: React.KeyboardEvent<HTMLElement>, index: number, row: TData) {
    if (event.key === 'Enter') {
      event.preventDefault();
      (onRowActivate ?? onRowSelect)?.(row);
      return;
    }
    if (event.key === ' ') {
      event.preventDefault();
      (onRowSelect ?? onRowActivate)?.(row);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const nextIndex = index + (event.key === 'ArrowDown' ? 1 : -1);
      if (nextIndex < 0 || nextIndex >= rows.length) return;
      const grid = event.currentTarget.closest(`.${styles.grid}`);
      virtualizer.scrollToIndex(nextIndex, { align: 'auto' });
      window.setTimeout(() => grid?.querySelector<HTMLElement>(`[data-row-index="${nextIndex}"]`)?.focus());
    }
  }

  const toolbar = (
    <EvidenceGridControls
      ariaLabel={ariaLabel}
      table={table}
      lockedColumnIds={lockedColumns}
      density={density}
      onDensityChange={onDensityChange}
      onRestoreDefaults={onRestoreDefaults}
    />
  );

  if (!rows.length && isMobile) {
    return (
      <section className={styles.grid} aria-label={ariaLabel}>
        {toolbar}
        <p className={styles.empty} role="status">{emptyLabel}</p>
      </section>
    );
  }

  if (isMobile) {
    return (
      <section className={styles.grid} aria-label={ariaLabel}>
        {toolbar}
        <div
          ref={scrollRef}
          className={styles.mobileScroller}
          style={{ height: viewportHeight }}
          data-layout-scroll="true"
          data-virtualized="true"
          data-virtual-row-count={virtualRows.length}
        >
        <ol className={styles.mobileList} aria-label={`${ariaLabel} ranked list`} style={{ height: virtualizer.getTotalSize() }}>
          {virtualRows.map(virtualRow => {
            const row = rows[virtualRow.index];
            if (!row) return null;
            const rank = virtualRow.index + 1;
            const selected = row.id === selectedRowId;
            return (
              <li key={row.id} style={{ height: virtualRow.size, transform: `translateY(${virtualRow.start}px)` }}>
                <button
                  type="button"
                  className={selected ? styles.mobileRowSelected : styles.mobileRow}
                  aria-label={mobile.actionLabel(row.original, rank)}
                  aria-pressed={selected}
                  data-row-index={virtualRow.index}
                  onClick={() => clickRow(row.original)}
                  onDoubleClick={() => (onRowActivate ?? onRowSelect)?.(row.original)}
                  onMouseEnter={selectOnHover && onRowSelect ? () => onRowSelect(row.original) : undefined}
                  onKeyDown={event => rowKeyDown(event, virtualRow.index, row.original)}
                >
                  <span className={styles.rank} aria-hidden="true">{rank}</span>
                  <span className={styles.mobileCopy}>
                    <strong>{mobile.primary(row.original, rank)}</strong>
                    <small>{mobile.secondary(row.original, rank)}</small>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        </div>
        <p className={styles.rowCount}>{rows.length.toLocaleString()} ranked evidence rows</p>
      </section>
    );
  }

  const tableWidth = Math.max(table.getTotalSize(), 720);

  return (
    <section className={styles.grid} aria-label={ariaLabel}>
      {toolbar}
      {canScrollRight ? (
        <button
          className={styles.continuationCue}
          type="button"
          aria-label="Show more columns"
          title="Show more columns"
          onClick={() => scrollRef.current?.scrollBy({ left: 280, behavior: 'smooth' })}
        >
          More columns <ChevronsRight aria-hidden="true" />
        </button>
      ) : null}
      <div
        className={styles.scroller}
        ref={scrollRef}
        style={{ height: viewportHeight }}
        data-layout-scroll="true"
        data-virtualized="true"
        data-virtual-row-count={virtualRows.length}
      >
        <table className={styles.table} aria-label={ariaLabel} aria-rowcount={rows.length + 1} style={{ width: tableWidth }}>
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map(header => {
                  const sorted = header.column.getIsSorted();
                  const frozen = header.column.id === identityColumnId;
                  const label = headerText(header.column.columnDef.header, header.column.id);
                  return (
                    <th
                      key={header.id}
                      className={frozen ? `${styles.frozenCell} sticky-column` : undefined}
                      style={{ width: header.getSize() }}
                      aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                      scope="col"
                    >
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          type="button"
                          aria-label={`Sort by ${label}`}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          <span>{flexRender(header.column.columnDef.header, header.getContext())}</span>
                          <span aria-hidden="true">{sorted === 'asc' ? ' ↑' : sorted === 'desc' ? ' ↓' : ' ↕'}</span>
                        </button>
                      ) : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody style={{ height: virtualizer.getTotalSize() }}>
            {virtualRows.map(virtualRow => {
              const row = rows[virtualRow.index];
              if (!row) return null;
              const selected = row.id === selectedRowId;
              const rowStyle = {
                height: virtualRow.size,
                transform: `translateY(${virtualRow.start}px)`,
                width: tableWidth,
              } as CSSProperties;
              return (
                <tr
                  key={row.id}
                  className={selected ? styles.selectedRow : styles.row}
                  style={rowStyle}
                  tabIndex={onRowSelect || onRowActivate ? 0 : undefined}
                  aria-selected={selected}
                  data-row-index={virtualRow.index}
                  onClick={() => clickRow(row.original)}
                  onDoubleClick={() => (onRowActivate ?? onRowSelect)?.(row.original)}
                  onMouseEnter={selectOnHover && onRowSelect ? () => onRowSelect(row.original) : undefined}
                  onKeyDown={event => rowKeyDown(event, virtualRow.index, row.original)}
                >
                  {row.getVisibleCells().map(cell => (
                    <td
                      key={cell.id}
                      className={cell.column.id === identityColumnId ? `${styles.frozenCell} sticky-column` : undefined}
                      style={{ width: cell.column.getSize() }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!rows.length ? <p className={styles.empty} role="status">{emptyLabel}</p> : null}
      <p className={styles.rowCount}>{rows.length.toLocaleString()} ranked evidence rows</p>
    </section>
  );
}
