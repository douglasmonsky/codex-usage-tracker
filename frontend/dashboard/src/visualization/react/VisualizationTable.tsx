import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';

import { useShellI18n } from '../../app/i18nContext';
import { formatVisualizationValue, tableRowsForVisualization } from '../spec';
import type { VisualizationSpecV1, VisualizationTableColumn } from '../spec';
import styles from './VisualizationTable.module.css';

type VisualizationTableProps = {
  onSelectionChange: (key: string) => void;
  selectedKey: string | null;
  spec: VisualizationSpecV1;
};

export function VisualizationTable({ onSelectionChange, selectedKey, spec }: VisualizationTableProps) {
  const i18n = useShellI18n();
  const rows = tableRowsForVisualization(spec);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [hasMoreRight, setHasMoreRight] = useState(false);

  const updateOverflowCue = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const remaining = element.scrollWidth - element.clientWidth - element.scrollLeft;
    setHasMoreRight(remaining > 2);
  }, []);

  useEffect(() => {
    updateOverflowCue();
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateOverflowCue);
    observer.observe(element);
    const table = element.querySelector('table');
    if (table) observer.observe(table);
    return () => observer.disconnect();
  }, [spec, updateOverflowCue]);

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, rowIndex: number) {
    const nextIndex = nextKeyboardIndex(event.key, rowIndex, rows.length);
    if (nextIndex === null) return;
    event.preventDefault();
    const nextRow = rows[nextIndex];
    onSelectionChange(nextRow.key);
    event.currentTarget.parentElement
      ?.querySelector<HTMLTableRowElement>(`tr[data-selection-key="${CSS.escape(nextRow.key)}"]`)
      ?.focus();
  }

  return (
    <div className={styles.tableFrame} data-overflow-right={hasMoreRight}>
      <div
        ref={scrollRef}
        className={styles.tableScroll}
        role="region"
        aria-label={i18n.translateText(`${spec.title} table`)}
        tabIndex={0}
        onScroll={updateOverflowCue}
      >
        <table className={styles.table}>
        <caption>{spec.table.caption}</caption>
        <thead>
          <tr>
            {spec.table.columns.map(column => (
              <th key={column.field} scope="col" className={column.align === 'right' ? styles.numeric : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={row.key}
              data-selection-key={row.key}
              aria-selected={selectedKey === row.key}
              tabIndex={0}
              onClick={() => onSelectionChange(row.key)}
              onKeyDown={event => handleRowKeyDown(event, rowIndex)}
            >
              {spec.table.columns.map(column => (
                <td key={column.field} className={column.align === 'right' ? styles.numeric : undefined}>
                  {formatVisualizationValue(row.values[column.field] ?? null, column)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </div>
  );
}

export function selectedVisualizationLabel(spec: VisualizationSpecV1, selectedKey: string | null): string | null {
  if (!selectedKey) return null;
  const row = tableRowsForVisualization(spec).find(candidate => candidate.key === selectedKey);
  if (!row) return null;
  const preferredField = spec.interactions?.selection?.labelField;
  const preferredColumn = preferredField
    ? spec.table.columns.find(column => column.field === preferredField)
    : spec.table.columns[0];
  return preferredColumn ? labelForColumn(row.values[preferredColumn.field] ?? null, preferredColumn) : selectedKey;
}

function labelForColumn(value: string | number | boolean | null, column: VisualizationTableColumn) {
  return `${column.label}: ${formatVisualizationValue(value, column)}`;
}

function nextKeyboardIndex(key: string, currentIndex: number, rowCount: number): number | null {
  if (!rowCount) return null;
  if (key === 'ArrowDown' || key === 'ArrowRight') return Math.min(rowCount - 1, currentIndex + 1);
  if (key === 'ArrowUp' || key === 'ArrowLeft') return Math.max(0, currentIndex - 1);
  if (key === 'Home') return 0;
  if (key === 'End') return rowCount - 1;
  return null;
}
