import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';

type DataTableProps<T> = {
  columns: Array<ColumnDef<T>>;
  data: T[];
  compact?: boolean;
  emptyLabel?: string;
};

export function DataTable<T>({ columns, data, compact = false, emptyLabel = 'No rows match the current filters.' }: DataTableProps<T>) {
  const table = useReactTable({ columns, data, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="table-scroll">
      <table className={compact ? 'data-table compact' : 'data-table'}>
        <thead>
          {table.getHeaderGroups().map(headerGroup => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map(header => (
                <th key={header.id}>
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map(row => (
              <tr key={row.id}>
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="empty-cell">
                {emptyLabel}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
