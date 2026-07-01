export type CsvColumn<T> = {
  header: string;
  value: (row: T) => unknown;
};

export function rowsToCsv<T>(rows: T[], columns: Array<CsvColumn<T>>): string {
  const header = columns.map(column => escapeCsvCell(column.header)).join(',');
  const body = rows.map(row => columns.map(column => escapeCsvCell(column.value(row))).join(','));
  return [header, ...body].join('\n');
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const objectUrl = typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();

  if (objectUrl.startsWith('blob:') && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(objectUrl);
  }
}

export function csvDateStamp(date = new Date()): string {
  return date.toISOString().slice(0, 10);
}

function escapeCsvCell(value: unknown): string {
  const text = String(value ?? '');
  if (/[",\n\r]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}
