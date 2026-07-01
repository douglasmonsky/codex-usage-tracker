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
  selectedRowId?: string;
  onRowSelect?: (row: T) => void;
  ariaLabel?: string;
  columnVisibility?: VisibilityState;
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>;
};

export function DataTable<T>({
  columns,
  data,
  compact = false,
  emptyLabel = 'No rows match current filters.',
  getRowId,
  selectedRowId,
  onRowSelect,
  ariaLabel,
  columnVisibility,
  onColumnVisibilityChange,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    columns,
    data,
    state: { sorting, ...(columnVisibility ? { columnVisibility } : {}) },
    onSortingChange: setSorting,
    onColumnVisibilityChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(getRowId ? { getRowId } : {}),
  });

  return (
    <div className="table-scroll">
      <table className={compact ? 'data-table compact' : 'data-table'} aria-label={ariaLabel}>
        <thead>
          {table.getHeaderGroups().map(headerGroup => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map(header => {
                const sorted = header.column.getIsSorted();
                return (
                  <th key={header.id} aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none'}>
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
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map(row => {
              const isSelected = row.id === selectedRowId;
              return (
                <tr
                  key={row.id}
                  className={[onRowSelect ? 'is-clickable' : '', isSelected ? 'selected-row' : ''].filter(Boolean).join(' ')}
                  aria-selected={isSelected || undefined}
                  tabIndex={onRowSelect ? 0 : undefined}
                  onClick={onRowSelect ? () => onRowSelect(row.original) : undefined}
                  onKeyDown={
                    onRowSelect
                      ? event => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            onRowSelect(row.original);
                          }
                        }
                      : undefined
                  }
                >
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
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
  );
}

function headerLabel(header: unknown): string {
  return typeof header === 'string' ? header : 'column';
}
