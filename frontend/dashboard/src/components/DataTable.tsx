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
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { useState } from 'react';

type DataTableProps<T> = {
  columns: Array<ColumnDef<T>>;
  data: T[];
  compact?: boolean;
  emptyLabel?: string;
  getRowId?: (row: T, index: number) => string;
  getRowActionLabel?: (row: T) => string;
  selectedRowId?: string;
  onRowSelect?: (row: T) => void;
  onRowActivate?: (row: T) => void;
  activateOnClick?: boolean;
  selectOnHover?: boolean;
  ariaLabel?: string;
  columnVisibility?: VisibilityState;
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>;
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;
  manualSorting?: boolean;
  initialVisibleRows?: number;
  visibleRowsIncrement?: number;
  visibleRowCount?: number;
  onVisibleRowCountChange?: (count: number) => void;
};

const defaultVisibleRows = 250;
const defaultVisibleRowsIncrement = 250;

export function DataTable<T>({
  columns,
  data,
  compact = false,
  emptyLabel = 'No rows match current filters.',
  getRowId,
  getRowActionLabel,
  selectedRowId,
  onRowSelect,
  onRowActivate,
  activateOnClick = false,
  selectOnHover,
  ariaLabel,
  columnVisibility,
  onColumnVisibilityChange,
  sorting,
  onSortingChange,
  manualSorting = false,
  initialVisibleRows = defaultVisibleRows,
  visibleRowsIncrement = defaultVisibleRowsIncrement,
  visibleRowCount,
  onVisibleRowCountChange,
}: DataTableProps<T>) {
const [internalSorting, setInternalSorting] = useState<SortingState>([]);
const [internalVisibleRowCount, setInternalVisibleRowCount] = useState(initialVisibleRows);
const tableSorting = sorting ?? internalSorting;
const handleSortingChange = onSortingChange ?? setInternalSorting;
const tableVisibleRowCount = visibleRowCount ?? internalVisibleRowCount;
const table = useReactTable({
columns,
data,
state: { sorting: tableSorting, ...(columnVisibility ? { columnVisibility } : {}) },
onSortingChange: handleSortingChange,
onColumnVisibilityChange,
getCoreRowModel: getCoreRowModel(),
getSortedRowModel: getSortedRowModel(),
enableSortingRemoval: false,
manualSorting,
...(getRowId ? { getRowId } : {}),
});
const rows = table.getRowModel().rows;
const visibleRows = rows.slice(0, tableVisibleRowCount);
const hiddenRowCount = Math.max(0, rows.length - visibleRows.length);

function showMoreRows() {
const nextVisibleRowCount = Math.min(rows.length, tableVisibleRowCount + visibleRowsIncrement);
if (onVisibleRowCountChange) {
onVisibleRowCountChange(nextVisibleRowCount);
return;
}
setInternalVisibleRowCount(nextVisibleRowCount);
}

  return (
    <div className="table-window">
      <div className="table-scroll">
        <table className={compact ? 'data-table compact' : 'data-table'} aria-label={ariaLabel}>
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map(header => {
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={stickyColumnClass(header.column.id)}
                      aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none'}
                    >
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          className="sort-header"
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          aria-label={`Sort by ${headerLabel(header.column.columnDef.header)}`}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sorted === 'asc' ? <ArrowUp size={13} /> : sorted === 'desc' ? <ArrowDown size={13} /> : <ChevronsUpDown size={13} />}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length ? (
              visibleRows.map(row => {
                const isSelected = row.id === selectedRowId;
                const isInteractive = Boolean(onRowSelect || onRowActivate);
                const clickActivates = Boolean(onRowActivate && (!onRowSelect || activateOnClick));
                const rowActionLabel = getRowActionLabel?.(row.original);
                const selectRow = () => onRowSelect?.(row.original);
                const activateRow = () => (onRowActivate ?? onRowSelect)?.(row.original);
                const clickRow = () => {
                  if (clickActivates) {
                    selectRow();
                    activateRow();
                    return;
                  }
                  if (onRowSelect) {
                    selectRow();
                  } else {
                    activateRow();
                  }
                };
                return (
                  <tr
                    key={row.id}
                    className={[
                      isInteractive ? 'is-clickable' : '',
                      onRowActivate ? 'is-activatable' : '',
                      isSelected ? 'selected-row' : '',
                    ].filter(Boolean).join(' ')}
                    aria-label={rowActionLabel}
                    aria-selected={isSelected || undefined}
                    tabIndex={isInteractive ? 0 : undefined}
                    title={
                      rowActionLabel ??
                      (onRowActivate
                        ? onRowSelect
                          ? activateOnClick
                            ? 'Click opens full investigator. Hover or press Space previews details.'
                            : 'Click to inspect details. Double-click or press Enter open full investigator.'
                          : 'Click or press Enter open the full investigator.'
                        : undefined)
                    }
                    onClick={isInteractive ? clickRow : undefined}
                    onMouseEnter={selectOnHover && onRowSelect ? selectRow : undefined}
                    onDoubleClick={onRowActivate ? activateRow : undefined}
                    onKeyDown={
                      isInteractive
                        ? event => {
                            if (event.key === 'Enter') {
                              event.preventDefault();
                              activateRow();
                            }
                            if (event.key === ' ') {
                              event.preventDefault();
                              if (onRowSelect) {
                                selectRow();
                              } else {
                                activateRow();
                              }
                            }
                          }
                        : undefined
                    }
                  >
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className={stickyColumnClass(cell.column.id)}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={Math.max(table.getVisibleLeafColumns().length, 1)} className="empty-cell">
                  {emptyLabel}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {hiddenRowCount ? (
        <div className="table-window-footer">
          <span>
            Showing {visibleRows.length.toLocaleString()} of {rows.length.toLocaleString()} table rows
          </span>
          <button type="button" className="inline-button" onClick={showMoreRows}>
            Show {Math.min(visibleRowsIncrement, hiddenRowCount).toLocaleString()} more rows
          </button>
        </div>
      ) : null}
    </div>
  );
}

function headerLabel(header: unknown): string {
  return typeof header === 'string' ? header : 'column';
}

function stickyColumnClass(columnId: string): string | undefined {
  return columnId === 'thread' ? 'sticky-column' : undefined;
}
